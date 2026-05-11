"""LLMxCPG-Q: generate CPGQL queries from source code.

Backed by vLLM for high-throughput batch inference (the paper §4.2 specifies
vLLM for query inference).

The model returns a JSON object `{"queries": [...]}`. We parse it strictly
because anything else is a generation failure, and the bootstrap loop relies
on the parse failure mode being deterministic.
"""

from __future__ import annotations

import json
import logging
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
    """Wraps a vLLM `LLM` engine for CPGQL query generation.

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
    ) -> None:
        self.model_path = model_path
        self.max_context = max_context
        self.temperature = temperature
        self.top_p = top_p
        self._engine_kind = engine

        if engine == "vllm":
            self._llm, self._sampling_params = self._init_vllm(
                model_path, max_context, temperature, top_p,
                gpu_memory_utilization, tensor_parallel_size,
            )
        elif engine == "dummy":
            self._llm = None
            self._sampling_params = None
        else:
            raise ValueError(f"Unknown engine: {engine}")

    @classmethod
    def from_config(cls, cfg: ModelConfig, **kwargs) -> "QueryGenerator":
        return cls(
            model_path=cfg.query_model_path,
            max_context=cfg.query_max_context,
            temperature=cfg.query_temperature,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def generate(self, code: str) -> QueryGenerationOutput:
        """Generate CPGQL queries for one code sample."""
        prompt = render_query_prompt(code)
        text = self._raw_generate(prompt)
        return self._parse(text)

    def generate_batch(self, codes: list[str]) -> list[QueryGenerationOutput]:
        """Batched generation via vLLM, much faster than looping `generate`."""
        prompts = [render_query_prompt(c) for c in codes]
        if self._engine_kind == "dummy":
            return [self._parse(self._dummy_response(c)) for c in codes]

        # vLLM batch
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
        outs = self._llm.generate([prompt], self._sampling_params)
        return outs[0].outputs[0].text if outs and outs[0].outputs else ""

    @staticmethod
    def _init_vllm(model_path, max_context, temperature, top_p,
                   gpu_memory_utilization, tensor_parallel_size):
        from vllm import LLM, SamplingParams

        llm = LLM(
            model=model_path,
            max_model_len=max_context,
            gpu_memory_utilization=gpu_memory_utilization,
            tensor_parallel_size=tensor_parallel_size,
            trust_remote_code=True,
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
