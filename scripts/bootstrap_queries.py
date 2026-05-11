"""Bootstrap CPGQL training data via DeepSeek-v3 with iterative correction.

This populates `data/q_train.jsonl` for fine-tuning LLMxCPG-Q.

Usage:
    export DEEPSEEK_API_KEY=...
    python scripts/bootstrap_queries.py \
        --dataset primevul \
        --input /path/to/primevul/train.jsonl \
        --out data/q_train.jsonl \
        --joern-host localhost --joern-port 8080
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from llmxcpg.config import SUPPORTED_CWES
from llmxcpg.data.bootstrap import bootstrap_query_dataset, DeepSeekQueryProposer
from llmxcpg.data.loaders import (
    load_formai_v2, load_primevul, load_sven, load_reposvul,
)
from llmxcpg.joern.client import JoernClient


LOADERS = {
    "formai": load_formai_v2,
    "primevul": load_primevul,
    "sven": load_sven,
    "reposvul": load_reposvul,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, choices=list(LOADERS))
    parser.add_argument("--input", required=True,
                        help="Path to dataset file/directory.")
    parser.add_argument("--out", required=True, help="Output JSONL path.")
    parser.add_argument("--joern-host", default="localhost")
    parser.add_argument("--joern-port", type=int, default=8080)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N samples (for smoke tests).")
    parser.add_argument("--vulnerable-only", action="store_true",
                        help="Only bootstrap from labelled-vulnerable samples. "
                             "Safe samples don't need queries that find paths.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")

    samples = LOADERS[args.dataset](args.input)

    def filtered():
        n = 0
        for s in samples:
            if s["cwe"] not in SUPPORTED_CWES:
                continue
            if args.vulnerable_only and not s["is_vulnerable"]:
                continue
            yield s
            n += 1
            if args.limit is not None and n >= args.limit:
                break

    proposer = DeepSeekQueryProposer()
    with JoernClient(host=args.joern_host, port=args.joern_port) as joern:
        summary = bootstrap_query_dataset(
            samples=filtered(),
            joern=joern,
            proposer=proposer,
            output_path=args.out,
            max_retries=args.max_retries,
            require_non_empty_path=True,
        )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
