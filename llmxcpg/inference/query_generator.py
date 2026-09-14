"""LLMxCPG-Q: generate CPGQL queries from source code.

Backed by vLLM for high-throughput batch inference (the paper §4.2 specifies
vLLM for query inference).

The model returns a JSON object `{"queries": [...]}`. We parse it strictly
because anything else is a generation failure, and the bootstrap loop relies
on the parse failure mode being deterministic.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
from dataclasses import dataclass

from llmxcpg.config import ModelConfig
from llmxcpg.prompts import render_query_prompt

logger = logging.getLogger(__name__)


@dataclass
class QueryGenerationOutput:
    """Result of one Q-model call."""
    queries: list[str]
    raw_text: str
    parsed_ok: bool
    error: str | None = None


class QueryGenerator:
    """Wrap a local vLLM or OpenAI-compatible query-generation engine.

    For testing, you can pass `engine="dummy"` to get a stub that always
    returns a hardcoded query bundle.
    """

    def __init__(
        self,
        model_path: str,
        max_context: int = 32_768,
        temperature: float = 0.0,
        top_p: float = 1.0,
        engine: str = "vllm",
        gpu_memory_utilization: float = 0.9,
        tensor_parallel_size: int = 1,
        base_url: str | None = None,
        api_key_env: str = "LLMXCPG_QUERY_API_KEY",
        revision: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.max_context = max_context
        self.temperature = temperature
        self.top_p = top_p
        self._engine_kind = engine

        if engine == "vllm":
            self._llm, self._sampling_params = self._init_vllm(
                model_path, max_context, temperature, top_p,
                gpu_memory_utilization, tensor_parallel_size, revision,
            )
        elif engine == "dummy":
            self._llm = None
            self._sampling_params = None
        elif engine == "openai":
            if not base_url:
                raise ValueError("base_url is required for the OpenAI-compatible query engine.")
            from openai import OpenAI

            self._llm = OpenAI(
                base_url=base_url,
                api_key=os.environ.get(api_key_env, "EMPTY"),
            )
            self._sampling_params = None
        else:
            raise ValueError(f"Unknown engine: {engine}")

    @classmethod
    def from_config(cls, cfg: ModelConfig, **kwargs) -> QueryGenerator:
        return cls(
            model_path=cfg.query_model_path,
            max_context=cfg.query_max_context,
            temperature=cfg.query_temperature,
            engine=cfg.query_engine,
            gpu_memory_utilization=cfg.query_gpu_memory_utilization,
            tensor_parallel_size=cfg.query_tensor_parallel_size,
            base_url=cfg.query_base_url,
            api_key_env=cfg.query_api_key_env,
            revision=cfg.query_model_revision,
            **kwargs,
        )

    @property
    def uses_local_gpu(self) -> bool:
        return self._engine_kind == "vllm"

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def generate(self, code: str) -> QueryGenerationOutput:
        """Generate CPGQL queries for one code sample."""
        prompt = render_query_prompt(code)
        text = self._raw_generate(prompt)
        return self._parse(text)

    def generate_batch(self, codes: list[str]) -> list[QueryGenerationOutput]:
        """Generate a batch (native batching for vLLM, sequential for HTTP)."""
        prompts = [render_query_prompt(c) for c in codes]
        if self._engine_kind == "dummy":
            return [self._parse(self._dummy_response(c)) for c in codes]
        if self._llm is None:
            raise RuntimeError(
                "The query engine has been closed. Create a new pipeline before another batch."
            )
        if self._engine_kind == "openai":
            return [self._parse(self._openai_generate(p)) for p in prompts]

        # vLLM batch
        prompts = [self._format_vllm_prompt(p) for p in prompts]
        outputs = self._llm.generate(prompts, self._sampling_params)
        results: list[QueryGenerationOutput] = []
        for out in outputs:
            text = out.outputs[0].text if out.outputs else ""
            results.append(self._parse(text))
        return results

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _raw_generate(self, prompt: str) -> str:
        if self._engine_kind == "dummy":
            return self._dummy_response(prompt)
        if self._llm is None:
            raise RuntimeError(
                "The local query model has been released. Use detect_batch for multiple "
                "samples, use the OpenAI-compatible query engine, or retain both models."
            )
        if self._engine_kind == "openai":
            return self._openai_generate(prompt)
        outs = self._llm.generate([self._format_vllm_prompt(prompt)], self._sampling_params)
        return outs[0].outputs[0].text if outs and outs[0].outputs else ""

    def _format_vllm_prompt(self, prompt: str) -> str:
        tokenizer = self._llm.get_tokenizer()
        if getattr(tokenizer, "chat_template", None):
            return tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
        logger.warning("Query tokenizer has no chat template; using the raw prompt.")
        return prompt

    def _openai_generate(self, prompt: str) -> str:
        response = self._llm.chat.completions.create(
            model=self.model_path,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    def close(self) -> None:
        """Release a local vLLM engine before the detector is loaded."""
        if self._llm is None:
            return
        engine = self._llm
        self._llm = None
        if self._engine_kind == "vllm":
            try:
                shutdown = getattr(engine, "shutdown", None)
                if callable(shutdown):
                    shutdown()
                else:
                    executor = getattr(getattr(engine, "llm_engine", None),
                                       "model_executor", None)
                    executor_shutdown = getattr(executor, "shutdown", None)
                    if callable(executor_shutdown):
                        executor_shutdown()
            except Exception as exc:  # noqa: BLE001 - vLLM exposes backend-specific errors
                logger.warning("vLLM engine shutdown reported an error: %s", exc)
            del engine
            try:
                from vllm.distributed.parallel_state import (
                    destroy_distributed_environment,
                    destroy_model_parallel,
                )

                destroy_model_parallel()
                destroy_distributed_environment()
            except Exception as exc:  # noqa: BLE001 - helpers vary across vLLM releases
                logger.debug("vLLM cleanup helpers were unavailable or already closed: %s", exc)
            gc.collect()
            try:
                import torch

                torch.cuda.empty_cache()
            except (ImportError, RuntimeError):
                pass

    @staticmethod
    def _init_vllm(model_path, max_context, temperature, top_p,
                   gpu_memory_utilization, tensor_parallel_size, revision):
        from vllm import LLM, SamplingParams

        llm = LLM(
            model=model_path,
            max_model_len=max_context,
            gpu_memory_utilization=gpu_memory_utilization,
            tensor_parallel_size=tensor_parallel_size,
            trust_remote_code=True,
            revision=revision,
        )
        sp = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=2048,
            stop=None,
        )
        return llm, sp

    @staticmethod
    def _parse(text: str) -> QueryGenerationOutput:
        """Extract the `{"queries": [...]}` payload from raw model output."""
        if not text:
            return QueryGenerationOutput([], text, parsed_ok=False, error="empty output")

        # The model is fine-tuned to emit JSON, but it sometimes wraps it in
        # markdown code fences. Strip those defensively.
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # Find the outermost {...} block.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return QueryGenerationOutput([], text, parsed_ok=False, error="no JSON object found")

        try:
            obj = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            return QueryGenerationOutput([], text, parsed_ok=False, error=f"json decode: {e}")

        queries = obj.get("queries")
        if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            return QueryGenerationOutput(
                [], text, parsed_ok=False, error="`queries` must be list[str]",
            )
        if not queries:
            return QueryGenerationOutput(
                [], text, parsed_ok=False, error="empty `queries` list",
            )
        if "reachableByFlows" not in queries[-1]:
            return QueryGenerationOutput(
                [], text, parsed_ok=False,
                error="final query must use reachableByFlows",
            )

        return QueryGenerationOutput(queries=queries, raw_text=text, parsed_ok=True)

    @staticmethod
    def _dummy_response(_: str) -> str:
        """Test stub. Returns a plausible UAF-style query bundle."""
        return json.dumps({
            "queries": [
                'val source = cpg.identifier.name("buf").l',
                'val sink = cpg.call.name("memcpy").l',
                "val execution_path = sink.reachableByFlows(source).l",
            ]
        })
