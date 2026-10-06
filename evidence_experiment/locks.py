"""Provenance locks for acquisition (Q/Joern) and detection (D).

The acquisition lock freezes what determines the Q and Joern outputs: the
manifest and sources, the acquisition part of the config, the repeat count,
witness results, the run-spec/runner code and the pinned Q/Joern pipeline
files. Paths are hashed relative to the repository, so a work directory can be
analysed from a different checkout location.

Package versions are enforced only where they matter:

* ``query``/``slice``/``all`` must run with the same Q/Joern packages
  (``ACQUISITION_PACKAGES``) as the first acquisition call;
* ``detect`` must run with the same D packages (``DETECTOR_PACKAGES``) as the
  first detection call, recorded in the separate detector lock;
* ``packets`` and ``analyze`` only record their environment in
  ``phase_log.jsonl``, so review and analysis can run on another machine.

Review-queue and analysis code are not part of the acquisition fingerprint;
``analysis.json`` and ``review_key.jsonl`` record their own provenance.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runner import PINNED_PIPELINE_COMMIT, Q_JOERN_PINNED_PATHS
from .schema import append_jsonl, digest, index_jsonl

LOCK_VERSION = 2
ACQUISITION_PHASES = frozenset({"query", "slice", "all"})
ACQUISITION_PACKAGES = ("cpgqls-client", "websocket-client", "vllm", "torch", "transformers")
DETECTOR_PACKAGES = ("torch", "transformers", "peft", "bitsandbytes", "accelerate")
ALL_PACKAGES = tuple(dict.fromkeys(ACQUISITION_PACKAGES + DETECTOR_PACKAGES + ("numpy",)))

ROOT = Path(__file__).resolve().parents[1]


def _core() -> Path:
    core = ROOT / "llmxcpg"
    return core if core.exists() else ROOT / "tmp_pinned" / "llmxcpg"


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def package_versions(names: tuple[str, ...]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                              text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_provenance() -> dict[str, Any]:
    """Actual checkout, uncommitted tracked changes, and the Q/Joern pin check."""
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    pin = _git("diff", "--quiet", PINNED_PIPELINE_COMMIT, "--", *Q_JOERN_PINNED_PATHS)
    if pin is None or pin.returncode not in (0, 1):
        pin_state = "unverifiable"  # no git, or the pinned commit is not in this clone
    else:
        pin_state = "matches_pin" if pin.returncode == 0 else "differs_from_pin"
    modified = ([line[3:] for line in status.stdout.splitlines()]
                if status is not None and status.returncode == 0 else None)
    return {"commit": head.stdout.strip() if head is not None and head.returncode == 0 else None,
            "modified_tracked_files": modified,
            "pinned_pipeline_commit": PINNED_PIPELINE_COMMIT,
            "q_joern_paths": list(Q_JOERN_PINNED_PATHS),
            "q_joern_pin": pin_state}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_phase(work: Path, phase: str, provenance: dict[str, Any]) -> None:
    append_jsonl(work / "phase_log.jsonl", {
        "phase": phase, "utc": _now(), "python": platform.python_version(),
        "packages": package_versions(ALL_PACKAGES), "provenance": provenance})


def acquisition_fingerprint(manifest: Path, config: Path, cases, repeats: int,
                            work: Path) -> str:
    h = hashlib.sha256()
    core = _core()
    code = [Path(__file__).with_name(name) for name in ("runner.py", "schema.py", "validate.py")]
    code += [core / "config.py", core / "prompts.py", core / "inference" / "query_generator.py"]
    code += sorted((core / "joern").rglob("*.py")) + sorted((core / "slicing").rglob("*.py"))
    h.update(b"manifest\n" + manifest.read_bytes())
    for path in code:
        h.update(_relative(path).encode("utf-8") + b"\n" + path.read_bytes())
    cfg = json.loads(config.read_text(encoding="utf-8"))
    acquisition_cfg = {key: value for key, value in cfg.items()
                       if key != "threshold" and not key.startswith("detector_")}
    h.update(json.dumps(acquisition_cfg, sort_keys=True).encode("utf-8"))
    h.update(f"repeats={repeats}".encode())
    for case in cases:
        for arm, source in sorted(case.sources.items()):
            h.update(f"{case.case_id}|{arm}\n".encode() + source.encode("utf-8"))
    witness = work / "witness_validation.jsonl"
    if witness.exists():
        h.update(witness.read_bytes())
    return h.hexdigest()


def _environment_change(recorded: dict[str, Any], current: dict[str, Any]) -> str:
    return ", ".join(f"{name} {recorded.get(name)} -> {current.get(name)}"
                     for name in sorted(set(recorded) | set(current))
                     if recorded.get(name) != current.get(name))


def lock_inputs(work: Path, manifest: Path, config: Path, cases, repeats: int = 3,
                *, phase: str = "query") -> dict[str, Any]:
    """Create or check the acquisition lock; enforce packages only for Q/Joern phases."""
    fingerprint = acquisition_fingerprint(manifest, config, cases, repeats, work)
    provenance = git_provenance()
    acquiring = phase in ACQUISITION_PHASES
    if acquiring and provenance["q_joern_pin"] == "differs_from_pin":
        raise ValueError("Q/Joern code differs from pinned commit "
                         f"{PINNED_PIPELINE_COMMIT}; restore it or change the pin deliberately")
    environment = package_versions(ACQUISITION_PACKAGES)
    lock = work / "experiment_lock.json"
    if lock.exists():
        recorded = json.loads(lock.read_text(encoding="utf-8"))
        if recorded.get("lock_version") != LOCK_VERSION:
            raise ValueError("experiment_lock.json was written by an older engine; "
                             "use a new --work directory")
        if recorded["fingerprint"] != fingerprint:
            raise ValueError("Inputs or code changed; use a new --work directory for a new run")
        if acquiring and recorded["acquisition_environment"] != environment:
            change = _environment_change(recorded["acquisition_environment"], environment)
            raise ValueError(f"Q/Joern packages changed ({change}); "
                             "acquire in a new --work directory or restore the environment")
    else:
        recorded = {"lock_version": LOCK_VERSION, "fingerprint": fingerprint,
                    "created_utc": _now(), "created_by_phase": phase,
                    "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    "config": str(config), "repeats": repeats,
                    "acquisition_environment": environment,
                    "python": platform.python_version(), "provenance": provenance}
        lock.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
    _log_phase(work, phase, provenance)
    return recorded


def lock_detector(work: Path, config: Path, calibration: Path | None = None) -> dict[str, Any]:
    """Freeze D settings, calibration and D packages at the first detection."""
    calibration = calibration or work / "calibration.json"
    cfg = json.loads(config.read_text(encoding="utf-8"))
    settings = {key: value for key, value in cfg.items()
                if key == "threshold" or key.startswith("detector_")}
    h = hashlib.sha256()
    h.update(calibration.read_bytes() if calibration.exists() else b"dummy_run")
    h.update(json.dumps(settings, sort_keys=True).encode("utf-8"))
    core = _core()
    for path in (core / "config.py", core / "inference" / "classifier.py"):
        if path.exists():
            h.update(_relative(path).encode("utf-8") + b"\n" + path.read_bytes())
    fingerprint = h.hexdigest()
    environment = package_versions(DETECTOR_PACKAGES)
    lock = work / "detector_lock.json"
    if lock.exists():
        recorded = json.loads(lock.read_text(encoding="utf-8"))
        if recorded["fingerprint"] != fingerprint:
            raise ValueError("D settings or calibration changed; use a new --work directory")
        if recorded.get("detector_environment", environment) != environment:
            change = _environment_change(recorded["detector_environment"], environment)
            raise ValueError(f"D packages changed ({change}); restore the environment "
                             "or detect in a new --work directory")
    else:
        recorded = {"fingerprint": fingerprint, "created_utc": _now(),
                    "detector_settings": settings, "detector_environment": environment,
                    "calibration_path": str(calibration),
                    "calibration_sha256": (hashlib.sha256(calibration.read_bytes()).hexdigest()
                                           if calibration.exists() else None),
                    "provenance": git_provenance()}
        lock.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
    return recorded


def require_witnesses(work: Path, cases) -> None:
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


def require_calibration(calibration: Path, cfg: dict, manifest: Path) -> None:
    """Accept a calibration from any directory if its scores and manifest still match."""
    if cfg.get("allow_dummy", False):
        return
    if not calibration.exists():
        raise ValueError(f"No calibration at {calibration}; run score-calibration on "
                         "disjoint data, then pass --calibration")
    result = json.loads(calibration.read_text(encoding="utf-8"))
    if not result.get("score_sha256"):
        raise ValueError("Use score-calibration so D scores have a retained stage trace")
    score_path = calibration.parent / "calibration_scores.jsonl"
    if (not score_path.exists() or
            hashlib.sha256(score_path.read_bytes()).hexdigest() != result["score_sha256"]):
        raise ValueError("Calibration scores changed after threshold selection")
    if (result.get("analysis_manifest_sha256") and
            result["analysis_manifest_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest()):
        raise ValueError("Analysis manifest changed after calibration")
    if not result["usability_gate_pass"] or abs(result["threshold"] - cfg["threshold"]) > 1e-9:
        raise ValueError("Usability gate failed or configured threshold differs from calibration")
