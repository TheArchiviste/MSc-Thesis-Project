"""Command-line entry point for end-to-end LLMxCPG inference."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from llmxcpg.config import Config, DEFAULT_THRESHOLDS, JoernConfig, ModelConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LLMxCPG on a C/C++ input.")
    parser.add_argument("--code", required=True, help="Code file, or '-' for stdin.")
    parser.add_argument("--query-model", default="QCRI/LLMxCPG-Q")
    parser.add_argument("--detector-model", default="QCRI/LLMxCPG-D")
    parser.add_argument("--query-revision", help="Exact Hugging Face revision/commit.")
    parser.add_argument("--detector-revision", help="Exact Hugging Face revision/commit.")
    parser.add_argument("--query-engine", choices=("vllm", "openai", "dummy"),
                        default="vllm")
    parser.add_argument("--query-base-url",
                        help="OpenAI-compatible endpoint, e.g. http://localhost:8000/v1.")
    parser.add_argument("--query-api-key-env", default="LLMXCPG_QUERY_API_KEY")
    parser.add_argument("--query-gpu-memory-utilization", type=float, default=0.85)
    parser.add_argument("--query-tensor-parallel-size", type=int, default=1)
    parser.add_argument("--retain-query-model", action="store_true",
                        help="Keep local Q loaded when D starts (requires enough aggregate GPU RAM).")
    parser.add_argument("--joern-host", default="localhost")
    parser.add_argument("--joern-port", type=int, default=8080)
    parser.add_argument("--work-dir", default="./work")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Binary decision threshold; overrides --dataset.")
    parser.add_argument("--dataset", choices=list(DEFAULT_THRESHOLDS), default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from llmxcpg.inference.pipeline import LLMxCPGPipeline

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")

    source = sys.stdin.read() if args.code == "-" else Path(args.code).read_text()
    threshold = (
        args.threshold
        if args.threshold is not None
        else (DEFAULT_THRESHOLDS[args.dataset] if args.dataset else 0.5)
    )

    config = Config(
        joern=JoernConfig(host=args.joern_host, port=args.joern_port),
        models=ModelConfig(
            query_model_path=args.query_model,
            query_model_revision=args.query_revision,
            detector_model_path=args.detector_model,
            detector_model_revision=args.detector_revision,
            query_engine=args.query_engine,
            query_base_url=args.query_base_url,
            query_api_key_env=args.query_api_key_env,
            query_gpu_memory_utilization=args.query_gpu_memory_utilization,
            query_tensor_parallel_size=args.query_tensor_parallel_size,
            release_local_query_model_before_detection=not args.retain_query_model,
        ),
        work_dir=Path(args.work_dir),
        threshold=threshold,
    )
    result = LLMxCPGPipeline.from_config(config).detect(source, threshold=threshold)

    if args.json:
        print(json.dumps({
            "is_vulnerable": result.is_vulnerable,
            "probability_vulnerable": result.probability_vulnerable,
            "probability_safe": result.probability_safe,
            "threshold": result.threshold,
            "failure_stage": result.failure_stage,
            "failure_reason": result.failure_reason,
            "queries": (result.query_output.queries
                        if result.query_output and result.query_output.parsed_ok else None),
            "slice": result.slice.code if result.slice else None,
            "reduction_ratio": result.slice.reduction_ratio if result.slice else None,
        }, indent=2))
        return 0 if result.succeeded else 2

    print("=" * 70)
    print("LLMxCPG verdict")
    print("=" * 70)
    if not result.succeeded:
        print(f"  FAILED at stage: {result.failure_stage}")
        print(f"  Reason: {result.failure_reason}")
        return 2

    print(f"  Verdict:       {'VULNERABLE' if result.is_vulnerable else 'SAFE'}")
    print(f"  P(vulnerable): {result.probability_vulnerable:.4f}")
    print(f"  Threshold γ:   {result.threshold:.4f}")
    if result.slice:
        print(f"  Slice reduction: {result.slice.reduction_ratio * 100:.1f}%")
        print("\n--- Generated CPGQL queries ---")
        for query in result.query_output.queries:
            print(f"  • {query}")
        print("\n--- Reconstructed slice ---")
        print(result.slice.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
