"""Acquire real Q and Joern traces on four Juliet cases before D calibration.

The probe never runs D or estimates evidence adequacy. Its outputs are
exploratory and must not be mixed with the later frozen main study.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import re
import shutil
import socket
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

# Let `python juliet_pilot/<script>.py` import the experiment from a checkout
# whose editable install predates the evidence_experiment package entry.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidence_experiment.review import build_queue, write_queue
from evidence_experiment.runner import extract_slices, generate_queries, load_config
from evidence_experiment.schema import DECOY_ARM, index_jsonl, load_cases, read_jsonl, run_specs

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
    engine = Path(__file__).parents[1] / "evidence_experiment"
    for path in (config, MANIFEST, Path(__file__), engine / "runner.py", engine / "review.py"):
        digest.update(path.read_bytes())
    for case in cases:
        for arm, source in sorted(case.sources.items()):
            digest.update(f"{case.case_id}|{arm}".encode())
            digest.update(source.encode())
    return digest.hexdigest()


def _function_lines(source: str) -> set[int]:
    """The generated case_entry body, excluding headers and the test driver."""
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("void case_entry("))
    stop = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("int main("))
    return {i + 1 for i in range(start, stop) if lines[i].strip()}


def fix_sites(vulnerable: str, fixed: str) -> tuple[list[int], list[int]]:
    """1-based lines that differ between the vulnerable and fixed sources."""
    u_lines, f_lines = [], []
    matcher = difflib.SequenceMatcher(a=vulnerable.splitlines(), b=fixed.splitlines(),
                                      autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            u_lines += range(i1 + 1, i2 + 1)
            f_lines += range(j1 + 1, j2 + 1)
    return u_lines, f_lines


def probe_readouts(cases, slices: dict[str, dict], repeats: int = 3) -> list[dict]:
    """Mechanical go/no-go observations; reviewers still decide adequacy.

    ``fix_site_selected_*`` is the discriminability readout: if the lines that
    distinguish the vulnerable and fixed programs are absent from a slice, its
    excerpt cannot show why one program is vulnerable and the other is not.
    """
    first = {(spec["case_id"], spec["arm"]): slices[spec["run_id"]]
             for spec in run_specs(cases, repeats) if spec["repeat"] == 0}
    result = []
    for case in cases:
        vulnerable = first[case.case_id, "U"]
        selected = set(vulnerable.get("slice_lines", [])) if vulnerable["status"] == "ok" else set()
        function_lines = _function_lines(case.sources["U"])
        elements = [{"role": element["role"], "id": element["id"],
                     "selected": bool(selected & set(element["lines"]))}
                    for element in case.referent["elements"]]
        row = {"case_id": case.case_id, "U_status": vulnerable["status"],
               "U_selected_function_lines": len(selected & function_lines),
               "U_function_lines": len(function_lines),
               "U_selected_fraction": len(selected & function_lines) / len(function_lines),
               "element_roles": elements,
               "referent_coverage": sum(e["selected"] for e in elements) / len(elements)}
        if DECOY_ARM in case.sources:
            fixed = first[case.case_id, DECOY_ARM]
            fixed_selected = (set(fixed.get("slice_lines", []))
                              if fixed["status"] == "ok" else set())
            fixed_function = _function_lines(case.sources[DECOY_ARM])
            u_sites, f_sites = fix_sites(case.sources["U"], case.sources[DECOY_ARM])
            row.update({
                "fixed_status": fixed["status"],
                "fixed_selected_fraction": len(fixed_selected & fixed_function) / len(fixed_function),
                "fix_site_lines_U": u_sites,
                "fix_site_selected_in_U": bool(selected & set(u_sites)) if u_sites else None,
                "fix_site_lines_fixed": f_sites,
                "fix_site_selected_in_fixed": (bool(fixed_selected & set(f_sites))
                                               if f_sites else None),
                "fixed_excerpt_text_identical": (
                    vulnerable.get("slice_code") == fixed.get("slice_code")
                    if vulnerable["status"] == fixed["status"] == "ok" else None),
            })
        result.append(row)
    return result


def probe(config: Path, work: Path, *, include_fixed_controls: bool = False) -> dict:
    blockers = preflight(config)
    if blockers:
        raise RuntimeError("Real Q/Joern probe is blocked:\n- " + "\n- ".join(blockers))
    cfg = load_config(config, require_detector=False)
    originals = load_cases(MANIFEST)
    cases = []
    for case in originals:
        if include_fixed_controls:
            # The fixed control enters as the case's F (decoy) arm with the same claim.
            prepared = next(row for row in read_jsonl(MANIFEST)
                            if row["case_id"] == case.case_id)
            source_path = prepared["control_source"]
            source = (MANIFEST.parent / source_path).read_text(encoding="utf-8")
            case = replace(case, sources={**case.sources, DECOY_ARM: source},
                           source_paths={**case.source_paths, DECOY_ARM: source_path})
        cases.append(case)
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
    packets, key = build_queue(cases, work, repeats)
    write_queue(work, packets, key, {"duplicate_fraction": 0.0, "seed": 0, "repeats": repeats})
    q = read_jsonl(work / "queries.jsonl")
    slices = read_jsonl(work / "slices.jsonl")
    expected = len(run_specs(cases, repeats))
    if len(q) != expected or len(slices) != expected:
        raise AssertionError("Probe has an incomplete query/slice grid")
    readouts = probe_readouts(cases, index_jsonl(work / "slices.jsonl", "run_id"), repeats)
    (work / "probe_readouts.json").write_text(json.dumps(readouts, indent=2) + "\n")
    report = {
        "kind": "real_Q_Joern_exploratory_probe",
        "research_results": False,
        "cases": len(cases),
        "fixed_variant_decoys": sum(DECOY_ARM in case.sources for case in cases),
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
    parser.add_argument("--include-fixed-controls", action="store_true")
    args = parser.parse_args()
    if args.work is None:
        print(json.dumps({"blockers": preflight(args.config)}, indent=2))
    else:
        print(json.dumps(probe(args.config, args.work,
                               include_fixed_controls=args.include_fixed_controls), indent=2))
