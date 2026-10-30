"""Portable U/F manifests and append-only observations for RQ1."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

IMPLEMENTATION_ID = "rq1-v2"
ARMS = ("U", "F")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def index_jsonl(path: Path, key: str) -> dict:
    result = {}
    for row in read_jsonl(path):
        value = row[key]
        if value in result:
            raise ValueError(f"Duplicate {key}={value!r} in {path}")
        result[value] = row
    return result


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value, *, exclusive=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class Case:
    case_id: str
    cluster_id: str
    cwe: str
    sources: dict[str, str]
    source_paths: dict[str, str]
    referent: dict

    def source_for(self, arm: str) -> str:
        return self.sources[arm]


def load_cases(manifest: Path) -> list[Case]:
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    rows = index_jsonl(manifest, "case_id")
    if not rows:
        raise ValueError("The RQ1 manifest is empty")
    cases = []
    for row in rows.values():
        if set(row["sources"]) != set(ARMS):
            raise ValueError("RQ1 requires exactly U and F; transformed arms are unsupported")
        ref = row["referent"]
        if not ref.get("elements") or not ref.get("relations"):
            raise ValueError("Source-grounded elements and relationships are required")
        if not row.get("cluster_id") or not row.get("cwe"):
            raise ValueError("A generator block and upstream CWE are required")
        for element in ref["elements"]:
            if not element.get("id") or not element.get("role") or not element.get("lines"):
                raise ValueError("Reference elements need an id, role and source lines")
        sources = {a: (manifest.parent / p).read_text(encoding="utf-8")
                   for a, p in row["sources"].items()}
        cases.append(Case(row["case_id"], row["cluster_id"], row["cwe"], sources,
                          row["sources"], ref))
    return cases


def run_specs(cases: list[Case], repeats: int = 1) -> list[dict]:
    if repeats != 1:
        raise ValueError("RQ1 has one primary run; repeats must equal 1")
    return [{"run_id": digest(f"{IMPLEMENTATION_ID}|{c.case_id}|{a}|0|{digest(c.sources[a])}"),
             "case_id": c.case_id, "cluster_id": c.cluster_id, "cwe": c.cwe,
             "arm": a, "repeat": 0, "source_sha256": digest(c.sources[a]),
             "source_path": c.source_paths[a]}
            for c in cases for a in ARMS]
