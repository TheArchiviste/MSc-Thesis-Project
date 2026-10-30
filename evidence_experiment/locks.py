"""Source, stage, environment and output integrity for the RQ1 acquisition."""
from __future__ import annotations

import contextlib
import fcntl
import importlib.metadata
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .schema import file_digest, index_jsonl, run_specs, write_json

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_SETTINGS = {"joern_host", "joern_port", "joern_input_dir", "server_input_dir",
                       "rq1_freeze_file", "rq1_token_audit_file", "joern_capability_file", "rq1_calibration_file"}
LOCK_VERSION = 6


def now():
    return datetime.now(UTC).isoformat()


def package_versions(names):
    result = {}
    for name in names:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def environment():
    """Lock the complete installed stage environment, including Python and prompt dependencies."""
    packages = {d.metadata["Name"].lower().replace("_", "-"): d.version
                for d in importlib.metadata.distributions() if d.metadata.get("Name")}
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "machine": platform.machine(), "packages": dict(sorted(packages.items()))}


def git_provenance():
    def run(*args):
        p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                           text=True, timeout=20, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    return {"commit": run("rev-parse", "HEAD"),
            "modified_tracked_files": run("status", "--porcelain", "--untracked-files=no")}


def policy(cfg):
    return {k: v for k, v in cfg.items() if k not in DEPLOYMENT_SETTINGS}


@contextlib.contextmanager
def work_lock(work):
    work.mkdir(parents=True, exist_ok=True)
    with (work / ".run.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another process is using this work directory") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def acquisition_fingerprint(manifest, config, cases, repeats, work):
    from rq1.setup import corpus_contract

    from .schema import digest
    calibration_path = ROOT / config["rq1_calibration_file"]
    return digest(json.dumps({"code_and_corpus": corpus_contract(), "policy": policy(config),
          "manifest": file_digest(manifest), "runs": run_specs(cases, repeats),
          "witnesses": file_digest(work / "witness_validation.jsonl"),
          "calibration": file_digest(calibration_path) if calibration_path.is_file() else None}, sort_keys=True))


def require_witnesses(work, cases):
    records = index_jsonl(work / "witness_validation.jsonl", "case_id")
    from .schema import digest
    if set(records) != {c.case_id for c in cases}:
        raise ValueError("Witnesses must cover exactly this split")
    for c in cases:
        row = records[c.case_id]
        checks = row.get("checks", {})
        if (any(checks.get(k) != "pass" for k in ("compile", "trigger", "fixed")) or
            checks.get("benign_behavior") not in {"pass", "not_applicable"} or
            (c.referent.get("rq1_benign_required") and checks.get("benign_behavior") != "pass") or
            row.get("witness_plan_sha256") != c.referent.get("witness_plan_sha256") or
            row.get("source_sha256") != {a: digest(s) for a, s in c.sources.items()}):
            raise ValueError(f"Witness missing, failed or changed: {c.case_id}")


def lock_inputs(work, manifest, config, cases, repeats=1, *, phase="query"):
    cfg = json.loads(config.read_text()) if isinstance(config, Path) else config
    require_witnesses(work, cases)
    fingerprint = acquisition_fingerprint(manifest, cfg, cases, repeats, work)
    path = work / "experiment_lock.json"
    if not path.exists():
        if any((work / name).exists() for name in (
                "queries.jsonl", "slices.jsonl", "slice_attempts.jsonl", "query_sessions.jsonl",
                "stage_receipts.json", "blind_review_packets.jsonl", "analysis.json")):
            raise ValueError("Orphan outputs: restore their original lock or use a fresh work directory")
        lock = {"lock_version": LOCK_VERSION, "fingerprint": fingerprint,
                "created_utc": now(), "provenance": git_provenance(),
                "policy": policy(cfg), "stage_environments": {},
                "calibration_file": cfg["rq1_calibration_file"]}
    else:
        lock = json.loads(path.read_text())
        if lock.get("lock_version") != LOCK_VERSION or lock.get("fingerprint") != fingerprint:
            raise ValueError("Inputs, policy or code changed; use a new run directory")
    if phase in {"query", "slice"}:
        current = environment()
        prior = lock["stage_environments"].get(phase)
        if prior is not None and prior != current:
            raise ValueError(f"{phase} environment changed; restore its accepted Python/packages")
        lock["stage_environments"][phase] = current
        lines = [f"{k}=={v}" for k, v in current["packages"].items() if k != "llmxcpg"]
        (work / f"runtime.{phase}.requirements.txt").write_text("\n".join(lines) + "\n")
    write_json(path, lock)
    return lock


def check_stage_receipts(work):
    path = work / "stage_receipts.json"
    if not path.exists():
        return
    lock = json.loads((work / "experiment_lock.json").read_text())
    receipts = json.loads(path.read_text())
    if set(receipts) - {"query", "slice"}:
        raise ValueError("Unknown stage receipt")
    for phase, receipt in receipts.items():
        required = {"queries.jsonl", "query_sessions.jsonl"} if phase == "query" else {"slices.jsonl"}
        allowed = required if phase == "query" else required | {"slice_attempts.jsonl"}
        if (not required <= receipt.get("files", {}).keys() or
                set(receipt["files"]) - allowed or
                receipt.get("input_fingerprint") != lock["fingerprint"]):
            raise ValueError("Incomplete stage receipt or different inputs")
        for name, expected in receipt["files"].items():
            if not (work / name).is_file() or file_digest(work / name) != expected:
                raise ValueError(f"Completed output changed: {name}")


def validate_terminal_records(work, phase, cases):
    from .runner import QUERY_STATUSES, SLICE_STATUSES
    name = "queries.jsonl" if phase == "query" else "slices.jsonl"
    records = index_jsonl(work / name, "run_id")
    expected = {s["run_id"] for s in run_specs(cases)}
    if set(records) != expected:
        raise ValueError(f"Incomplete or foreign {phase} IDs: expected {len(expected)}, got {len(records)}")
    statuses = QUERY_STATUSES if phase == "query" else SLICE_STATUSES
    if any(row.get("status") not in statuses for row in records.values()):
        raise ValueError("Unknown or nonterminal observation status")
    if phase == "query":
        lock = json.loads((work / "experiment_lock.json").read_text())
        cfg = lock["policy"]
        sessions = index_jsonl(work / "query_sessions.jsonl", "session_id")
        for row in records.values():
            session = sessions.get(row.get("session_id"), {})
            if (row.get("synthetic") is not False or row.get("query_engine") != "vllm" or
                    session.get("synthetic") is not False or not session.get("model_load_seconds") or
                    session.get("effective_dtype") not in {"torch.bfloat16", "bfloat16"} or
                    session.get("runtime") != lock["stage_environments"].get("query") or
                    session.get("query_revision") != cfg["query_revision"] or
                    session.get("query_model") != cfg["query_model"] or
                    session.get("effective_max_context") != cfg["query_max_context"] or
                    session.get("effective_seed") != 0 or session.get("temperature") != 0 or
                    session.get("top_p") != 1 or session.get("generation_allowance") != 2048 or
                    type(row.get("prompt_tokens")) is not int or row["prompt_tokens"] <= 0 or
                    not isinstance(row.get("queries"), list) or
                    (row["status"] == "ok" and not row["queries"])):
                raise ValueError("Real Q session provenance is missing or synthetic")
    return records


def write_stage_receipt(work, phase, cases):
    validate_terminal_records(work, phase, cases)
    lock = json.loads((work / "experiment_lock.json").read_text())
    path = work / "stage_receipts.json"
    receipts = json.loads(path.read_text()) if path.exists() else {}
    files = ["queries.jsonl", "query_sessions.jsonl"] if phase == "query" else ["slices.jsonl"]
    if phase == "slice" and (work / "slice_attempts.jsonl").exists():
        files.append("slice_attempts.jsonl")
    receipts[phase] = {"input_fingerprint": lock["fingerprint"], "utc": now(),
                       "files": {name: file_digest(work / name) for name in files}}
    write_json(path, receipts)
