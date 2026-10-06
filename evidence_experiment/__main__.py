"""Command line entry point: python -m evidence_experiment ..."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from collections import Counter
from pathlib import Path

from .analysis import analyze
from .calibrate import calibrate
from .calibration_runner import score_and_calibrate
from .runner import (
    classify_slices,
    extract_slices,
    generate_queries,
    load_config,
    review_packets,
)
from .schema import digest, index_jsonl, load_cases, read_jsonl
from .validate import validate_witnesses


def _environment_versions() -> dict[str, str | None]:
    names = ("cpgqls-client", "transformers", "torch", "vllm", "peft",
             "bitsandbytes", "numpy")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _lock_inputs(work: Path, manifest: Path, config: Path, cases, repeats: int = 3) -> None:
    """Freeze acquisition inputs; permit later D calibration and versioned reanalysis."""
    h = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    core = root / "llmxcpg"
    if not core.exists():  # reduced development workspace
        core = root / "tmp_pinned" / "llmxcpg"
    q_joern_sources = [core / "config.py", core / "prompts.py",
                       core / "inference" / "query_generator.py"]
    q_joern_sources += sorted((core / "joern").rglob("*.py"))
    q_joern_sources += sorted((core / "slicing").rglob("*.py"))
    for path in (manifest, Path(__file__), Path(__file__).with_name("runner.py"),
                 Path(__file__).with_name("schema.py"), Path(__file__).with_name("validate.py"),
                 *q_joern_sources):
        h.update(str(path).encode("utf-8"))
        h.update(path.read_bytes())
    cfg = json.loads(config.read_text(encoding="utf-8"))
    acquisition_cfg = {key: value for key, value in cfg.items()
                       if key != "threshold" and not key.startswith("detector_")}
    h.update(json.dumps(acquisition_cfg, sort_keys=True).encode("utf-8"))
    h.update(f"repeats={repeats}".encode("utf-8"))
    versions = _environment_versions()
    h.update(json.dumps(versions, sort_keys=True).encode("utf-8"))
    for case in cases:
        for arm, source in sorted(case.sources.items()):
            h.update(case.case_id.encode("utf-8"))
            h.update(arm.encode("utf-8"))
            h.update(source.encode("utf-8"))
    for evidence in (work / "witness_validation.jsonl",):
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
                                    "config": str(config.resolve()),
                                    "environment_versions": versions}, indent=2) + "\n",
                        encoding="utf-8")


def _lock_detector(work: Path, config: Path) -> None:
    """Freeze D settings and calibration at first detection, after Q/Joern may have run."""
    calibration = work / "calibration.json"
    cfg = json.loads(config.read_text(encoding="utf-8"))
    settings = {key: value for key, value in cfg.items()
                if key == "threshold" or key.startswith("detector_")}
    h = hashlib.sha256()
    h.update(calibration.read_bytes() if calibration.exists() else b"dummy_run")
    h.update(json.dumps(settings, sort_keys=True).encode("utf-8"))
    root = Path(__file__).resolve().parents[1]
    core = root / "llmxcpg"
    if not core.exists():
        core = root / "tmp_pinned" / "llmxcpg"
    for path in (core / "config.py", core / "inference" / "classifier.py"):
        if path.exists():
            h.update(path.read_bytes())
    fingerprint = h.hexdigest()
    lock = work / "detector_lock.json"
    if lock.exists():
        if json.loads(lock.read_text(encoding="utf-8"))["fingerprint"] != fingerprint:
            raise ValueError("D settings or calibration changed; use a new --work directory")
    else:
        lock.write_text(json.dumps({"fingerprint": fingerprint,
                                    "detector_settings": settings}, indent=2) + "\n",
                        encoding="utf-8")


def _require_witnesses(work: Path, cases) -> None:
    if not any(c.admissible for c in cases):
        return
    checks = index_jsonl(work / "witness_validation.jsonl", "case_id")
    for case in cases:
        if case.admissible and (case.case_id not in checks or
                                any(checks[case.case_id]["checks"].get(k) != "pass"
                                    for k in ("compile", "trigger")) or
                                checks[case.case_id]["checks"].get("benign_behavior") !=
                                case.validation["benign_behavior"] or
                                checks[case.case_id].get("source_sha256") !=
                                {arm: digest(case.sources[arm]) for arm in ("U", "TM", "TN")}):
            raise ValueError(f"Missing or failed executable witness checks for {case.case_id}")


def _require_calibration(work: Path, cfg: dict, manifest: Path) -> None:
    if cfg.get("allow_dummy", False):
        return
    path = work / "calibration.json"
    if not path.exists():
        raise ValueError("Run score-calibration on disjoint data before D detection")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not result.get("score_sha256") and not cfg.get("allow_dummy", False):
        raise ValueError("Use score-calibration so D scores have a retained stage trace")
    score_path = work / "calibration_scores.jsonl"
    if result.get("score_sha256") and (not score_path.exists() or
            hashlib.sha256(score_path.read_bytes()).hexdigest() != result["score_sha256"]):
        raise ValueError("Calibration scores changed after threshold selection")
    if (result.get("analysis_manifest_sha256") and
            result["analysis_manifest_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest()):
        raise ValueError("Analysis manifest changed after calibration")
    if not result["usability_gate_pass"] or abs(result["threshold"] - cfg["threshold"]) > 1e-9:
        raise ValueError("Usability gate failed or configured threshold differs from calibration")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate source-to-evidence retrieval")
    parser.add_argument("phase", choices=("verify", "calibrate", "score-calibration", "validate", "query", "slice", "detect", "packets",
                                          "analyze", "all"))
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
            parser.error("D has already run; use a new --work directory")
        result = score_and_calibrate(cases, args.calibration_manifest, args.work,
                                     load_config(args.config))
        result["analysis_manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
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
    cfg = (load_config(args.config, require_detector=args.phase in ("all", "detect"))
           if args.phase in ("all", "query", "slice", "detect", "packets", "analyze") else None)
    if args.phase in ("packets", "analyze") and not cfg.get("allow_dummy", False):
        missing = [case.case_id for case in cases
                   if not isinstance(case.referent.get("review_claim"), str) or
                   not case.referent["review_claim"].strip()]
        if missing:
            raise ValueError(f"Case-specific review_claim required for blind review: {missing}")
    _lock_inputs(args.work, args.manifest, args.config, cases, args.repeats)
    _require_witnesses(args.work, cases)
    if args.phase in ("all", "detect"):
        _require_calibration(args.work, cfg, args.manifest)
        _lock_detector(args.work, args.config)
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
                         repeats=args.repeats, resolutions=args.resolutions,
                         evidence_only=args.evidence_only)
        report["analysis_provenance"] = {
            "analysis_sha256": hashlib.sha256(Path(__file__).with_name("analysis.py").read_bytes()).hexdigest(),
            "assessments_sha256": hashlib.sha256(args.assessments.read_bytes()).hexdigest(),
            "adjudications_sha256": hashlib.sha256(args.adjudications.read_bytes()).hexdigest(),
            "resolutions_sha256": (hashlib.sha256(args.resolutions.read_bytes()).hexdigest()
                                   if args.resolutions else None),
        }
        path = args.work / "analysis.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
