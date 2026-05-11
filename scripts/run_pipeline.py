"""Run the full LLMxCPG pipeline on a code file or string.

Usage:
    python scripts/run_pipeline.py \
        --code examples/cve_2011_3359.c \
        --query-model qcri/llmxcpg-q \
        --detector-model qcri/llmxcpg-d \
        --threshold 0.594

Prints structured output: query, slice, probability, verdict.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from llmxcpg.config import Config, JoernConfig, ModelConfig, DEFAULT_THRESHOLDS
from llmxcpg.inference.pipeline import LLMxCPGPipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True,
                        help="Path to a code file, or '-' to read from stdin")
    parser.add_argument("--query-model", required=True)
    parser.add_argument("--detector-model", required=True)
    parser.add_argument("--joern-host", default="localhost")
    parser.add_argument("--joern-port", type=int, default=8080)
    parser.add_argument("--threshold", type=float, default=None,
                        help="γ for the binary decision. If omitted and "
                             "--dataset is given, uses the per-dataset default.")
    parser.add_argument("--dataset", choices=list(DEFAULT_THRESHOLDS.keys()), default=None)
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of human text")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")

    if args.code == "-":
        source = sys.stdin.read()
    else:
        source = Path(args.code).read_text()

    threshold = args.threshold
    if threshold is None and args.dataset:
        threshold = DEFAULT_THRESHOLDS[args.dataset]
    if threshold is None:
        threshold = 0.5

    cfg = Config(
        joern=JoernConfig(host=args.joern_host, port=args.joern_port),
        models=ModelConfig(
            query_model_path=args.query_model,
            detector_model_path=args.detector_model,
        ),
        threshold=threshold,
    )
    pipeline = LLMxCPGPipeline.from_config(cfg)
    result = pipeline.detect(source, threshold=threshold)

    if args.json:
        out = {
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
        }
        print(json.dumps(out, indent=2))
        return 0

    # Human-readable output
    print("=" * 70)
    print("LLMxCPG verdict")
    print("=" * 70)
    if not result.succeeded:
        print(f"  FAILED at stage: {result.failure_stage}")
        print(f"  Reason: {result.failure_reason}")
        return 2

    label = "VULNERABLE" if result.is_vulnerable else "SAFE"
    print(f"  Verdict:       {label}")
    print(f"  P(vulnerable): {result.probability_vulnerable:.4f}")
    print(f"  Threshold γ:   {result.threshold:.4f}")
    if result.slice:
        print(f"  Slice reduction: {result.slice.reduction_ratio*100:.1f}%")
        print()
        print("--- Generated CPGQL queries ---")
        for q in result.query_output.queries:
            print(f"  • {q}")
        print()
        print("--- Reconstructed slice ---")
        print(result.slice.code)
    return 0 if result.is_vulnerable is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
