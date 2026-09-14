"""Build the D-model training set.

After Q is fine-tuned, run it over the labelled training corpus to produce
slices, then pair each slice with its ground-truth label. That's what
LLMxCPG-D is fine-tuned on (paper §3.3).
"""

from __future__ import annotations

import argparse
import logging

from llmxcpg.config import Config, JoernConfig, ModelConfig
from llmxcpg.data.prepare import build_d_training_set
from llmxcpg.data.loaders import load_primevul, load_formai_v2
from llmxcpg.inference.query_generator import QueryGenerator
from llmxcpg.joern.client import JoernClient
from llmxcpg.slicing.extractor import SliceExtractor, SliceFailure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q-model", required=True,
                        help="Path or HF repo for the fine-tuned LLMxCPG-Q.")
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
        models=ModelConfig(query_model_path=args.q_model),
    )
    query_generator = QueryGenerator.from_config(cfg.models)
    joern = JoernClient(
        host=cfg.joern.host,
        port=cfg.joern.port,
        local_input_dir=cfg.joern.local_input_dir,
        server_input_dir=cfg.joern.server_input_dir,
    )
    slicer = SliceExtractor(joern)

    sliced = []
    try:
        query_outputs = query_generator.generate_batch([s["code"] for s in samples])
        for index, (s, query_output) in enumerate(zip(samples, query_outputs)):
            if not query_output.parsed_ok:
                continue
            try:
                result_slice = slicer.extract(
                    s["code"], query_output.queries, project_name=f"d_train_{index}",
                )
            except SliceFailure:
                logging.exception("Slicing failed for sample %s", s.get("id", index))
                continue
            sliced.append({
                "id": s["id"],
                "slice": result_slice.code,
                "is_vulnerable": s["is_vulnerable"],
                "cwe": s["cwe"],
            })
    finally:
        query_generator.close()
        try:
            joern.reset()
        except Exception as exc:
            logging.warning("Joern cleanup failed: %s", exc)

    n = build_d_training_set(sliced, args.out)
    print(f"Wrote {n} D training records (from {len(samples)} samples; "
          f"{len(samples) - n} discarded due to slicing failures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
