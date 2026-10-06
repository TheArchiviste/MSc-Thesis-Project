"""Command line entry point: python -m evidence_experiment ..."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .analysis import analyze
from .calibrate import calibrate
from .calibration_runner import score_and_calibrate
from .locks import (
    git_provenance,
    lock_detector,
    lock_inputs,
    require_calibration,
    require_witnesses,
)
from .review import build_queue, claim_problem, write_queue
from .runner import classify_slices, extract_slices, generate_queries, load_config
from .schema import load_cases, read_jsonl
from .validate import validate_witnesses

# Backwards-compatible names for callers and tests.
_lock_inputs = lock_inputs
_lock_detector = lock_detector
_require_witnesses = require_witnesses
_require_calibration = require_calibration


def _sha256(path: Path | None) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else None




def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate source-to-evidence retrieval")
    parser.add_argument("phase", choices=("verify", "calibrate", "score-calibration", "validate",
                                          "query", "slice", "detect", "packets", "analyze", "all"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--assessments", type=Path)
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--resolutions", type=Path)
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("--witness-plan", type=Path)
    parser.add_argument("--calibration-scores", type=Path)
    parser.add_argument("--calibration-manifest", type=Path)
    parser.add_argument("--calibration", type=Path,
                        help="calibration.json from score-calibration (default: WORK/calibration.json)")
    parser.add_argument("--duplicate-fraction", type=float, default=0.0,
                        help="packets: share of evidence packets re-issued as disguised duplicates")
    parser.add_argument("--review-seed", type=int, default=0,
                        help="packets: seed for duplicate selection and line offsets")
    parser.add_argument("--analysis-seed", type=int, default=0,
                        help="analyze: seed for the bootstrap and one-case-per-cluster selection")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    cases = load_cases(args.manifest)
    args.work.mkdir(parents=True, exist_ok=True)
    if args.phase == "verify":
        print(json.dumps({"cases": len(cases), "clusters": len({c.cluster_id for c in cases}),
                          "admissible_pairs": sum(c.admissible for c in cases),
                          "fixed_variant_decoys": sum("F" in c.sources for c in cases),
                          "claim_problems": {c.case_id: claim_problem(c.referent) for c in cases
                                             if claim_problem(c.referent)},
                          "validation_failures": dict(Counter(
                              k for c in cases for k, v in c.validation.items() if v != "pass"))},
                         indent=2))
        return
    if args.phase == "calibrate":
        if not args.calibration_scores:
            parser.error("calibrate requires --calibration-scores")
        if (args.work / "detector_lock.json").exists():
            parser.error("D has already run; use a new --work directory for recalibration")
        result = calibrate(read_jsonl(args.calibration_scores), {c.cluster_id for c in cases})
        path = args.work / "calibration.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(path)
        return
    if args.phase == "score-calibration":
        if not args.config or not args.calibration_manifest:
            parser.error("score-calibration needs --config and --calibration-manifest")
        if (args.work / "detector_lock.json").exists():
            parser.error("D has already run in this --work directory; calibrate in its own directory")
        result = score_and_calibrate(cases, args.calibration_manifest, args.work,
                                     load_config(args.config, require_threshold=False))
        result["analysis_manifest_sha256"] = _sha256(args.manifest)
        result["provenance"] = git_provenance()
        (args.work / "calibration.json").write_text(json.dumps(result, indent=2) + "\n",
                                                     encoding="utf-8")
        print(args.work / "calibration.json")
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
    cfg = load_config(args.config, require_detector=args.phase in ("all", "detect"))
    if args.phase in ("packets", "analyze") and not cfg.get("allow_dummy", False):
        problems = {c.case_id: claim_problem(c.referent) for c in cases if claim_problem(c.referent)}
        if problems:
            raise ValueError(f"Templated review_claim required for blind review: {problems}")
    lock_inputs(args.work, args.manifest, args.config, cases, args.repeats, phase=args.phase)
    require_witnesses(args.work, cases)
    calibration = args.calibration or args.work / "calibration.json"
    if args.phase in ("all", "detect"):
        require_calibration(calibration, cfg, args.manifest)
        lock_detector(args.work, args.config, calibration)
    if args.phase in ("all", "query"):
        generate_queries(cases, args.work, cfg, args.repeats)
    if args.phase in ("all", "slice"):
        extract_slices(cases, args.work, cfg, args.repeats)
    if args.phase in ("all", "detect"):
        classify_slices(cases, args.work, cfg, args.repeats)
    if args.phase == "packets":
        packets, key = build_queue(cases, args.work, args.repeats,
                                   duplicate_fraction=args.duplicate_fraction,
                                   seed=args.review_seed)
        settings = {"duplicate_fraction": args.duplicate_fraction, "seed": args.review_seed,
                    "repeats": args.repeats}
        print(write_queue(args.work, packets, key, settings))
    if args.phase == "analyze":
        if not args.assessments or not args.adjudications:
            parser.error("analyze requires --assessments and --adjudications")
        report = analyze(cases, args.work, args.assessments, args.adjudications,
                         repeats=args.repeats, seed=args.analysis_seed,
                         resolutions=args.resolutions, evidence_only=args.evidence_only)
        report["analysis_provenance"] = {
            "analysis_sha256": _sha256(Path(__file__).with_name("analysis.py")),
            "review_sha256": _sha256(Path(__file__).with_name("review.py")),
            "assessments_sha256": _sha256(args.assessments),
            "adjudications_sha256": _sha256(args.adjudications),
            "resolutions_sha256": _sha256(args.resolutions),
            "review_key_sha256": _sha256(args.work / "review_key.jsonl"),
            "analysis_seed": args.analysis_seed,
            "checkout": git_provenance(),
        }
        path = args.work / "analysis.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
