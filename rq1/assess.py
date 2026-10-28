"""Prepare an honest single-AI-assessor queue and audit delayed consistency."""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evidence_experiment.review import packet_index
from evidence_experiment.schema import append_jsonl, load_cases, read_jsonl, run_specs

from .setup import CORPUS, ROOT, write_json

SEED = 20261027


def prepare(split, work):
    """Order unchanged packets; never fill in a judgement without seeing an excerpt."""
    cases = load_cases(CORPUS / f"{split}.jsonl")
    packets, joins = packet_index(cases, work, 1)
    issued = read_jsonl(work / "blind_review_packets.jsonl")
    if {r["review_id"] for r in issued} != packets.keys():
        raise ValueError("Issue packets with --repeats 1 --duplicate-fraction 0 first")
    paths = [work / name for name in ("assessment_order.jsonl", "assessments.template.jsonl",
                                      "adjudications.template.jsonl", "assessment_order_metadata.json")]
    if any(p.exists() for p in paths):
        raise FileExistsError("Assessment forms already exist; preserving the issued order")
    case_sets = {rid: set() for rid in packets}
    for spec in run_specs(cases, 1):
        if spec["run_id"] in joins:
            case_sets[joins[spec["run_id"]]].add(spec["case_id"])
    remaining = sorted(packets)
    random.Random(SEED).shuffle(remaining)
    ordered, previous, violations = [], set(), 0
    while remaining:
        index = next((i for i, rid in enumerate(remaining) if not case_sets[rid] & previous), 0)
        rid = remaining.pop(index)
        violations += bool(case_sets[rid] & previous)
        ordered.append(rid)
        previous = case_sets[rid]
    for rid in ordered:
        append_jsonl(paths[0], packets[rid])
        append_jsonl(paths[1], {"review_id": rid, "assessor_id": "codex_ai_assessor",
                              "assessment_origin": "AI-assisted; no independent human validation",
                              "assessed_utc": None, "adequacy": "unassessed", "cited_lines": [],
                              "relationships": [], "assumptions_used": [], "missing_context": [],
                              "limitations": [], "explanation": ""})
    for cid, rid in sorted({(s["case_id"], joins[s["run_id"]]) for s in run_specs(cases, 1)
                            if s["arm"] == "U" and s["run_id"] in joins}):
        append_jsonl(paths[2], {"case_id": cid, "review_id": rid, "match": "unassessed", "reason": ""})
    for path in paths[:3]:
        path.touch(exist_ok=True)  # empty files are valid when every retrieval failed
    write_json(paths[3], {"seed": SEED, "packets": len(ordered), "adjacent_case_violations": violations,
                          "blinding_limit": "Labels concealed; source familiarity and sibling code remain cues. Same AI prepares references and assesses evidence."})
    print(f"Prepared {len(ordered)} unassessed packets; adjacent-case collisions: {violations}.")


def reassessment_plan(work, first):
    packets = {r["review_id"]: r for r in read_jsonl(work / "assessment_order.jsonl")}
    ratings = read_jsonl(first)
    if len({r["review_id"] for r in ratings}) != len(ratings) or {r["review_id"] for r in ratings} != packets.keys():
        raise ValueError("Need exactly one initial assessment per issued unique packet")
    if any(r["adequacy"] not in {"adequate", "inadequate", "uncertain"} or not r.get("assessed_utc") for r in ratings):
        raise ValueError("Complete real initial ratings and timestamps before selecting the subset")
    candidates = sorted(packets)
    chosen = sorted(random.Random(SEED).sample(candidates, math.ceil(.25 * len(candidates))))
    times = {r["review_id"]: datetime.fromisoformat(r["assessed_utc"]) for r in ratings}
    if any(t.tzinfo is None for t in times.values()):
        raise ValueError("Assessment timestamps must include a UTC offset")
    plan = {"seed": SEED, "fraction": .25, "first_assessments_sha256": _hash(first),
            "subset": [{"review_id": rid, "not_before_utc": (times[rid] + timedelta(hours=48)).isoformat()}
                       for rid in chosen], "meaning": "Within-assessor consistency; not independent validation"}
    path = work / "reassessment_plan.json"
    if path.exists():
        raise FileExistsError("Delayed subset already selected; preserving it")
    write_json(path, plan)
    for rid in chosen:
        append_jsonl(work / "reassessment_packets.jsonl", packets[rid])
    print(f"Selected {len(chosen)}/{len(candidates)} packets; honour each not-before timestamp.")


def consistency(work, first, second):
    plan = json.loads((work / "reassessment_plan.json").read_text())
    if _hash(first) != plan["first_assessments_sha256"]:
        raise ValueError("Initial ratings changed; retain corrections in a separate final file")
    initial = {r["review_id"]: r for r in read_jsonl(first)}
    later_rows = read_jsonl(second)
    later = {r["review_id"]: r for r in later_rows}
    if len(later) != len(later_rows) or later.keys() != {r["review_id"] for r in plan["subset"]}:
        raise ValueError("Second pass must cover the entire frozen subset exactly once")
    rows = []
    for rid, row in later.items():
        old = initial[rid]
        if row["assessor_id"] != old["assessor_id"] or row["adequacy"] not in {"adequate", "inadequate", "uncertain"}:
            raise ValueError("Use the same honest assessor identity and a valid decision")
        first_time, second_time = (datetime.fromisoformat(r["assessed_utc"]) for r in (old, row))
        hours = (second_time - first_time).total_seconds() / 3600
        if hours < 0 or second_time > datetime.now(timezone.utc):
            raise ValueError("Invalid or future assessment timestamp")
        rows.append({"review_id": rid, "initial": old["adequacy"], "second": row["adequacy"],
                     "delay_hours": hours, "met_48_hours": hours >= 48})
    write_json(work / "consistency.json", {"n": len(rows), "agreement":
               sum(r["initial"] == r["second"] for r in rows) / len(rows) if rows else None,
               "all_met_48_hours": all(r["met_48_hours"] for r in rows) if rows else None, "records": rows,
               "limit": "Within-assessor consistency only; short delays are explicitly reported, not relabelled independent review."})
    print(work / "consistency.json")


def _hash(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "reassessment-plan", "consistency"))
    parser.add_argument("--split", choices=("development", "main"), default="development")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    args = parser.parse_args()
    work = args.work or ROOT / "work/rq1" / args.split
    if args.action == "prepare":
        prepare(args.split, work)
    elif args.action == "reassessment-plan":
        reassessment_plan(work, args.first or work / "assessments.initial.jsonl")
    else:
        consistency(work, args.first or work / "assessments.initial.jsonl",
                    args.second or work / "assessments.second.jsonl")


if __name__ == "__main__":
    main()
