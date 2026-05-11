"""Dataset loaders for FormAI-v2, PrimeVul, SVEN, ReposVul.

These are intentionally minimal: HuggingFace `datasets` does the heavy lifting
where it can, and for SVEN/ReposVul we provide a small adapter because their
on-disk formats vary.

Each loader returns an iterable of dicts with the schema the bootstrap loop
expects:
    {"id": str, "code": str, "cwe": str, "is_vulnerable": bool, "location_hint": str}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Iterator

from llmxcpg.data.esbmc_cwe_mapping import esbmc_error_to_cwe


logger = logging.getLogger(__name__)


def load_formai_v2(path: str | Path) -> Iterator[dict]:
    """Iterate over FormAI-v2 (Tihanyi et al., 2024).

    Expected JSONL schema (after preprocessing):
        {"file": "...", "code": "...", "esbmc_verdict": "...", "verified": "..."}

    We use the ESBMC verdict text to map to a CWE; safe samples are those
    where ESBMC's `verified` field is `"true"` and we still know which CWE
    family the assertion targeted.
    """
    path = Path(path)
    with path.open() as f:
        for i, line in enumerate(f):
            rec = json.loads(line)
            verdict = rec.get("esbmc_verdict", "")
            cwe = esbmc_error_to_cwe(verdict)
            if cwe is None:
                continue
            is_vuln = bool(rec.get("vulnerable", verdict and "violated" in verdict.lower()))
            yield {
                "id": f"formai_{rec.get('file', i)}",
                "code": rec["code"],
                "cwe": cwe,
                "is_vulnerable": is_vuln,
                "location_hint": "",
            }


def load_primevul(path: str | Path, split: str = "train") -> Iterator[dict]:
    """Iterate over the PrimeVul dataset.

    Expected JSONL schema (matches the official release):
        {
            "idx": ..., "func": "...source...", "target": 0|1,
            "cwe": ["CWE-119", ...], "project": "...", "commit_id": "..."
        }
    `target=1` is vulnerable.
    """
    path = Path(path)
    with path.open() as f:
        for line in f:
            rec = json.loads(line)
            cwes = rec.get("cwe") or []
            cwe = cwes[0] if cwes else None
            if cwe is None:
                continue
            yield {
                "id": f"primevul_{rec.get('idx', '')}",
                "code": rec["func"],
                "cwe": cwe,
                "is_vulnerable": bool(rec.get("target", 0)),
                "location_hint": "",
            }


def load_sven(path: str | Path) -> Iterator[dict]:
    """Iterate over the SVEN dataset (He & Vechev, 2023).

    SVEN ships as paired vulnerable/patched JSONL files keyed by CWE.
    `path` should point at a directory containing them; we walk it.
    """
    path = Path(path)
    if not path.is_dir():
        raise NotADirectoryError(f"SVEN loader expects a directory, got: {path}")

    for jsonl_file in sorted(path.glob("*.jsonl")):
        # Filename convention: cwe-119.jsonl, cwe-190.jsonl, ...
        cwe_token = jsonl_file.stem.upper().replace("CWE-", "CWE-")
        with jsonl_file.open() as f:
            for i, line in enumerate(f):
                rec = json.loads(line)
                # Each record typically has both vulnerable and fixed code.
                if "vul_func" in rec:
                    yield {
                        "id": f"sven_{cwe_token}_{i}_vul",
                        "code": rec["vul_func"],
                        "cwe": cwe_token,
                        "is_vulnerable": True,
                        "location_hint": "",
                    }
                if "fixed_func" in rec:
                    yield {
                        "id": f"sven_{cwe_token}_{i}_fix",
                        "code": rec["fixed_func"],
                        "cwe": cwe_token,
                        "is_vulnerable": False,
                        "location_hint": "",
                    }


def load_reposvul(path: str | Path) -> Iterator[dict]:
    """Iterate over the ReposVul dataset (Wang et al., 2024).

    ReposVul ships as a JSONL of repository-level CVE entries; each entry has
    a list of files with vulnerable/patched pairs. We flatten to per-file
    samples. Caller should sample for balance — the loader does not.
    """
    path = Path(path)
    with path.open() as f:
        for line in f:
            rec = json.loads(line)
            cwe = (rec.get("cwe") or [None])[0]
            if cwe is None:
                continue
            for file_entry in rec.get("files", []):
                if "vulnerable_code" in file_entry:
                    yield {
                        "id": f"reposvul_{rec.get('cve_id', '')}_{file_entry.get('path', '')}_vul",
                        "code": file_entry["vulnerable_code"],
                        "cwe": cwe,
                        "is_vulnerable": True,
                        "location_hint": "",
                    }
                if "patched_code" in file_entry:
                    yield {
                        "id": f"reposvul_{rec.get('cve_id', '')}_{file_entry.get('path', '')}_fix",
                        "code": file_entry["patched_code"],
                        "cwe": cwe,
                        "is_vulnerable": False,
                        "location_hint": "",
                    }
