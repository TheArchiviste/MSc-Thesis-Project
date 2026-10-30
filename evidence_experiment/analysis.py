"""RQ1 primary-repeat evidence adequacy; uncertainty remains explicit."""
from __future__ import annotations

import json
from collections import Counter

from .locks import check_stage_receipts, now, validate_terminal_records
from .review import assessments, packet_index
from .schema import file_digest, index_jsonl, run_specs, write_json


def consistency_status(work, packets):
    if not packets:
        return {"complete": True, "status": "not_applicable_no_shown_packets", "n": 0}
    required = [work / name for name in ("reassessment_plan.json", "assessments.second.jsonl", "consistency.json")]
    if not all(p.is_file() for p in required):
        return {"complete": False, "status": "pending_25_percent_delayed_reassessment"}
    from rq1.assess import consistency
    # Validate actual subset, ratings, 48-hour delay and immutable initial file again.
    result = consistency(work, work / "assessments.initial.jsonl", work / "assessments.second.jsonl")
    return {"complete": result["all_met_48_hours"] is True, "status": "complete" if result["all_met_48_hours"] else "delay_below_48_hours", **result}


def analyze(cases, work):
    check_stage_receipts(work)
    receipts = json.loads((work / "stage_receipts.json").read_text())
    if not {"query", "slice"} <= receipts.keys():
        raise ValueError("Acquire and receipt both real stages before analysis")
    for phase in ("query", "slice"):
        validate_terminal_records(work, phase, cases)
    packets, joins = packet_index(cases, work)
    issued = index_jsonl(work / "blind_review_packets.jsonl", "review_id")
    if issued != packets:
        raise ValueError("Issue the exact current packets before assessment")
    initial = assessments(work / "assessments.initial.jsonl", packets)
    final = assessments(work / "assessments.final.jsonl", packets)
    from datetime import datetime
    if any(datetime.fromisoformat(final[r]["assessed_utc"]) < datetime.fromisoformat(initial[r]["assessed_utc"]) for r in packets):
        raise ValueError("Final correction predates its initial assessment")
    specs = run_specs(cases)
    expected = {s["case_id"]: joins[s["run_id"]] for s in specs if s["arm"] == "U" and s["run_id"] in joins}
    path = work / "adjudications.jsonl"
    if not path.is_file():
        raise FileNotFoundError(path)
    matches = index_jsonl(path, "case_id")
    if matches.keys() != expected.keys():
        raise ValueError("Match each shown U packet to its source-only reference exactly once")
    for cid, row in matches.items():
        if (row.get("review_id") != expected[cid] or row.get("match") not in {"yes", "no", "uncertain"}
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            raise ValueError("Mechanism correspondence needs an explicit supported decision/reason")
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    by_case = {c.case_id: c for c in cases}
    records = []
    from .runner import INFRA_STATUSES
    for spec in specs:
        row, case = slices[spec["run_id"]], by_case[spec["case_id"]]
        rid = joins.get(spec["run_id"])
        if row["status"] != "ok":
            verdict = "uncertain" if row["status"] in INFRA_STATUSES | {"mapping_error"} else "inadequate"
        else:
            verdict = final[rid]["adequacy"]
            if spec["arm"] == "U":
                match = matches[spec["case_id"]]["match"]
                if verdict == "adequate" and match != "yes":
                    verdict = "inadequate" if match == "no" else "uncertain"
        elements = case.referent["elements"]
        overlap = sum(bool(set(e["lines"]) & set(row.get("rendered_lines", []))) for e in elements) / len(elements)
        records.append({**spec, "status": row["status"], "adequacy": verdict,
                        "review_id": rid, "rendered_element_recall": overlap if spec["arm"] == "U" else None})
    primary = [r for r in records if r["arm"] == "U"]
    counts = {k: sum(r["adequacy"] == k for r in primary) for k in ("adequate", "inadequate", "uncertain")}
    n = len(cases)
    initial_fixed = [r for r in records if r["arm"] == "F" and r["review_id"]]
    false_adequate = sum(initial[r["review_id"]]["adequacy"] == "adequate" for r in initial_fixed)
    consistency = consistency_status(work, packets)
    report = {"scope": "rq1_only", "utc": now(), "primary_rule": "repeat_0", "repeats": 1,
              "assessment_mode": "AI-assisted single assessor",
              "assessment_limit": "The same AI prepares references and assesses excerpts. Label concealment is limited; no independent human validation or inter-rater reliability is claimed.",
              "completion": "complete" if consistency["complete"] else "provisional",
              "consistency": consistency, "run_evidence": records,
              "rq1": {"n": n, "blocks": len({c.cluster_id for c in cases}), "adequacy": counts,
                      "adequate_fraction": counts["adequate"] / n,
                      "identification_bounds": [counts["adequate"] / n, (counts["adequate"] + counts["uncertain"]) / n],
                      "status_counts": dict(Counter(r["status"] for r in primary))},
              "initial_fixed_control_check": {"planned_F": n, "shown_F": len(initial_fixed),
                  "unique_shown_F_packets": len({r["review_id"] for r in initial_fixed}),
                  "initial_false_adequate": false_adequate,
                  "initial_false_adequacy_rate": false_adequate / len(initial_fixed) if initial_fixed else None},
              "analysis_provenance": {name: file_digest(work / name) for name in (
                  "assessments.initial.jsonl", "assessments.final.jsonl", "adjudications.jsonl",
                  "blind_review_packets.jsonl", "stage_receipts.json", "experiment_lock.json")}}
    write_json(work / "analysis.json", report)
    from .rq1_report import write_report
    write_report(cases, work, report, work / "assessments.final.jsonl", path)
    return report
