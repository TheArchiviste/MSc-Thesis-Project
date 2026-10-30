"""RQ1 excerpt-only packets and honest single-assessor validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .schema import append_jsonl, index_jsonl, run_specs

_LINE_LABEL = re.compile(r"(?m)^L(\d+):")

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

CAUSAL_WORDS = frozenset({
    "because", "since", "exceeds", "exceeding", "beyond", "without", "unchecked",
    "missing", "terminator", "nul", "null", "bound", "bounds", "guard", "check",
    "checked", "size", "length", "larger", "smaller", "freed", "after", "before",
    "overflow", "overflows", "underflow", "invalid", "unsafe", "dangling",
})

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
    """Render a candidate claim, never its causal explanation."""
    claim = referent.get("review_claim")
    if isinstance(claim, dict):
        problem = claim_problem(referent)
        if problem:
            raise ValueError(problem)
        return CLAIM_TEMPLATE.format(article=CLAIM_CLASSES[claim["flaw_class"]],
                                     flaw_class=claim["flaw_class"],
                                     operation=claim["operation"].strip())
    raise ValueError("A structured source-only review claim is required")

def packet_lines(code: str) -> set[int]:
    return {int(n) for n in _LINE_LABEL.findall(code)}


def numbered_view(source, rendered_lines):
    if (not rendered_lines or sorted(set(rendered_lines)) != rendered_lines or
            any(type(n) is not int or not 1 <= n <= len(source.splitlines()) for n in rendered_lines)):
        raise ValueError("Packet has invalid or incomplete enclosing-block coordinates")
    lines, out, previous = source.splitlines(), [], 0
    for n in rendered_lines:
        if previous and n > previous + 1:
            out.append("...")
        out.append(f"L{n}: {lines[n - 1]}")
        previous = n
    return "\n".join(out)


def packet_index(cases, work: Path, repeats=1):
    from llmxcpg.slicing.reconstruction import context_lines, reconstruct_code_from_lines
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    by_case = {c.case_id: c for c in cases}
    packets, joins = {}, {}
    for spec in run_specs(cases, repeats):
        slc = slices.get(spec["run_id"])
        if slc is None or slc["status"] != "ok":
            continue
        case = by_case[spec["case_id"]]
        source = case.source_for(spec["arm"])
        if (context_lines(source, slc["slice_lines"]) != slc["rendered_lines"] or
                reconstruct_code_from_lines(source, slc["slice_lines"]) != slc["slice_code"]):
            raise ValueError("Stored excerpt does not match its source/line mapping")
        view, claim = numbered_view(source, slc["rendered_lines"]), render_claim(case.referent)
        from rq1.assessment_protocol import public_packet
        packet = public_packet(claim, view)
        rid = packet["review_id"]
        packets[rid] = packet
        joins[spec["run_id"]] = rid
    return packets, joins


def build_queue(cases, work, repeats=1):
    from rq1.sealing import require_release
    require_release(work)
    packets, joins = packet_index(cases, work, repeats)
    path = work / "blind_review_packets.jsonl"
    if path.exists():
        if index_jsonl(path, "review_id") != packets:
            raise ValueError("Issued packets changed; preserving the original queue")
        return
    for rid in sorted(packets):
        append_jsonl(path, packets[rid])
    path.touch(exist_ok=True)
    for spec in run_specs(cases, repeats):
        if spec["run_id"] in joins:
            append_jsonl(work / "review_key.jsonl", {**spec, "review_id": joins[spec["run_id"]]})


def validate_assessment(row, packet, *, expected_context="excerpt_only_stateless"):
    from rq1.assessment_protocol import (
        ASSUMPTIONS,
        ORIGIN,
        PROOF_CATEGORIES,
        contract,
        utc_stamp,
        validate_identity,
    )
    if row.get("assessor_id") != "calibrated_ai_assessor" or row.get("assessment_origin") != ORIGIN:
        raise ValueError("Use the explicitly labelled AI-assisted assessor identity")
    if row.get("assessment_context") != expected_context:
        raise ValueError("The primary assessment must use a fresh excerpt-only context")
    if row.get("assessment_contract_sha256") != contract()["contract_sha256"]:
        raise ValueError("Assessment uses a different rubric or assumption contract")
    validate_identity(row.get("assessor_identity"))
    stamp = utc_stamp(row.get("assessed_utc"))
    if row.get("adequacy") not in {"adequate", "inadequate", "uncertain"}:
        raise ValueError("Assessment is missing or not terminal")
    if not isinstance(row.get("explanation"), str) or not row["explanation"].strip():
        raise ValueError("Explain each assessment from the visible excerpt")
    for key in ("cited_lines", "premises", "relationships", "assumptions_used", "missing_context", "limitations"):
        if not isinstance(row.get(key), list):
            raise ValueError(f"Assessment field {key} is missing or malformed")  # noqa: TRY004
    visible = packet_lines(packet["code"])
    def citations(values):
        if (not isinstance(values, list) or any(type(n) is not int for n in values) or
                len(values) != len(set(values)) or not set(values) <= visible):
            raise ValueError("Assessment cites a hidden or invalid line")
    citations(row["cited_lines"])
    if (any(not isinstance(v, str) for v in row['assumptions_used']) or
            len(row['assumptions_used']) != len(set(row['assumptions_used'])) or
            not set(row["assumptions_used"]) <= ASSUMPTIONS.keys()):
        raise ValueError("An unpermitted assumption supplies hidden context")
    for premise in row["premises"]:
        if (not isinstance(premise, dict) or set(premise) != {'category', 'statement', 'cited_lines', 'assumption_ids'} or
                premise.get("category") not in PROOF_CATEGORIES or
                not isinstance(premise.get('statement'), str) or not premise['statement'].strip() or
                not isinstance(premise.get("assumption_ids"), list) or
                any(not isinstance(v, str) for v in premise['assumption_ids']) or
                len(premise['assumption_ids']) != len(set(premise['assumption_ids'])) or
                not set(premise["assumption_ids"]) <= ASSUMPTIONS.keys()):
            raise ValueError("A premise needs its category, visible support and permitted assumption IDs")
        citations(premise.get("cited_lines"))
        if not premise["cited_lines"]:
            raise ValueError("Case-specific premises require visible source citations")
    if any(not isinstance(value, str) or not value.strip() for key in
           ("relationships", "missing_context", "limitations") for value in row[key]):
        raise ValueError("Relationships, missing context and limitations need nonempty text")
    if row["adequacy"] == "adequate":
        categories = {p["category"] for p in row["premises"]}
        if not {"capacity", "extent", "binding", "violation"} <= categories or not row["relationships"] or not row["cited_lines"]:
            raise ValueError("Adequacy needs cited capacity, extent, binding and violation premises")
    if row["adequacy"] == "uncertain" and not (row["limitations"] or row["missing_context"]):
        raise ValueError("Identify the unresolved issue in an uncertain assessment")
    return stamp


def assessments(path, packets):
    if not path.is_file():
        raise FileNotFoundError(path)
    rows = index_jsonl(path, "review_id")
    if rows.keys() != packets.keys():
        raise ValueError("Assess every shown unique packet exactly once, with no foreign packets")
    for rid, row in rows.items():
        validate_assessment(row, packets[rid])
    return rows
