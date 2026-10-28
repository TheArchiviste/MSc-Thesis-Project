"""Local-first preparation, readiness and pre-main freeze; no automatic GPU rental."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from evidence_experiment.locks import (
    DEPLOYMENT_SETTINGS,
    QUERY_PACKAGES,
    SLICE_PACKAGES,
    check_stage_receipts,
    git_provenance,
    lock_inputs,
    package_versions,
    require_witnesses,
)
from evidence_experiment.runner import PINNED_PIPELINE_COMMIT, load_config
from evidence_experiment.schema import index_jsonl, load_cases, read_jsonl, run_specs
from evidence_experiment.validate import validate_witnesses

from .prepare import ROOT as CORPUS
from .prepare import reference, render, sha, verify_selection

ROOT = CORPUS.parent
SPLITS = ("development", "main")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def corpus_contract():
    """Hash the retained sources, maps, references, selection and preparation code."""
    paths = [p for p in CORPUS.rglob("*") if p.is_file() and
             "__pycache__" not in p.parts and "validation" not in p.parts]
    paths += [ROOT / "evidence_experiment" / name for name in
              ("runner.py", "bounded_joern.py", "locks.py", "schema.py", "validate.py", "review.py")]
    paths += [ROOT / "juliet_pilot" / name for name in ("prepare.py", "templates.py")]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def verify_corpus():
    if (platform.system() != "Linux" or tuple(ctypes.sizeof(x) for x in
            (ctypes.c_void_p, ctypes.c_int, ctypes.c_long)) != (8, 4, 8)):
        raise ValueError("The RQ1 corpus requires LP64 Linux/WSL2")
    selection = json.loads((CORPUS / "selection.json").read_text())
    verify_selection(selection, root=CORPUS)
    selected = {r["case_id"]: r for r in selection["cases"]}
    for cid, row in selected.items():
        if sha((CORPUS / "upstream" / f"{cid}.c").read_text()) != row["normalized_sha256"]:
            raise ValueError(f"Upstream source hash changed: {cid}")
    for name, expected in selection["support_sha256"].items():
        if hashlib.sha256((CORPUS / "support" / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Witness support hash changed: {name}")
    blocks = set()
    counts = {}
    for split in SPLITS:
        rows = read_jsonl(CORPUS / f"{split}.jsonl")
        cases = load_cases(CORPUS / f"{split}.jsonl")
        counts[split] = len(cases)
        for row in rows:
            cid = row["case_id"]
            if row["cluster_id"] in blocks:
                raise ValueError(f"Related block duplicated or shared across splits: {cid}")
            blocks.add(row["cluster_id"])
            original = (CORPUS / "upstream" / f"{cid}.c").read_text()
            control = "goodB2G" if selected[cid]["block"] == "CWE129" else "goodG2B"
            for arm in ("U", "F"):
                code, mapping, renames = render(original, arm, control)
                if (CORPUS / row["sources"][arm]).read_text() != code:
                    raise ValueError(f"Prepared source is not reproducible: {cid}/{arm}")
                expected_map = {"upstream_line_for_generated_line": mapping,
                                "identifier_map": renames, "source_sha256_lf": sha(original),
                                "generated_sha256": sha(code)}
                if json.loads((CORPUS / row["line_maps"][arm]).read_text()) != expected_map:
                    raise ValueError(f"Line map changed: {cid}/{arm}")
            expected = reference(selected[cid], (CORPUS / row["sources"]["U"]).read_text())
            if any(row["referent"].get(k) != v for k, v in expected.items()):
                raise ValueError(f"Source-only reference changed: {cid}")
            if not row["referent"].get("rq1_witness_required"):
                raise ValueError(f"Witness gate disabled: {cid}")
    if counts != {"development": 3, "main": 12}:
        raise ValueError(f"Unexpected enrolled counts: {counts}")
    return counts


def policy(cfg):
    return {k: v for k, v in cfg.items() if k not in DEPLOYMENT_SETTINGS}


def check_acquisition_ready(manifest, config, phase=None):
    """Called by the public experiment CLI as well as the convenience wrapper."""
    verify_corpus()
    if Path(manifest).resolve() not in {CORPUS / f"{split}.jsonl" for split in SPLITS}:
        raise ValueError("Use the verified canonical development or main RQ1 manifest")
    cfg = load_config(config, require_detector=False)
    if (cfg.get("allow_dummy") or cfg.get("query_engine") != "vllm" or
            cfg.get("query_model") != "QCRI/LLMxCPG-Q" or
            cfg.get("query_revision") != "1f48ab60420d90277207394f1254d27d3375b07e" or
            cfg.get("pipeline_commit") != PINNED_PIPELINE_COMMIT or
            not re.fullmatch(r"sha256:[0-9a-f]{64}", cfg.get("joern_digest", ""))):
        raise ValueError("RQ1 requires released Q, real vLLM and an inspected Joern digest")
    if Path(manifest).resolve() == CORPUS / "main.jsonl":
        frozen_path = ROOT / cfg.get("rq1_freeze_file", "work/rq1-freeze.json")
        if not frozen_path.exists():
            raise ValueError("Main acquisition is blocked until the real development report is frozen")
        frozen = json.loads(frozen_path.read_text())
        if frozen.get("corpus_contract") != corpus_contract() or frozen.get("policy") != policy(cfg):
            raise ValueError("Corpus or Q/Joern policy changed after the pre-main freeze")
        if phase in ("query", "slice"):
            current = package_versions(QUERY_PACKAGES if phase == "query" else SLICE_PACKAGES)
            if current != frozen.get("stage_environments", {}).get(phase):
                raise ValueError(f"{phase} packages differ from the accepted development environment")


def initialize(config):
    verify_corpus()
    if config.exists():
        raise FileExistsError(f"{config} exists; refusing to overwrite")
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CORPUS / "config.example.json", config)
    (ROOT / "work/joern-inputs").mkdir(parents=True, exist_ok=True)


def command(*argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        return out.returncode == 0, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def pin_joern(config):
    if (ROOT / "work/rq1-freeze.json").exists():
        raise ValueError("Policy already frozen; use a new study directory for a changed Joern image")
    ok, image = command("docker", "inspect", "llmxcpg_joern", "--format", "{{.Image}}")
    if not ok:
        raise ValueError(image)
    ok, raw = command("docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}")
    if not ok:
        raise ValueError(raw)
    matches = [d.split("@", 1)[1] for d in json.loads(raw) or []
               if d.startswith("ghcr.io/joernio/joern@sha256:")]
    if len(set(matches)) != 1:
        raise ValueError("Cannot establish one Joern repository digest from the running container")
    cfg = json.loads(config.read_text())
    cfg["joern_digest"] = matches[0]
    write_json(config, cfg)
    print(f"Pinned running Joern image: {matches[0]}")


def doctor(profile, config, work):
    checks = []
    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    try:
        add("corpus", True, verify_corpus())
    except (ValueError, OSError) as exc:
        add("corpus", False, exc)
    add("linux_lp64", platform.system() == "Linux" and
        tuple(ctypes.sizeof(x) for x in (ctypes.c_void_p, ctypes.c_int, ctypes.c_long)) == (8, 4, 8),
        "Use 64-bit Linux or WSL2; this witness corpus is validated for LP64")
    provenance = git_provenance()
    add("pinned_pipeline", provenance["q_joern_pin"] == "matches_pin", provenance["q_joern_pin"])
    try:
        check_acquisition_ready(CORPUS / "development.jsonl", config)
        cfg = load_config(config, require_detector=False)
        add("config", True, "Real Q/Joern pins present")
    except (ValueError, OSError) as exc:
        cfg = {}
        add("config", False, exc)
    if profile == "local":
        add("gcc", *command("gcc", "--version"))
        add("compose", *command("docker", "compose", "version"))
        from scripts.pilot_setup import _docker_digest
        if cfg:
            add("joern_image", *_docker_digest(cfg))
            add("real_cpg_import_and_query", *_probe_joern(cfg))
    else:
        for name in ("torch", "vllm", "transformers"):
            add(name, importlib.util.find_spec(name) is not None, "Required on the Q host")
        if importlib.util.find_spec("torch"):
            from scripts.pilot_setup import _gpu
            add("cuda_bf16_capacity", *_gpu())
        cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
        existing = next(p for p in (cache, *cache.parents) if p.exists())
        free = shutil.disk_usage(existing).free / 2**30
        add("model_cache_space", free >= 100, f"{free:.1f} GiB free; allow >=100 GiB for pinned Q")
    result = {"profile": profile, "ready": all(r["ok"] for r in checks), "checks": checks,
              "utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "machine": platform.machine(), "provenance": provenance,
              "meaning": "Readiness checks only; not experiment results. GPU load remains untested."}
    write_json(work / "readiness.json", result)
    lines = [f"# RQ1 {profile} readiness", "", f"Ready: **{result['ready']}**", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    for row in checks:
        detail = row["detail"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {row['check']} | {'PASS' if row['ok'] else 'BLOCKED'} | {detail} |")
    (work / "readiness.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(result, indent=2))
    return result["ready"]


def _probe_joern(cfg):
    from evidence_experiment.bounded_joern import BoundedJoern
    from llmxcpg.joern.client import JoernClient
    client = None
    try:
        client = BoundedJoern(JoernClient(host=cfg.get("joern_host", "127.0.0.1"),
                             port=cfg.get("joern_port", 8080),
                             local_input_dir=ROOT / cfg.get("joern_input_dir", "work/joern-inputs"),
                             server_input_dir=cfg.get("server_input_dir", "/analysis/inputs")),
                             cfg.get("joern_rpc_timeout", 120), cfg.get("joern_case_timeout", 600))
        client.begin_case()
        client.import_code("int main(void) { return 0; }", project_name="rq1_preflight")
        result = client.run('cpg.method.name("main").size')
        if not result.success or not re.search(r"=\s*1\s*$", result.stdout.strip()):
            return False, f"Staged CPG check failed: {result.stdout[:250]}"
        client.reset()
        return True, "Imported staged C and found main in the real CPG"
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
        return False, f"Joern check failed: {exc}; restart the worker before retrying"
    finally:
        if client is not None:
            client.close()


def status(split, work):
    cases = load_cases(CORPUS / f"{split}.jsonl")
    expected = {s["run_id"] for s in run_specs(cases, 1)}
    queries = index_jsonl(work / "queries.jsonl", "run_id")
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    witnesses = index_jsonl(work / "witness_validation.jsonl", "case_id")
    witness_ok = True
    try:
        require_witnesses(work, cases)
    except ValueError:
        witness_ok = False
    return {"split": split, "cases": len(cases), "blocks": len({c.cluster_id for c in cases}),
            "planned_U": len(cases), "planned_F": len(cases), "planned_Q_and_slices": len(expected),
            "witness_records": len(witnesses), "all_witnesses_pass_current_sources": witness_ok,
            "queries_recorded": len(expected & queries.keys()),
            "slices_recorded": len(expected & slices.keys()),
            "real_inference_complete": (expected <= queries.keys() and expected <= slices.keys()
                and all(queries[r].get("query_engine") == "vllm" and
                        queries[r].get("synthetic") is False for r in expected)),
            "assessment_report": str(work / "rq1_report.md") if (work / "rq1_report.md").exists() else "pending",
            "interpretation": "Pending inference or assessment is not an inadequate finding."}


def freeze(config, dev_work):
    verify_corpus()
    cfg = load_config(config, require_detector=False)
    check_acquisition_ready(CORPUS / "development.jsonl", config)
    summary = status("development", dev_work)
    if not summary["all_witnesses_pass_current_sources"] or not summary["real_inference_complete"]:
        raise ValueError("Freeze requires validated U/F and all six real development runs")
    check_stage_receipts(dev_work)
    lock_inputs(dev_work, CORPUS / "development.jsonl", config,
                load_cases(CORPUS / "development.jsonl"), 1, phase="freeze")
    receipts = json.loads((dev_work / "stage_receipts.json").read_text())
    if not {"queries.jsonl", "slices.jsonl"} <= receipts.keys():
        raise ValueError("Both real stage receipts are required")
    for row in read_jsonl(dev_work / "queries.jsonl"):
        if row.get("query_engine") != "vllm" or row.get("synthetic") is not False:
            raise ValueError("Synthetic or unidentified Q output cannot pass the development gate")
    lock = json.loads((dev_work / "experiment_lock.json").read_text())
    if not lock.get("stage_environments", {}).get("query", {}).get("vllm"):
        raise ValueError("Development must record the real vLLM runtime")
    report = json.loads((dev_work / "analysis.json").read_text())
    if report.get("scope") != "evidence_only" or report.get("assessment_mode") != "assistant":
        raise ValueError("Need the explicitly labelled AI-assisted development assessment report")
    for filename, key in (("assessments.final.jsonl", "assessments_sha256"),
                          ("assessments.initial.jsonl", "initial_assessments_sha256"),
                          ("adjudications.jsonl", "adjudications_sha256")):
        if (hashlib.sha256((dev_work / filename).read_bytes()).hexdigest() !=
                report.get("analysis_provenance", {}).get(key)):
            raise ValueError("Development assessments changed after analysis; analyze again")
    from evidence_experiment.review import packet_index
    packets, _ = packet_index(load_cases(CORPUS / "development.jsonl"), dev_work, 1)
    if report["review"].get("assessed_packets") != len(packets):
        raise ValueError("Assess every shown development packet, allowing justified uncertain decisions")
    audit_path = ROOT / cfg.get("rq1_token_audit_file", "work/rq1-token-audit.json")
    audit = json.loads(audit_path.read_text())
    if (audit["corpus_contract"] != corpus_contract() or audit["query_revision"] != cfg["query_revision"]
            or audit["query_max_context"] != cfg["query_max_context"]):
        raise ValueError("Rerun token-audit for the final sources and context setting")
    infra = {"joern_transport", "timeout", "unknown_slice_failure", "worker_reset_failed"}
    if any(r["status"] in infra for r in report["run_evidence"]):
        raise ValueError("Resolve development infrastructure failures before freezing")
    frozen = {"utc": datetime.now(timezone.utc).isoformat(), "corpus_contract": corpus_contract(),
              "stage_environments": lock["stage_environments"],
              "policy": policy(cfg), "development_output_sha256": receipts,
              "development_analysis_sha256": hashlib.sha256((dev_work / "analysis.json").read_bytes()).hexdigest(),
              "token_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
              "assessment_mode": "assistant", "primary_rule": "repeat_0",
              "repeats": 1, "development_summary": summary, "provenance": git_provenance()}
    path = ROOT / cfg.get("rq1_freeze_file", "work/rq1-freeze.json")
    if path.exists():
        raise FileExistsError("Pre-main freeze already exists; refusing to overwrite")
    write_json(path, frozen)
    print(f"Main policy frozen: {path}")


def token_audit(config):
    """Download only the pinned tokenizer, never the model weights; CPU is sufficient."""
    from types import SimpleNamespace

    from transformers import AutoTokenizer

    from llmxcpg.inference.query_generator import QueryGenerator
    from llmxcpg.prompts import render_query_prompt
    verify_corpus()
    cfg = json.loads(config.read_text())
    tokenizer = AutoTokenizer.from_pretrained(cfg["query_model"], revision=cfg["query_revision"],
                                              trust_remote_code=True)
    formatter = object.__new__(QueryGenerator)
    formatter._llm = SimpleNamespace(get_tokenizer=lambda: tokenizer)
    records = []
    for split in SPLITS:
        for case in load_cases(CORPUS / f"{split}.jsonl"):
            for arm, source in case.sources.items():
                prompt = formatter._format_vllm_prompt(render_query_prompt(source))
                count = len(tokenizer.encode(prompt))
                records.append({"case_id": case.case_id, "split": split, "arm": arm,
                                "source_sha256": sha(source), "prompt_tokens": count,
                                "generation_allowance": 2048,
                                "fits": count + 2048 <= cfg["query_max_context"]})
    result = {"query_revision": cfg["query_revision"], "query_max_context": cfg["query_max_context"],
              "corpus_contract": corpus_contract(), "records": records,
              "meaning": "Token lengths only; no generated queries or adequacy results."}
    path = ROOT / cfg.get("rq1_token_audit_file", "work/rq1-token-audit.json")
    write_json(path, result)
    print(f"Audited {len(records)} prompts; {sum(r['fits'] for r in records)} fit. {path}")


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "init", "validate", "doctor", "pin-joern", "status", "freeze", "token-audit"))
    parser.add_argument("--config", type=Path, default=Path("work/rq1-config.json"))
    parser.add_argument("--split", choices=SPLITS, default="development")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--profile", choices=("local", "gpu"), default="local")
    args = parser.parse_args()
    work = args.work or Path("work/rq1") / args.split
    if args.action == "verify":
        print(json.dumps(verify_corpus(), indent=2))
    elif args.action == "init":
        initialize(args.config)
        print(f"Created {args.config}; inspect and pin running Joern before acquisition.")
    elif args.action == "validate":
        verify_corpus()
        out = work / "witness_validation.jsonl"
        if out.exists():
            raise FileExistsError(f"{out} exists; use a fresh --work directory")
        validate_witnesses(load_cases(CORPUS / f"{args.split}.jsonl"),
                           CORPUS / f"{args.split}.jsonl", CORPUS / "witness_plan.jsonl", out)
        summary = status(args.split, work)
        write_json(work / "status.json", summary)
        print(json.dumps(summary, indent=2))
        if not summary["all_witnesses_pass_current_sources"]:
            raise SystemExit(1)
    elif args.action == "doctor":
        if not doctor(args.profile, args.config, work):
            raise SystemExit(1)
    elif args.action == "pin-joern":
        pin_joern(args.config)
    elif args.action == "freeze":
        freeze(args.config, work)
    elif args.action == "token-audit":
        token_audit(args.config)
    else:
        print(json.dumps(status(args.split, work), indent=2))


if __name__ == "__main__":
    main()
