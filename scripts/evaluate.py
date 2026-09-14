"""Evaluate a trained pipeline on a labelled test set.

Reproduces the table layouts from the paper:
  - overall metrics (Tables 3, 5, 7)
  - per-CWE breakdown (Tables 4, 8)
  - reduction-ratio statistics (§4.3.1)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from llmxcpg.config import Config, JoernConfig, ModelConfig, DEFAULT_THRESHOLDS
from llmxcpg.evaluation.metrics import (
    classification_metrics, metrics_by_cwe, reduction_ratio_stats,
)
from llmxcpg.inference.pipeline import LLMxCPGPipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-model", required=True)
    parser.add_argument("--detector-model", required=True)
    parser.add_argument("--test-data", required=True,
                        help="JSONL with {'code', 'label', 'cwe'} per row.")
    parser.add_argument("--joern-host", default="localhost")
    parser.add_argument("--joern-port", type=int, default=8080)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--dataset", choices=list(DEFAULT_THRESHOLDS), default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--failure-policy", choices=("exclude", "safe", "vulnerable", "error"),
        default="exclude", help="How pipeline abstentions affect classification metrics.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    threshold = (
        args.threshold
        if args.threshold is not None
        else (DEFAULT_THRESHOLDS[args.dataset] if args.dataset else 0.5)
    )

    cfg = Config(
        joern=JoernConfig(host=args.joern_host, port=args.joern_port),
        models=ModelConfig(
            query_model_path=args.query_model,
            detector_model_path=args.detector_model,
        ),
        threshold=threshold,
    )
    pipeline = LLMxCPGPipeline.from_config(cfg)

    records = [json.loads(l) for l in Path(args.test_data).read_text().splitlines() if l.strip()]

    predictions: list[bool | None] = []
    labels: list[int] = []
    cwes: list[str] = []
    original_lengths: list[int] = []
    slice_lengths: list[int] = []
    failures = {"query_parse": 0, "slice": 0}

    results = pipeline.detect_batch([r["code"] for r in records], threshold=threshold)
    for r, result in zip(records, results):
        predictions.append(result.is_vulnerable)
        labels.append(int(r["label"]))
        cwes.append(r.get("cwe", "UNKNOWN"))
        if result.slice:
            original_lengths.append(len(r["code"].splitlines()))
            slice_lengths.append(len(result.slice.code.splitlines()))
        if result.failure_stage:
            failures[result.failure_stage] += 1

    overall = classification_metrics(
        predictions, labels, failure_policy=args.failure_policy,
    )
    per_cwe = {
        k: v.as_dict()
        for k, v in metrics_by_cwe(
            predictions, labels, cwes, failure_policy=args.failure_policy,
        ).items()
    }
    reduction = reduction_ratio_stats(original_lengths, slice_lengths)

    report = {
        "threshold": threshold,
        "failure_policy": args.failure_policy,
        "overall": overall.as_dict(),
        "per_cwe": per_cwe,
        "reduction_ratio": reduction,
        "failures": failures,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))

    # Pretty print
    print("=" * 60)
    print(f"Overall (γ={threshold:.3f})")
    print("=" * 60)
    for k, v in overall.as_dict().items():
        print(f"  {k:14s}: {v}")
    print(f"\nFailures: {failures}")
    print(f"Slice reduction (mean): {reduction['mean_reduction']*100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
