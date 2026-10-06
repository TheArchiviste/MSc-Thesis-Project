"""Blind review queue: templated claims, fixed-variant decoys and duplicates.

Reviewers receive only ``blind_review_packets.jsonl``. The private
``review_key.jsonl`` and the work directory stay with the study coordinator.

* **Claims** use one fixed granularity: a flaw class from a controlled
  vocabulary plus the operation where it manifests. They never state the
  causal explanation, sizes, bounds or line numbers.
* **Decoys** are the documented fixed variant of a case (arm ``F``), run
  through the same Q -> Joern stages and shown with the same claim. An
  ``adequate`` rating on a decoy is a false adequacy.
* **Duplicates** re-issue a seeded sample of evidence packets with shifted
  line labels and a new review id, to estimate rater test-retest agreement.

Packet order is by review id (a content hash), which interleaves cases, arms,
decoys and duplicates. The issued queue is frozen: re-running ``packets``
with different settings refuses to overwrite it.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from .schema import DECOY_ARM, Case, digest, index_jsonl, read_jsonl, run_specs

# Controlled flaw-class vocabulary with the article used in the rendered claim.
CLAIM_CLASSES: dict[str, str] = {
    "stack buffer overflow": "a",
    "heap buffer overflow": "a",
    "buffer underwrite": "a",
    "buffer over-read": "a",
    "buffer under-read": "a",
    "out-of-bounds write": "an",
    "out-of-bounds read": "an",
    "integer overflow": "an",
    "integer underflow": "an",
    "use after free": "a",
    "double free": "a",
}
CLAIM_TEMPLATE = "Does this excerpt justify {article} {flaw_class} at the {operation}?"
MAX_OPERATION_WORDS = 5
# Words that would smuggle the causal explanation into the operation field.
CAUSAL_WORDS = frozenset({
    "because", "since", "exceeds", "exceeding", "beyond", "without", "unchecked",
    "missing", "terminator", "nul", "null", "bound", "bounds", "guard", "check",
    "checked", "size", "length", "larger", "smaller", "freed", "after", "before",
    "overflow", "overflows", "underflow", "invalid", "unsafe", "dangling",
})
DEFAULT_CLAIM = "Does this excerpt justify a vulnerability? Explain the mechanism."
EVIDENCE_ARMS = ("U", "TM", "TN")

_LINE_LABEL = re.compile(r"(?m)^L(\d+):")


def claim_problem(referent: dict[str, Any]) -> str | None:
    """Return why a case's review claim is unusable for a final run, else None."""
    claim = referent.get("review_claim")
    if not isinstance(claim, dict):
        return ("review_claim must be {\"flaw_class\": ..., \"operation\": ...} "
                "so every case is asked at the same granularity")
    flaw_class, operation = claim.get("flaw_class"), claim.get("operation")
    if flaw_class not in CLAIM_CLASSES:
        return f"flaw_class must be one of: {', '.join(sorted(CLAIM_CLASSES))}"
    if not isinstance(operation, str) or not operation.strip():
        return "operation must name the statement or call, e.g. 'memcpy call'"
    words = operation.split()
    if len(words) > MAX_OPERATION_WORDS:
        return f"operation must have at most {MAX_OPERATION_WORDS} words"
    if re.search(r"\d", operation):
        return "operation must not contain numbers (sizes, bounds or lines)"
    leaked = sorted({w.strip(".,;:()").lower() for w in words} & CAUSAL_WORDS)
    if leaked:
        return f"operation must not explain the mechanism (remove: {', '.join(leaked)})"
    if set(claim) - {"flaw_class", "operation"}:
        return "review_claim may only contain flaw_class and operation"
    return None


def render_claim(referent: dict[str, Any]) -> str:
    """Render the reviewer question. Legacy free-text claims are kept verbatim."""
    claim = referent.get("review_claim")
    if isinstance(claim, dict):
        problem = claim_problem(referent)
        if problem:
            raise ValueError(problem)
        return CLAIM_TEMPLATE.format(article=CLAIM_CLASSES[claim["flaw_class"]],
                                     flaw_class=claim["flaw_class"],
                                     operation=claim["operation"].strip())
    if isinstance(claim, str) and claim.strip():
        return claim
    return DEFAULT_CLAIM


def numbered_view(source: str, rendered_lines: list[int], offset: int = 0) -> str:
    lines = source.splitlines()
    numbered: list[str] = []
    last = 0
    for n in rendered_lines:
        if last and n - last > 1:
            numbered.append("...")
        numbered.append(f"L{n + offset}: {lines[n - 1]}")
        last = n
    return "\n".join(numbered)


def packet_lines(code: str) -> set[int]:
    return {int(n) for n in _LINE_LABEL.findall(code)}


def packet_index(cases: list[Case], work: Path, repeats: int = 3
                 ) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Return primary blind packets and the private run-to-review join key."""
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    by_case = {case.case_id: case for case in cases}
    packets: dict[str, dict[str, str]] = {}
    joins: dict[str, str] = {}
    for spec in run_specs(cases, repeats):
        slc = slices.get(spec["run_id"])
        if slc is None or slc["status"] != "ok":
            continue
        case = by_case[spec["case_id"]]
        view = numbered_view(case.source_for(spec["arm"]), slc["rendered_lines"])
        claim = render_claim(case.referent)
        review_id = digest(claim + "\n" + view)
        packets[review_id] = {"review_id": review_id, "claim": claim, "code": view}
        joins[spec["run_id"]] = review_id
    return packets, joins


def _duplicate_id(seed: int, original: str, offset: int, claim: str, view: str) -> str:
    return digest(f"duplicate|{seed}|{original}|{offset}\n{claim}\n{view}")


def build_queue(cases: list[Case], work: Path, repeats: int = 3, *,
                duplicate_fraction: float = 0.0, seed: int = 0
                ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Return (blind packets, private key) for the complete review queue."""
    if not 0 <= duplicate_fraction <= 1:
        raise ValueError("duplicate_fraction must be in [0, 1]")
    packets, joins = packet_index(cases, work, repeats)
    arms_for: dict[str, set[str]] = {}
    for spec in run_specs(cases, repeats):
        rid = joins.get(spec["run_id"])
        if rid:
            arms_for.setdefault(rid, set()).add(spec["arm"].split("_")[0])
    key: list[dict[str, Any]] = []
    for rid in sorted(packets):
        arms = arms_for[rid]
        kind = ("evidence_and_decoy" if DECOY_ARM in arms and arms - {DECOY_ARM} else
                "decoy" if arms == {DECOY_ARM} else "evidence")
        key.append({"review_id": rid, "kind": kind, "duplicate_of": None, "line_offset": 0})
    candidates = sorted(rid for rid, arms in arms_for.items()
                        if arms & set(EVIDENCE_ARMS) and DECOY_ARM not in arms)
    rng = random.Random(seed)
    k = round(duplicate_fraction * len(candidates))
    if duplicate_fraction > 0 and candidates:
        k = max(1, k)
    queue = dict(packets)
    for original in sorted(rng.sample(candidates, k)):
        packet = packets[original]
        offset = rng.randint(10, 90)
        view = _shift(packet["code"], offset)
        rid = _duplicate_id(seed, original, offset, packet["claim"], view)
        queue[rid] = {"review_id": rid, "claim": packet["claim"], "code": view}
        key.append({"review_id": rid, "kind": "duplicate", "duplicate_of": original,
                    "line_offset": offset})
    ordered = [queue[rid] for rid in sorted(queue)]
    return ordered, sorted(key, key=lambda row: row["review_id"])


def _shift(code: str, offset: int) -> str:
    return _LINE_LABEL.sub(lambda m: f"L{int(m.group(1)) + offset}:", code)


def write_queue(work: Path, packets: list[dict[str, str]], key: list[dict[str, Any]],
                settings: dict[str, Any]) -> Path:
    """Write the issued queue once; identical regeneration is allowed."""
    outputs = {
        work / "blind_review_packets.jsonl":
            "".join(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n" for p in packets),
        work / "review_key.jsonl":
            "".join(json.dumps({**row, "settings": settings}, sort_keys=True) + "\n"
                    for row in key),
    }
    for path, text in outputs.items():
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise ValueError(f"{path.name} was already issued with different content; "
                             "the review queue is frozen once sent to reviewers")
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    return work / "blind_review_packets.jsonl"


def duplicate_packets(cases: list[Case], work: Path, repeats: int = 3
                      ) -> dict[str, dict[str, Any]]:
    """Reconstruct and verify duplicate packets recorded in the private key."""
    path = work / "review_key.jsonl"
    rows = [row for row in read_jsonl(path) if row.get("kind") == "duplicate"]
    if not rows:
        return {}
    packets, _ = packet_index(cases, work, repeats)
    seeds = {row["settings"]["seed"] for row in rows}
    if len(seeds) != 1:
        raise ValueError("review_key.jsonl mixes duplicate seeds")
    seed = seeds.pop()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        original = packets.get(row["duplicate_of"])
        if original is None:
            raise ValueError(f"Duplicate {row['review_id']} refers to an unknown packet")
        view = _shift(original["code"], row["line_offset"])
        rid = _duplicate_id(seed, row["duplicate_of"], row["line_offset"],
                            original["claim"], view)
        if rid != row["review_id"]:
            raise ValueError(f"review_key.jsonl does not match the evidence for {row['review_id']}")
        result[rid] = {"review_id": rid, "claim": original["claim"], "code": view,
                       "duplicate_of": row["duplicate_of"], "line_offset": row["line_offset"]}
    return result


def review_packets(cases: list[Case], work: Path, repeats: int = 3) -> list[dict[str, str]]:
    """Primary blind packets (evidence and decoys), without duplicates."""
    packets, _ = packet_index(cases, work, repeats)
    return sorted(packets.values(), key=lambda p: p["review_id"])
