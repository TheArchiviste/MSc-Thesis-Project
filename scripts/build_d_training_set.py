"""Build the D-model training set.

After Q is fine-tuned, run it over the labelled training corpus to produce
slices, then pair each slice with its ground-truth label. That's what
LLMxCPG-D is fine-tuned on (paper §3.3).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from llmxcpg.config import Config, JoernConfig, ModelConfig
from llmxcpg.data.prepare import build_d_training_set
from llmxcpg.data.loaders import load_primevul, load_formai_v2
from llmxcpg.inference.pipeline import LLMxCPGPipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q-model", required=True,
                        help="Path or HF repo for the fine-tuned LLMxCPG-Q.")
    parser.add_argument("--detector-model", required=True,
                        help="Detector path. Pipeline will load it but the slicing "
                             "stage can be done without — we just need a valid model "
                             "object. For pure slice production you can stub D out.")
    parser.add_argument("--dataset", required=True, choices=("primevul", "formai"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--joern-host", default="localhost")
    parser.add_argument("--joern-port", type=int, default=8080)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    loader = {"primevul": load_primevul, "formai": load_formai_v2}[args.dataset]
    samples = list(loader(args.input))

    cfg = Config(
        joern=JoernConfig(host=args.joern_host, port=args.joern_port),
        models=ModelConfig(
            query_model_path=args.q_model,
            detector_model_path=args.detector_model,
        ),
    )
    pipeline = LLMxCPGPipeline.from_config(cfg)

    sliced = []
    for s in samples:
        result = pipeline.detect(s["code"])
        if result.slice is None:
            continue
        sliced.append({
            "id": s["id"],
            "slice": result.slice.code,
            "is_vulnerable": s["is_vulnerable"],
            "cwe": s["cwe"],
        })

    n = build_d_training_set(sliced, args.out)
    print(f"Wrote {n} D training records (from {len(samples)} samples; "
          f"{len(samples) - n} discarded due to slicing failures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
