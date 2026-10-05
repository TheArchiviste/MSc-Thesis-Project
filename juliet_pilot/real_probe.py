"""Acquire real Q and Joern traces on four Juliet cases before D calibration.

The probe never runs D or estimates evidence adequacy. Its outputs are
exploratory and must not be mixed with the later frozen main study.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import socket
from collections import Counter
from pathlib import Path

from evidence_experiment.runner import extract_slices, generate_queries, load_config, review_packets
from evidence_experiment.schema import load_cases, read_jsonl, run_specs

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "generated" / "cases.jsonl"
Q_REVISION = "1f48ab60420d90277207394f1254d27d3375b07e"
D_REVISION = "91e6c0d0e8ea645047c237166b1403262d116a92"
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def preflight(config: Path, *, check_runtime: bool = True) -> list[str]:
    """Return actionable blockers without fetching weights or starting services."""
    cfg = json.loads(config.read_text(encoding="utf-8"))
    blockers = []
    if cfg.get("pipeline_commit") != "7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b":
        blockers.append("Pin the required original pipeline commit")
    if cfg.get("query_model") != "QCRI/LLMxCPG-Q" or cfg.get("query_revision") != Q_REVISION:
        blockers.append("Pin the released Q checkpoint revision")
    if cfg.get("detector_model") != "QCRI/LLMxCPG-D" or cfg.get("detector_revision") != D_REVISION:
        blockers.append("Record the released D adapter revision for later stages")
    if cfg.get("query_engine") != "vllm" or cfg.get("allow_dummy"):
        blockers.append("Use the local vLLM Q engine without dummy mode")
    if not cfg.get("exploratory_probe_only"):
        blockers.append("Label this run exploratory_probe_only")
    if not SHA256_DIGEST.fullmatch(cfg.get("joern_digest") or ""):
        blockers.append("Replace joern_digest with the deployed image's sha256 digest")
    if not MANIFEST.exists():
        blockers.append("Run juliet_pilot/prepare.py to generate the four-case manifest")
    else:
        cases = load_cases(MANIFEST)
        if len(cases) != 4 or any(c.paired for c in cases):
            blockers.append("This probe requires exactly the four baseline-only pilot cases")
    if check_runtime:
        for package in ("torch", "transformers", "vllm"):
            if importlib.util.find_spec(package) is None:
                blockers.append(f"Install {package} in the model runtime")
        if shutil.which("nvidia-smi") is None:
            blockers.append("A visible NVIDIA GPU is needed for this vLLM configuration")
        if importlib.util.find_spec("torch") is not None:
            try:
                import torch

                if not torch.cuda.is_available():
                    blockers.append("PyTorch cannot see a CUDA GPU")
                else:
                    vram_gib = torch.cuda.get_device_properties(0).total_memory / 2**30
                    if vram_gib < 70:
                        blockers.append(
                            f"GPU 0 has {vram_gib:.1f} GiB; this unquantized Q probe needs "
                            "an approximately 80 GB GPU with runtime headroom"
                        )
                    if not torch.cuda.is_bf16_supported():
                        blockers.append("GPU 0 does not support the BF16 model runtime")
            except (OSError, RuntimeError, ImportError) as exc:
                blockers.append(f"Could not inspect CUDA runtime: {exc}")
        host, port = cfg.get("joern_host", "127.0.0.1"), cfg.get("joern_port", 8080)
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                pass
        except (OSError, TypeError, ValueError):
            blockers.append(f"Joern is not reachable at {host}:{port}")
    return blockers


def _fingerprint(config: Path, cases) -> str:
    digest = hashlib.sha256()
    for path in (config, MANIFEST, Path(__file__), Path(__file__).parents[1] /
                 "evidence_experiment" / "runner.py"):
        digest.update(path.read_bytes())
    for case in cases:
        digest.update(case.case_id.encode())
        digest.update(case.sources["U"].encode())
    return digest.hexdigest()


def probe(config: Path, work: Path) -> dict:
    blockers = preflight(config)
    if blockers:
        raise RuntimeError("Real Q/Joern probe is blocked:\n- " + "\n- ".join(blockers))
    cfg = load_config(config)
    cases = load_cases(MANIFEST)
    work.mkdir(parents=True, exist_ok=True)
    fingerprint = _fingerprint(config, cases)
    lock = work / "probe_lock.json"
    if lock.exists():
        if json.loads(lock.read_text())["fingerprint"] != fingerprint:
            raise ValueError("Probe inputs changed; use a fresh --work directory")
    else:
        lock.write_text(json.dumps({"fingerprint": fingerprint,
                                    "kind": "real_Q_Joern_exploratory_probe"}, indent=2) + "\n")
    repeats = 3
    generate_queries(cases, work, cfg, repeats=repeats)
    extract_slices(cases, work, cfg, repeats=repeats)
    packets = review_packets(cases, work, repeats=repeats)
    (work / "blind_review_packets.jsonl").write_text(
        "".join(json.dumps(packet, sort_keys=True) + "\n" for packet in packets))
    q = read_jsonl(work / "queries.jsonl")
    slices = read_jsonl(work / "slices.jsonl")
    expected = len(run_specs(cases, repeats))
    if len(q) != expected or len(slices) != expected:
        raise AssertionError("Probe has an incomplete query/slice grid")
    report = {
        "kind": "real_Q_Joern_exploratory_probe",
        "research_results": False,
        "cases": len(cases),
        "repeats": repeats,
        "query_status": dict(Counter(row["status"] for row in q)),
        "slice_status": dict(Counter(row["status"] for row in slices)),
        "blind_packets": len(packets),
        "query_revision": cfg["query_revision"],
        "joern_digest": cfg["joern_digest"],
        "detector_executed": False,
        "adequacy_assessed": False,
    }
    (work / "probe_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.work is None:
        print(json.dumps({"blockers": preflight(args.config)}, indent=2))
    else:
        print(json.dumps(probe(args.config, args.work), indent=2))
