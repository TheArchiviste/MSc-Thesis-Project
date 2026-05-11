"""Convert bootstrap output and slicing output into LLaMA-Factory training formats.

LLaMA-Factory accepts a `sharegpt`-style or `alpaca`-style JSONL. We use the
`alpaca` format because both LLMxCPG-Q and LLMxCPG-D are single-turn
instruction-following:
    {"instruction": "...", "input": "", "output": "..."}

For LLMxCPG-Q, the output is `{"queries": [...]}`.
For LLMxCPG-D, the output is the literal word "VULNERABLE" or "SAFE".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from llmxcpg.prompts import render_query_prompt, render_detection_prompt


logger = logging.getLogger(__name__)


def build_q_training_set(
    bootstrap_jsonl: str | Path,
    output_path: str | Path,
) -> int:
    """Convert bootstrap output → alpaca JSONL for fine-tuning Q."""
    bootstrap_jsonl = Path(bootstrap_jsonl)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with bootstrap_jsonl.open() as fin, output_path.open("w") as fout:
        for line in fin:
            rec = json.loads(line)
            instruction = render_query_prompt(rec["code"])
            output = json.dumps({"queries": rec["queries"]}, ensure_ascii=False)
            fout.write(json.dumps({
                "instruction": instruction,
                "input": "",
                "output": output,
            }) + "\n")
            n += 1
    logger.info("Wrote %d Q training records to %s", n, output_path)
    return n


def build_d_training_set(
    sliced_samples: Iterable[dict],
    output_path: str | Path,
) -> int:
    """Convert sliced + labelled samples → alpaca JSONL for fine-tuning D.

    Each sample dict must have:
      - `slice` (str): the reconstructed slice produced by Q + Joern.
      - `is_vulnerable` (bool)
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with output_path.open("w") as fout:
        for s in sliced_samples:
            slice_code = s.get("slice")
            if not slice_code:
                continue
            instruction = render_detection_prompt(slice_code)
            output = "VULNERABLE" if s.get("is_vulnerable") else "SAFE"
            fout.write(json.dumps({
                "instruction": instruction,
                "input": "",
                "output": output,
            }) + "\n")
            n += 1
    logger.info("Wrote %d D training records to %s", n, output_path)
    return n
