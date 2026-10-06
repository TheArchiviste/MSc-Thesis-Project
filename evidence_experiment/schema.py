"""Strict, portable input and run manifests for the evidence experiment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARMS = ("U", "TM", "TN", "TM_fixed", "TN_fixed", "U_rule", "TM_rule", "TN_rule", "F")
# F is the documented fixed (safe) variant of the same template. It is a blind
# review decoy and discriminability check, never part of the RQ1/RQ2 estimands.
DECOY_ARM = "F"
SOURCE_KEYS = ("U", "TM", "TN", DECOY_ARM)
REQUIRED_CHECKS = ("compile", "benign_behavior", "trigger", "mechanism_preserved",
                   "line_map", "match", "control_purity")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def index_jsonl(path: Path, key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        k = record[key]
        if k in result:
            raise ValueError(f"Duplicate {key}={k!r} in {path}")
        result[k] = record
    return result


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Case:
    case_id: str
    cluster_id: str
    cwe: str
    sources: dict[str, str]
    source_paths: dict[str, str]
    referent: dict[str, Any]
    rule_queries: dict[str, list[str]]
    validation: dict[str, str]
    control_in_slice: bool | None
    operator: str | None

    @property
    def paired(self) -> bool:
        return "TM" in self.sources and "TN" in self.sources

    @property
    def admissible(self) -> bool:
        return self.paired and all(
            self.validation.get(k) in ({"pass", "not_applicable"} if k == "benign_behavior"
                                       else {"pass"})
            for k in REQUIRED_CHECKS
        )

    def source_for(self, arm: str) -> str:
        return self.sources[arm.split("_")[0]]


def load_cases(manifest: Path) -> list[Case]:
    """Load a human-curated corpus, including misses and baseline failures.

    Transform validity is recorded as evidence; a declared 'pass' is never
    taken to be a proof of semantic equivalence. Validation artefacts should
    be retained with the dataset. Paths are relative to the manifest.
    """
    cases: list[Case] = []
    seen: set[str] = set()
    for obj in read_jsonl(manifest):
        cid = obj["case_id"]
        if cid in seen:
            raise ValueError(f"Duplicate case_id: {cid}")
        seen.add(cid)
        paths = obj["sources"]
        if "U" not in paths or ("TM" in paths) != ("TN" in paths):
            raise ValueError(f"{cid}: require U and either both transformed sources or neither")
        if set(paths) - set(SOURCE_KEYS):
            raise ValueError(f"{cid}: sources may only contain {', '.join(SOURCE_KEYS)}")
        sources = {arm: (manifest.parent / path).read_text(encoding="utf-8")
                   for arm, path in paths.items()}
        if not obj.get("cluster_id") or not obj.get("cwe"):
            raise ValueError(f"{cid}: missing cluster_id or cwe")
        referent = obj.get("referent", {})
        if not referent.get("elements") or not referent.get("relations"):
            raise ValueError(f"{cid}: independent element and relation referent required")
        for element in referent["elements"]:
            if not element.get("id") or not element.get("role") or not element.get("lines"):
                raise ValueError(f"{cid}: element requires id, role and original source lines")
            if "TM" in paths and any(arm not in element.get("mapped_lines", {})
                                     for arm in ("TM", "TN")):
                raise ValueError(f"{cid}: transformed mechanism elements require both line mappings")
        validation = obj.get("validation", {})
        if set(validation.values()) - {"pass", "fail", "indeterminate", "not_applicable"}:
            raise ValueError(f"{cid}: invalid validation status")
        if any(value == "not_applicable" and key != "benign_behavior"
               for key, value in validation.items()):
            raise ValueError(f"{cid}: only benign_behavior may be not_applicable")
        if validation.get("benign_behavior") == "not_applicable" and not obj.get("benign_reason"):
            raise ValueError(f"{cid}: benign_reason required for not_applicable")
        rules = obj.get("rule_queries", {})
        if rules == []:  # older baseline-only manifests
            rules = {}
        if (not isinstance(rules, dict) or set(rules) - {"U", "TM", "TN"} or
                any(not isinstance(items, list) or not items or
                    not all(isinstance(item, str) for item in items)
                    for items in rules.values()) or
                (not {"TM", "TN"} <= set(paths) and set(rules) - {"U"})):
            raise ValueError(f"{cid}: rule_queries must map available arms to nonempty query lists")
        cases.append(Case(cid, obj["cluster_id"], obj["cwe"], sources, paths,
                          referent, rules, validation,
                          obj.get("control_in_slice"), obj.get("operator")))
    return cases


def run_specs(cases: list[Case], repeats: int = 3) -> list[dict[str, Any]]:
    """Enumerate all baseline cases; paired arms only for admissible pairs.

    A documented fixed variant (F) runs once through regenerated Q and Joern
    so its excerpt can enter the blind queue as a decoy.
    """
    if repeats < 1 or repeats % 2 != 1:
        raise ValueError("repeats must be a positive odd number")
    specs: list[dict[str, Any]] = []
    for case in cases:
        arms = ["U"] + (["TM", "TN", "TM_fixed", "TN_fixed"] if case.admissible else [])
        arms += [f"{base}_rule" for base in ("U", "TM", "TN")
                 if base in case.rule_queries and (base == "U" or case.admissible)]
        if DECOY_ARM in case.sources:
            arms.append(DECOY_ARM)
        for arm in arms:
            for rep in range(repeats if arm in ("U", "TM", "TN") else 1):
                source = case.source_for(arm)
                identity = f"{case.case_id}|{arm}|{rep}|{digest(source)}"
                specs.append({"run_id": digest(identity), "case_id": case.case_id,
                              "cluster_id": case.cluster_id, "cwe": case.cwe,
                              "arm": arm, "repeat": rep, "source_sha256": digest(source),
                              "source_path": case.source_paths[arm.split("_")[0]],
                              "operator": case.operator})
    return specs
