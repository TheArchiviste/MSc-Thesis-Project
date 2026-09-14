"""Calibrate γ on a small labelled sample, per the paper's recommendation.

Usage:
    python scripts/calibrate_threshold.py \
        --query-model checkpoints/llmxcpg-q \
        --detector-model checkpoints/llmxcpg-d \
        --validation /path/to/validation.jsonl \
        --n 20 \
        --out calibrated_threshold.json
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

from llmxcpg.config import Config, JoernConfig, ModelConfig
from llmxcpg.calibration.threshold import calibrate_threshold
from llmxcpg.inference.pipeline import LLMxCPGPipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-model", required=True)
    parser.add_argument("--detector-model", required=True)
    parser.add_argument("--validation", required=True,
                        help="JSONL with {'code': ..., 'label': 0|1} fields.")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--joern-host", default="localhost")
    parser.add_argument("--joern-port", type=int, default=8080)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--optimise-for", choices=("accuracy", "f1"), default="accuracy")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")

    rng = random.Random(args.seed)
    records = [json.loads(l) for l in Path(args.validation).read_text().splitlines() if l.strip()]
    rng.shuffle(records)
    sample = records[: args.n]

    cfg = Config(
        joern=JoernConfig(host=args.joern_host, port=args.joern_port),
        models=ModelConfig(
            query_model_path=args.query_model,
            detector_model_path=args.detector_model,
        ),
    )
    pipeline = LLMxCPGPipeline.from_config(cfg)

    probs: list[float] = []
    labels: list[int] = []
    results = pipeline.detect_batch([r["code"] for r in sample], threshold=0.5)
    for r, result in zip(sample, results):
        if result.probability_vulnerable is None:
            # A failed pipeline has no model probability and cannot calibrate
            # the detector. Report it as missing coverage instead of inventing 0.
            continue
        probs.append(result.probability_vulnerable)
        labels.append(int(r["label"]))

    if not probs:
        raise RuntimeError("Every calibration sample abstained; no threshold can be fitted.")

    cal = calibrate_threshold(probs, labels, optimise_for=args.optimise_for)
    out_path = Path(args.out)
    out_path.write_text(json.dumps({
        "best_threshold": cal.best_threshold,
        "best_accuracy": cal.best_accuracy,
        "best_f1": cal.best_f1,
        "n_samples": cal.n_samples,
        "n_positive": cal.n_positive,
        "n_negative": cal.n_negative,
        "is_balanced": cal.is_balanced,
        "attempted_samples": len(sample),
        "abstentions": len(sample) - len(probs),
        "coverage": len(probs) / len(sample) if sample else 0.0,
        "sweep": cal.sweep,
    }, indent=2))
    print(f"Best γ = {cal.best_threshold:.3f}  (acc={cal.best_accuracy:.3f}, f1={cal.best_f1:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
