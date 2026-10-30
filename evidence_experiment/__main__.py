"""Acquire and report RQ1 only, with one primary U and F run per case."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .locks import (
    check_stage_receipts,
    lock_inputs,
    validate_terminal_records,
    work_lock,
    write_stage_receipt,
)
from .schema import load_cases


def main():
    from rq1.setup import CORPUS, DEFAULT_CONFIG, ROOT, check_acquisition_ready
    os.chdir(ROOT)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("query", "slice", "packets", "analyze", "finalize"))
    p.add_argument("--split", choices=("development", "main"), default="development")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--work", type=Path)
    args = p.parse_args()
    manifest = CORPUS / f"{args.split}.jsonl"
    cases = load_cases(manifest)
    work = args.work or Path("work/rq1-v6") / args.split
    with work_lock(work):
        cfg = check_acquisition_ready(manifest, args.config, phase=args.phase)
        lock_inputs(work, manifest, args.config, cases, phase=args.phase)
        check_stage_receipts(work)
        if args.phase == "query":
            from .runner import generate_queries
            generate_queries(cases, work, cfg)
            write_stage_receipt(work, "query", cases)
        elif args.phase == "slice":
            from .runner import extract_slices
            validate_terminal_records(work, "query", cases)
            receipts = json.loads((work / "stage_receipts.json").read_text())
            if "query" not in receipts:
                raise ValueError("Complete the receipted Q stage first")
            extract_slices(cases, work, cfg)
            write_stage_receipt(work, "slice", cases)
        else:
            for stage in ("query", "slice"):
                validate_terminal_records(work, stage, cases)
            if args.phase == "packets":
                from .review import build_queue
                build_queue(cases, work)
            else:
                from .analysis import analyze
                report = analyze(cases, work)
                print(json.dumps({"completion": report["completion"], "rq1": report["rq1"]}, indent=2))
                if args.phase == "finalize" and report["completion"] != "complete":
                    raise SystemExit("PROVISIONAL: complete the frozen 25% reassessment after at least 48 hours")
    print(f"RQ1_{args.phase.upper()}_OK: {len(cases) * 2} expected primary U/F inputs; {work}")


if __name__ == "__main__":
    main()
