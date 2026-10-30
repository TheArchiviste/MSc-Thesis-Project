"""Local-first RQ1 readiness, tokenizer audit and immutable pre-main freeze."""
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
from pathlib import Path

from evidence_experiment.locks import (
    check_stage_receipts,
    environment,
    git_provenance,
    lock_inputs,
    now,
    policy,
    require_witnesses,
    validate_terminal_records,
)
from evidence_experiment.schema import (
    IMPLEMENTATION_ID,
    file_digest,
    index_jsonl,
    load_cases,
    read_jsonl,
    run_specs,
    write_json,
)
from evidence_experiment.validate import validate_witnesses

from .prepare import ROOT as CORPUS
from .prepare import reference, render, sha, verify_selection

ROOT = CORPUS.parent
SPLITS = ("development", "main")
CORPUS_SPLITS = (*SPLITS, 'assessor_holdout')
DEFAULT_CONFIG = Path("work/rq1-v7/config.json")


def assessment_code_contract():
    """A separately frozen judging implementation; never part of Q/slice fingerprints."""
    names = ('rq1/assessment_protocol.py', 'rq1/providers.py', 'rq1/judge.py',
             'rq1/calibration.py', 'rq1/assess.py', 'rq1/source_audit.py',
             'ops/rq1_api_calibration.py',
             'evidence_experiment/review.py', 'evidence_experiment/analysis.py',
             'evidence_experiment/rq1_report.py', 'rq1/visibility.py', 'rq1/assessor.example.json')
    return {name: file_digest(ROOT / name) for name in names}


def corpus_contract():
    """Acquisition dependencies only; grader changes cannot invalidate sealed Q/slices."""
    assessment = set(assessment_code_contract())
    paths = [p for name in ("rq1", "llmxcpg", "evidence_experiment")
             for p in (ROOT / name).rglob("*") if p.is_file() and
             "__pycache__" not in p.parts and "validation" not in p.parts and
             p.suffix != '.md' and p.name != 'pipeline_contract.json' and
             p.relative_to(ROOT).as_posix() not in assessment]
    paths.append(ROOT / "pyproject.toml")
    paths += [ROOT / name for name in ('ops/rq1_q_handoff.py', 'ops/rq1_collect.py')]
    return {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted(paths)}


def verify_implementation():
    contract = json.loads((CORPUS / "pipeline_contract.json").read_text())
    if contract["implementation_id"] != IMPLEMENTATION_ID:
        raise ValueError("Wrong implementation contract")
    for name, expected in contract["files"].items():
        if file_digest(ROOT / name) != expected:
            raise ValueError(f"Implementation drift: {name}; use a new version, never edit an active run")
    return contract


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
    for split in CORPUS_SPLITS:
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
    if counts != {"development": 3, "main": 12, "assessor_holdout": 2}:
        raise ValueError(f"Unexpected enrolled counts: {counts}")
    return counts



def load_config(path):
    cfg = json.loads(Path(path).read_text())
    example = json.loads((CORPUS / "config.example.json").read_text())
    if set(cfg) != set(example):
        raise ValueError("RQ1-v7 config fields differ; initialize a fresh config, preserving old runs")
    fixed = {"implementation_id": IMPLEMENTATION_ID, "query_model": "QCRI/LLMxCPG-Q",
             "query_revision": "1f48ab60420d90277207394f1254d27d3375b07e",
             "query_engine": "vllm", "query_temperature": 0.0, "query_batch_size": 1,
             "query_max_context": 8192, "query_tensor_parallel_size": 1,
             "infrastructure_attempts": 3}
    if any(cfg[k] != v for k, v in fixed.items()):
        raise ValueError("Config changes the frozen RQ1-v7 Q/selector design")
    if (not re.fullmatch(r"sha256:[0-9a-f]{64}", cfg["joern_digest"]) or
            not 0 < cfg["query_gpu_memory_utilization"] < 1 or
            not 0 < cfg["joern_rpc_timeout"] <= cfg["joern_case_timeout"]):
        raise ValueError("Invalid image digest, GPU fraction or timeouts")
    # The Docker mount is fixed in compose.yml; arbitrary host folders would silently mis-map inputs.
    if cfg["joern_input_dir"] != "work/joern-inputs" or cfg["server_input_dir"] != "/analysis/inputs":
        raise ValueError("Use the documented Docker input mount")
    return cfg


def token_audit_valid(cfg):
    audit = json.loads((ROOT / cfg["rq1_token_audit_file"]).read_text())
    if (audit.get("corpus_contract") != corpus_contract() or
            audit.get("policy") != policy(cfg)):
        raise ValueError("Token audit is stale; rerun with final code, sources and config")
    expected = {(c.case_id, a): sha(s) for split in SPLITS
                for c in load_cases(CORPUS / f"{split}.jsonl") for a, s in c.sources.items()}
    rows = audit["records"]
    actual = {(r["case_id"], r["arm"]): r["source_sha256"] for r in rows}
    if actual != expected or len(rows) != len(expected):
        raise ValueError("Token audit must cover exactly all 30 current U/F inputs")
    for r in rows:
        if (type(r["prompt_tokens"]) is not int or r["prompt_tokens"] <= 0 or
                r["generation_allowance"] != 2048 or
                r["fits"] != (r["prompt_tokens"] + 2048 <= cfg["query_max_context"])):
            raise ValueError("Invalid token-audit record")
    return audit


def capability_valid(cfg):
    result = json.loads((ROOT / cfg["joern_capability_file"]).read_text())
    if (result.get("ready") is not True or result.get("synthetic") is not False or
            result.get("corpus_contract") != corpus_contract() or result.get("policy") != policy(cfg)):
        raise ValueError("Fresh full-selector CPU conformance is required")
    from .conformance import validate_receipt
    validate_receipt(result, evidence_root=(ROOT / cfg["joern_capability_file"]).parent)
    return result


def acquisition_freeze(config):
    """Freeze Q/Joern apparatus before collecting outputs, independently of grading."""
    verify_corpus()
    verify_implementation()
    cfg = load_config(config)
    token_audit_valid(cfg)
    capability = capability_valid(cfg)
    if capability['environment'] != environment():
        raise ValueError('Create the acquisition freeze on the accepted CPU environment')
    provenance = git_provenance()
    if not provenance['commit'] or provenance['modified_tracked_files']:
        raise ValueError('Freeze a clean, committed checkout')
    root = (ROOT / cfg['rq1_calibration_file']).parent.parent
    files = {}
    for split in SPLITS:
        work = root / split
        require_witnesses(work, load_cases(CORPUS / f'{split}.jsonl'))
        if any((work / name).exists() for name in ('queries.jsonl', 'slices.jsonl')):
            raise ValueError('Declare the acquisition freeze before any Q/slice output')
        path = work / 'witness_validation.jsonl'
        files[str(path.relative_to(ROOT))] = file_digest(path)
    for field in ('rq1_token_audit_file', 'joern_capability_file'):
        files[cfg[field]] = file_digest(ROOT / cfg[field])
    receipt = {'utc': now(), 'corpus_contract': corpus_contract(), 'policy': policy(cfg),
               'files': files, 'cpu_environment': environment(), 'provenance': provenance,
               'rule': 'One primary Q/slice run per input. Seal outputs before release; no assessor or corpus tuning from acquired outputs.'}
    write_json(ROOT / cfg['rq1_acquisition_freeze_file'], receipt, exclusive=True)
    print('RQ1_ACQUISITION_FREEZE_OK: sealed collection permitted; assessment is still gated')
    return receipt


def require_acquisition_freeze(cfg):
    receipt = json.loads((ROOT / cfg['rq1_acquisition_freeze_file']).read_text())
    if receipt.get('corpus_contract') != corpus_contract() or receipt.get('policy') != policy(cfg):
        raise ValueError('Acquisition code, corpus or policy changed after its freeze')
    required = {cfg['rq1_token_audit_file'], cfg['joern_capability_file']}
    root = (ROOT / cfg['rq1_calibration_file']).parent.parent
    required |= {str((root / split / 'witness_validation.jsonl').relative_to(ROOT)) for split in SPLITS}
    if set(receipt.get('files', {})) != required:
        raise ValueError('Acquisition freeze is incomplete')
    for name, sha256 in receipt['files'].items():
        if file_digest(ROOT / name) != sha256:
            raise ValueError('Acquisition apparatus evidence changed after freeze')
    return receipt


def check_acquisition_ready(manifest, config, phase=None, *, sealed=False):
    verify_corpus()
    verify_implementation()
    manifest = Path(manifest).resolve()
    if manifest not in {CORPUS / f"{s}.jsonl" for s in SPLITS}:
        raise ValueError("Use a canonical RQ1 development or main manifest")
    cfg = load_config(config)
    token_audit_valid(cfg)
    capability = capability_valid(cfg)
    if phase == "slice" and capability.get("environment") != environment():
        raise ValueError("Restore the CPU environment used for the accepted selector conformance")
    provenance = git_provenance()
    if not provenance["commit"] or provenance["modified_tracked_files"]:
        raise ValueError("Acquire only from a clean, committed implementation")
    if sealed:
        if phase not in {'query', 'slice', 'visibility'}:
            raise ValueError('Only acquisition and structural computation may run sealed')
        require_acquisition_freeze(cfg)
        if phase == 'query':
            receipt = json.loads(((ROOT / cfg['rq1_calibration_file']).parent.parent / 'q-vm-inspection.json').read_text())
            if (receipt.get('technical_ready') is not True or receipt.get('environment') != environment() or
                    receipt.get('core_contract') != corpus_contract()):
                raise ValueError('Restore the inspected Q VM environment before acquisition')
        if manifest == CORPUS / 'main.jsonl' and phase in {'query', 'slice'}:
            dev = (ROOT / cfg['rq1_calibration_file']).parent.parent / 'development'
            records = validate_terminal_records(dev, phase, load_cases(CORPUS / 'development.jsonl'))
            from evidence_experiment.runner import INFRA_STATUSES
            if phase == 'slice' and any(r['status'] in INFRA_STATUSES | {'mapping_error'} for r in records.values()):
                raise ValueError('Resolve development infrastructure/mapping before main slicing')
            check_stage_receipts(dev)
            prior = json.loads((dev / 'experiment_lock.json').read_text())
            if environment() != prior['stage_environments'].get(phase):
                raise ValueError('Main acquisition must use the development stage environment')
        return cfg
    from .calibration import require_calibration
    calibrated = require_calibration(cfg)
    if manifest == CORPUS / "main.jsonl":
        frozen = json.loads((ROOT / cfg["rq1_freeze_file"]).read_text())
        if (frozen["corpus_contract"] != corpus_contract() or frozen["policy"] != policy(cfg) or
                frozen.get("calibration_sha256") != file_digest(ROOT / cfg["rq1_calibration_file"]) or
                frozen.get("assessor_signature") != calibrated["assessor_signature"] or
                frozen.get('assessment_code_contract') != assessment_code_contract()):
            raise ValueError("Code, corpus or policy changed after the development freeze")
        if phase in {"query", "slice"} and environment() != frozen["stage_environments"].get(phase):
            raise ValueError(f"Restore the accepted development {phase} Python/package environment")
    return cfg


def initialize(config):
    verify_corpus()
    verify_implementation()
    write_json(config, json.loads((CORPUS / "config.example.json").read_text()), exclusive=True)
    print(f"RQ1_INIT_OK {config}")


def command(*argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        return out.returncode == 0, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def q_weights_cached(cache, cfg):
    snapshot = cache / 'hub' / ('models--' + cfg['query_model'].replace('/', '--')) / 'snapshots' / cfg['query_revision']
    index = snapshot / 'model.safetensors.index.json'
    try:
        shards = set(json.loads(index.read_text())['weight_map'].values())
        return bool(shards) and all((snapshot / name).is_file() and (snapshot / name).stat().st_size > 0 for name in shards)
    except (OSError, ValueError, KeyError):
        return False


def doctor(profile, config, work):
    checks = []
    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    for name, fn in (("corpus", verify_corpus), ("implementation", verify_implementation)):
        try:
            fn()
            add(name, True, "Verified")
        except (ValueError, OSError) as exc:
            add(name, False, exc)
    try:
        cfg = load_config(config)
        token_audit_valid(cfg)
        capability_valid(cfg)
        add("config_tokenizer_selector", True, "Current full-selector receipt and 30-input tokenizer audit")
    except (ValueError, OSError) as exc:
        cfg = None
        add("config_tokenizer_selector", False, exc)
    if profile == "local":
        add("gcc", *command("gcc", "--version"))
        add("compose", *command("docker", "compose", "version"))
    else:
        for name in ("torch", "vllm", "transformers"):
            add(name, importlib.util.find_spec(name) is not None, "Required on the Q host")
        try:
            import torch
            good = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
            capacity = torch.cuda.get_device_properties(0).total_memory / 2**30 if good else 0
            add("cuda_bf16_capacity", good and capacity >= 75, f"{capacity:.1f} GiB; use H100 80 GB")
        except (ImportError, RuntimeError) as exc:
            add("cuda_bf16_capacity", False, exc)
        cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
        existing = next(p for p in (cache, *cache.parents) if p.exists())
        free = shutil.disk_usage(existing).free / 2**30
        required = 15 if cfg and q_weights_cached(cache, cfg) else 100
        add("model_cache_space", free >= required, f"{free:.1f} GiB free; require >={required} GiB (lower limit only with all pinned Q shards cached)")
    from .calibration import require_calibration
    try:
        if cfg is None:
            raise ValueError("Config/technical checks pending")
        require_calibration(cfg)
        assessment_status = "accepted"
    except (ValueError, OSError) as exc:
        assessment_status = f"pending: {exc}"
    technical_ready = all(r["ok"] for r in checks)
    result = {"profile": profile, "ready": technical_ready and assessment_status == "accepted",
              "technical_ready": technical_ready, "assessor_calibration": assessment_status, "checks": checks,
              "utc": now(), "environment": environment(), "provenance": git_provenance(),
              "meaning": "Readiness only; no Q model load or experiment result."}
    write_json(work / "readiness.json", result)
    lines = [f"# RQ1 {profile} readiness", "", f"Technical ready: **{result['technical_ready']}**. Full experiment ready: **{result['ready']}**.",
             f"Assessor calibration: {assessment_status}", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    for row in checks:
        detail = row["detail"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {row['check']} | {'PASS' if row['ok'] else 'BLOCKED'} | {detail} |")
    (work / "readiness.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(result, indent=2))
    return result["technical_ready"]


def status(split, work):
    cases = load_cases(CORPUS / f"{split}.jsonl")
    expected = {s["run_id"] for s in run_specs(cases)}
    queries = index_jsonl(work / "queries.jsonl", "run_id")
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    witness_ok = True
    try:
        require_witnesses(work, cases)
    except ValueError:
        witness_ok = False
    complete = False
    try:
        for stage in ("query", "slice"):
            validate_terminal_records(work, stage, cases)
        check_stage_receipts(work)
        receipts = json.loads((work / "stage_receipts.json").read_text())
        complete = {"query", "slice"} <= receipts.keys()
    except (ValueError, OSError):
        pass
    return {"split": split, "cases": len(cases), "blocks": len({c.cluster_id for c in cases}),
            "planned_U": len(cases), "planned_F": len(cases),
            "planned_Q_and_slices": 0 if split == 'assessor_holdout' else len(expected),
            "all_witnesses_pass_current_sources": witness_ok,
            "queries_recorded": len(expected & queries.keys()),
            "slices_recorded": len(expected & slices.keys()), "real_inference_complete": complete,
            "assessment_report": str(work / "rq1_report.md") if (work / "rq1_report.md").exists() else "pending",
            "interpretation": ('Assessor-only sources: witnesses and calibration anchors; no Q/Joern experiment runs.'
                               if split == 'assessor_holdout' else
                               'Pending inference or assessment is not an inadequate finding.')}


def freeze(config, dev_work):
    cfg = check_acquisition_ready(CORPUS / "development.jsonl", config)
    cases = load_cases(CORPUS / "development.jsonl")
    lock = lock_inputs(dev_work, CORPUS / "development.jsonl", config, cases, phase="freeze")
    check_stage_receipts(dev_work)
    for stage in ("query", "slice"):
        validate_terminal_records(dev_work, stage, cases)
    receipts = json.loads((dev_work / "stage_receipts.json").read_text())
    if not {"query", "slice"} <= receipts.keys():
        raise ValueError("Both real stage receipts are required")
    from evidence_experiment.analysis import analyze
    # Recompute all judgements/provenance; a hand-written analysis.json is insufficient.
    report = analyze(cases, dev_work)
    from evidence_experiment.runner import INFRA_STATUSES
    if any(r["status"] in INFRA_STATUSES | {"mapping_error"} for r in report["run_evidence"]):
        raise ValueError("Resolve development infrastructure/mapping failures before freezing")
    proof = json.loads((dev_work / 'assessments.initial.provenance.json').read_text())
    snapshot_files = [dev_work / name for name in ('assessments.initial.jsonl',
        'assessments.initial.provenance.json', 'adjudications.jsonl', 'blind_review_packets.jsonl',
        'assessment_lock.json')]
    snapshot_files += [dev_work / proof[key] for key in ('requests_path', 'responses_path')]
    if any(p.is_symlink() or not p.resolve().is_relative_to(dev_work.resolve()) for p in snapshot_files):
        raise ValueError('Keep the complete development assessment evidence inside its stage directory')
    frozen = {"utc": now(), "corpus_contract": corpus_contract(), "policy": policy(cfg),
              'assessment_code_contract': assessment_code_contract(),
              'development_assessment_files': {str(p.resolve().relative_to(dev_work.parent.resolve())): file_digest(p)
                                               for p in snapshot_files},
              "stage_environments": lock["stage_environments"], "development_receipts": receipts,
              "development_analysis_sha256": file_digest(dev_work / "analysis.json"),
              "token_audit_sha256": file_digest(ROOT / cfg["rq1_token_audit_file"]),
              "capability_sha256": file_digest(ROOT / cfg["joern_capability_file"]),
              "assessment_mode": "Stateless calibrated AI plus source-support audit", "primary_rule": "repeat_0",
              "calibration_sha256": file_digest(ROOT / cfg["rq1_calibration_file"]),
              "assessor_signature": report["assessor_calibration_signature"],
              "development_summary": status("development", dev_work), "provenance": git_provenance()}
    write_json(ROOT / cfg["rq1_freeze_file"], frozen, exclusive=True)
    print("RQ1_FREEZE_OK: main assessment may now release its sealed acquisition")


def token_audit(config):
    from types import SimpleNamespace

    from transformers import AutoTokenizer

    from llmxcpg.inference.query_generator import QueryGenerator
    from llmxcpg.prompts import render_query_prompt
    verify_corpus()
    verify_implementation()
    cfg = load_config(config)
    tokenizer = AutoTokenizer.from_pretrained(cfg["query_model"], revision=cfg["query_revision"],
                                              trust_remote_code=False)
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
    result = {"utc": now(), "policy": policy(cfg), "corpus_contract": corpus_contract(),
              "environment": environment(), "records": records,
              "meaning": "Token lengths only; no Q weights, generated queries or adequacy results."}
    path = ROOT / cfg["rq1_token_audit_file"]
    write_json(path, result)
    print(f"RQ1_TOKEN_AUDIT_OK: {len(records)} prompts; {sum(r['fits'] for r in records)} fit; {path}")


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "init", "validate", "doctor", "status", "freeze", "acquisition-freeze", "token-audit", "conformance"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--split", choices=CORPUS_SPLITS, default="development")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--profile", choices=("local", "gpu"), default="local")
    args = parser.parse_args()
    work = args.work or Path("work/rq1-v7") / args.split
    if args.action == "verify":
        verify_implementation()
        print(json.dumps(verify_corpus(), indent=2))
        print("RQ1_VERIFY_OK")
    elif args.action == "init":
        initialize(args.config)
    elif args.action == "validate":
        verify_corpus()
        validate_witnesses(load_cases(CORPUS / f"{args.split}.jsonl"),
                           CORPUS / f"{args.split}.jsonl", CORPUS / "witness_plan.jsonl",
                           work / "witness_validation.jsonl")
        summary = status(args.split, work)
        write_json(work / "status.json", summary)
        print(json.dumps(summary, indent=2))
        if not summary["all_witnesses_pass_current_sources"]:
            raise SystemExit(1)
        print(f"RQ1_WITNESSES_OK {len(load_cases(CORPUS / f'{args.split}.jsonl'))}")
    elif args.action == "doctor":
        if not doctor(args.profile, args.config, work):
            raise SystemExit(1)
        print("RQ1_TECHNICAL_DOCTOR_OK: inspect assessor_calibration separately; no inference performed")
    elif args.action in {"freeze", "acquisition-freeze"}:
        from evidence_experiment.locks import work_lock
        with work_lock(work):
            if args.action == 'acquisition-freeze':
                acquisition_freeze(args.config)
            else:
                freeze(args.config, work)
    elif args.action == "token-audit":
        token_audit(args.config)
    elif args.action == "conformance":
        from .conformance import check
        if not check(args.config):
            raise SystemExit(1)
        print("RQ1_SELECTOR_CONFORMANCE_OK")
    else:
        print(json.dumps(status(args.split, work), indent=2))


if __name__ == "__main__":
    main()
