"""Acquire and report RQ1 only, with one primary U and F run per case."""
from __future__ import annotations

import argparse
import json
import os
import traceback
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
    p.add_argument("phase", choices=("query", "slice", "release", "visibility", "packets", "analyze", "finalize"))
    p.add_argument("--split", choices=("development", "main"), default="development")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--work", type=Path)
    p.add_argument('--sealed', action='store_true', help='Capture acquisition logs and keep outputs unopened until assessment release')
    args = p.parse_args()
    if args.phase in {'query', 'slice'} and not args.sealed:
        p.error('Use --sealed for Q/Joern acquisition; release is a separate calibrated checkpoint')
    if args.sealed and args.phase not in {'query', 'slice', 'visibility'}:
        p.error('--sealed applies only to acquisition or structural visibility computation')
    manifest = CORPUS / f"{args.split}.jsonl"
    cases = load_cases(manifest)
    work = args.work or Path("work/rq1-v7") / args.split
    from rq1.sealing import private_log, release, require_release, seal, verify_seal

    def execute_phase():
        cfg = check_acquisition_ready(manifest, args.config, phase=args.phase, sealed=args.sealed)
        lock_inputs(work, manifest, args.config, cases, phase=args.phase)
        check_stage_receipts(work)
        if args.phase == 'release':
            release(work, cfg, main=args.split == 'main')
        elif args.phase == 'visibility':
            from rq1.visibility import compute
            compute(cases, work, sealed=args.sealed)
        elif args.phase == "query":
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
            require_release(work)
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
    with work_lock(work):
        if args.sealed:
            if args.phase in {'query', 'slice'} and (work / f'{args.phase}.seal.json').exists():
                verify_seal(work, args.phase)
                print(f'RQ1_{args.phase.upper()}_ALREADY_SEALED: no execution repeated')
                return
            log = work / f'{args.phase}.sealed.log'
            try:
                with private_log(log):
                    execute_phase()
                if args.phase in {'query', 'slice'}:
                    seal(work, args.phase, cases)
            except Exception as exc:  # noqa: BLE001 - diagnostics stay sealed; never print generated content
                with log.open('a') as stream:
                    traceback.print_exc(file=stream)
                print(f'RQ1_SEALED_ACQUISITION_BLOCKED: {type(exc).__name__}; preserve {work}; do not open logs before the diagnostic decision')
                raise SystemExit(1) from None
        else:
            execute_phase()
    print(f"RQ1_{args.phase.upper()}_OK: {len(cases) * 2} expected primary U/F inputs; {work}")


if __name__ == "__main__":
    main()
