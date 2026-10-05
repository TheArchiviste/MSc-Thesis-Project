"""Command line entry point: python -m evidence_experiment ..."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .analysis import analyze
from .calibrate import calibrate
from .runner import (
    classify_slices,
    extract_slices,
    generate_queries,
    load_config,
    review_packets,
)
from .schema import digest, index_jsonl, load_cases, read_jsonl
from .validate import validate_witnesses


def _lock_inputs(work: Path, manifest: Path, config: Path, cases) -> None:
    """Refuse phase reuse after manifest, configuration or harness code changes."""
    h = hashlib.sha256()
    for path in (manifest, config, Path(__file__), Path(__file__).with_name("runner.py"),
                 Path(__file__).with_name("schema.py"), Path(__file__).with_name("analysis.py")):
        h.update(path.read_bytes())
    for case in cases:
        for arm, source in sorted(case.sources.items()):
            h.update(case.case_id.encode("utf-8"))
            h.update(arm.encode("utf-8"))
            h.update(source.encode("utf-8"))
    for evidence in (work / "calibration.json", work / "witness_validation.jsonl"):
        if evidence.exists():
            h.update(evidence.read_bytes())
    fingerprint = h.hexdigest()
    lock = work / "experiment_lock.json"
    if lock.exists():
        if json.loads(lock.read_text(encoding="utf-8"))["fingerprint"] != fingerprint:
            raise ValueError("Inputs or code changed; use a new --work directory for a new run")
    else:
        lock.write_text(json.dumps({"fingerprint": fingerprint,
                                    "manifest": str(manifest.resolve()),
                                    "config": str(config.resolve())}, indent=2) + "\n",
                        encoding="utf-8")


def _require_witnesses(work: Path, cases) -> None:
    if not any(c.admissible for c in cases):
        return
    checks = index_jsonl(work / "witness_validation.jsonl", "case_id")
    for case in cases:
        if case.admissible and (case.case_id not in checks or
                                any(checks[case.case_id]["checks"].get(k) != "pass"
                                    for k in ("compile", "trigger", "benign_behavior")) or
                                checks[case.case_id].get("source_sha256") !=
                                {arm: digest(case.sources[arm]) for arm in ("U", "TM", "TN")}):
            raise ValueError(f"Missing or failed executable witness checks for {case.case_id}")


def _require_calibration(work: Path, cfg: dict) -> None:
    if cfg.get("allow_dummy", False):
        return
    path = work / "calibration.json"
    if not path.exists():
        raise ValueError("Run calibrate on disjoint data before model phases")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not result["usability_gate_pass"] or abs(result["threshold"] - cfg["threshold"]) > 1e-9:
        raise ValueError("Usability gate failed or configured threshold differs from calibration")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate source-to-evidence retrieval")
    parser.add_argument("phase", choices=("verify", "calibrate", "validate", "query", "slice", "detect", "packets",
                                          "analyze", "all"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--witness-plan", type=Path)
    parser.add_argument("--calibration-scores", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    cases = load_cases(args.manifest)
    args.work.mkdir(parents=True, exist_ok=True)
    if args.phase == "verify":
        print(json.dumps({"cases": len(cases), "clusters": len({c.cluster_id for c in cases}),
                          "admissible_pairs": sum(c.admissible for c in cases),
                          "validation_failures": dict(Counter(
                              k for c in cases for k, v in c.validation.items() if v != "pass"))},
                         indent=2))
        return
    if args.phase == "calibrate":
        if not args.calibration_scores:
            parser.error("calibrate requires --calibration-scores")
        result = calibrate(read_jsonl(args.calibration_scores), {c.cluster_id for c in cases})
        path = args.work / "calibration.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(path)
        return
    if args.phase == "validate":
        if not args.witness_plan:
            parser.error("validate requires --witness-plan")
        path = args.work / "witness_validation.jsonl"
        if path.exists():
            parser.error("validation output already exists; use a fresh --work directory")
        validate_witnesses(cases, args.manifest, args.witness_plan, path)
        print(path)
        return
    if not args.config:
        parser.error("all phases except verify require --config")
    cfg = load_config(args.config) if args.phase in ("all", "query", "slice", "detect") else None
    _lock_inputs(args.work, args.manifest, args.config, cases)
    _require_witnesses(args.work, cases)
    if cfg is not None:
        _require_calibration(args.work, cfg)
    if args.phase in ("all", "query"):
        generate_queries(cases, args.work, cfg, args.repeats)
    if args.phase in ("all", "slice"):
        extract_slices(cases, args.work, cfg, args.repeats)
    if args.phase in ("all", "detect"):
        classify_slices(cases, args.work, cfg, args.repeats)
    if args.phase == "packets":
        path = args.work / "blind_review_packets.jsonl"
        with path.open("w", encoding="utf-8") as stream:
            for packet in review_packets(cases, args.work, args.repeats):
                stream.write(json.dumps(packet, ensure_ascii=False) + "\n")
        print(path)
    if args.phase == "analyze":
        if not args.assessments or not args.adjudications:
            parser.error("analyze requires --assessments and --adjudications")
        report = analyze(cases, args.work, args.assessments, args.adjudications,
                         repeats=args.repeats)
        path = args.work / "analysis.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
