"""The released pretrained Q checkpoint, with explicit local vLLM settings."""
from __future__ import annotations

import gc
import json
import re
from dataclasses import dataclass

from llmxcpg.config import ModelConfig
from llmxcpg.prompts import render_query_prompt


@dataclass
class QueryGenerationOutput:
    queries: list[str]
    raw_text: str
    parsed_ok: bool
    error: str | None = None
    finish_reason: str | None = None
    output_tokens: int | None = None


class QueryGenerator:
    """One local vLLM model; GPU imports happen only at construction."""

    def __init__(self, model_path, max_context=8192, temperature=0.0,
                 gpu_memory_utilization=0.85, tensor_parallel_size=1, revision=None):
        from vllm import LLM, SamplingParams
        self.max_context = max_context
        self._llm = LLM(model=model_path, revision=revision, tokenizer_revision=revision,
                        max_model_len=max_context, gpu_memory_utilization=gpu_memory_utilization,
                        tensor_parallel_size=tensor_parallel_size, trust_remote_code=False,
                        dtype="bfloat16", seed=0)
        self._sampling_params = SamplingParams(temperature=temperature, top_p=1.0,
                                               max_tokens=2048, seed=0)

    @classmethod
    def from_config(cls, cfg: ModelConfig):
        return cls(cfg.query_model_path, cfg.query_max_context, cfg.query_temperature,
                   cfg.query_gpu_memory_utilization, cfg.query_tensor_parallel_size,
                   cfg.query_model_revision)

    def _format_vllm_prompt(self, prompt):
        tokenizer = self._llm.get_tokenizer()
        if not getattr(tokenizer, "chat_template", None):
            raise ValueError("The pinned Q tokenizer must have its chat template")
        return tokenizer.apply_chat_template([{"role": "user", "content": prompt}],
                                              tokenize=False, add_generation_prompt=True)

    def generate_batch(self, codes):
        if self._llm is None:
            raise RuntimeError("The Q engine is closed")
        prompts = [self._format_vllm_prompt(render_query_prompt(code)) for code in codes]
        outputs = self._llm.generate(prompts, self._sampling_params)
        result = []
        for output in outputs:
            completion = output.outputs[0] if output.outputs else None
            row = self._parse(completion.text if completion else "")
            if completion:
                row.finish_reason = completion.finish_reason
                row.output_tokens = len(completion.token_ids)
            result.append(row)
        return result

    def close(self):
        engine, self._llm = self._llm, None
        if engine is None:
            return
        executor = getattr(getattr(engine, "llm_engine", None), "model_executor", None)
        shutdown = getattr(executor, "shutdown", None)
        if callable(shutdown):
            shutdown()
        del engine
        from vllm.distributed.parallel_state import (
            destroy_distributed_environment,
            destroy_model_parallel,
        )
        destroy_model_parallel()
        destroy_distributed_environment()
        gc.collect()
        import torch
        torch.cuda.empty_cache()

    @staticmethod
    def _parse(text):
        def failed(reason):
            return QueryGenerationOutput([], text, False, reason)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return failed("no JSON object found")
        try:
            obj = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            return failed(f"json decode: {exc}")
        queries = obj.get("queries") if isinstance(obj, dict) else None
        if not isinstance(queries, list) or not queries or any(
                not isinstance(q, str) or not q.strip() for q in queries):
            return failed("queries must be a nonempty list of nonempty strings")
        if "reachableByFlows" not in queries[-1]:
            return failed("final query must use reachableByFlows")
        return QueryGenerationOutput(queries, text, True)
