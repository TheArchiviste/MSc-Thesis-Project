"""Readable evidence-only results. Coverage never substitutes for assessment."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .schema import index_jsonl, read_jsonl


def initial_decoy_summary(cases, work, report, initial, repeats):
    from .analysis import _assessments
    from .review import packet_index
    packets, _ = packet_index(cases, work, repeats)
    decisions, _, ratings = _assessments(initial, packets, None,
                  min_reviewers=2 if report["assessment_mode"] == "independent" else 1)
    if ratings.keys() != packets.keys():
        raise ValueError("Initial assessments must cover every shown unique packet")
    fixed = [r for r in report["run_evidence"] if r["arm"] == "F"]
    shown = [r for r in fixed if r["status"] == "ok"]
    adequate = sum(decisions[r["review_id"]] == "adequate" for r in shown)
    return {"planned_F": len(fixed), "shown_F": len(shown),
            "unique_shown_F_packets": len({r["review_id"] for r in shown}),
            "initial_false_adequate": adequate,
            "initial_uncertain": sum(decisions[r["review_id"]] == "uncertain" for r in shown),
            "initial_false_adequacy_rate": adequate / len(shown) if shown else None,
            "meaning": "Initial excerpt-only ratings before reference matching/corrections; not D error."}


def write_report(cases, work: Path, report: dict, assessments: Path,
                 adjudications: Path) -> None:
    by_case = {case.case_id: case for case in cases}
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    ratings = {}
    for row in read_jsonl(assessments):
        ratings.setdefault(row["review_id"], []).append(row)
    matches = {(r["case_id"], r["review_id"]): r for r in read_jsonl(adjudications)}
    records = []
    role_records = []
    for outcome in report["run_evidence"]:
        case = by_case[outcome["case_id"]]
        slc = slices[outcome["run_id"]]
        rendered = set(slc.get("rendered_lines", []))
        selected = set(slc.get("slice_lines", []))
        missing = []
        if outcome["arm"] == "U":
            for element in case.referent["elements"]:
                hit = bool(rendered.intersection(element["lines"]))
                if not hit:
                    missing.append(element["id"])
                role_records.append({"case_id": case.case_id, "run_id": outcome["run_id"],
                                     "element_id": element["id"], "role": element["role"],
                                     "source_lines": ";".join(map(str, element["lines"])),
                                     "any_line_selected": bool(selected.intersection(element["lines"])),
                                     "any_line_rendered": hit})
        rid = outcome.get("review_id")
        reasons = " | ".join(r["explanation"] for r in ratings.get(rid, []))
        match = matches.get((case.case_id, rid), {})
        records.append({"case_id": case.case_id, "block": case.cluster_id,
                        "upstream_cwe": case.cwe, "arm": outcome["arm"],
                        "overflowing_object": case.referent.get("observed_storage_kind", "unspecified"),
                        "repeat": outcome["repeat"], "status": outcome["status"],
                        "adequacy": outcome["adequacy"],
                        "selected_lines": len(selected), "rendered_lines": len(rendered),
                        "source_lines": len(case.source_for(outcome["arm"]).splitlines()),
                        "rendered_element_line_overlap": outcome["rendered_element_recall"],
                        "elements_with_no_rendered_line": ";".join(missing),
                        "assessment_reason": reasons,
                        "mechanism_match": match.get("match", "not_applicable" if outcome["arm"] == "F" else "pending"),
                        "match_reason": match.get("reason", ""),
                        "review_id": rid or "", "run_id": outcome["run_id"]})
    _csv(work / "rq1_cases.csv", records)
    _csv(work / "rq1_element_visibility.csv", role_records)
    n = len(cases)
    counts = report["rq1"]["adequacy"]
    adequate, uncertain = counts.get("adequate", 0), counts.get("uncertain", 0)
    primary = [r for r in records if r["arm"] == "U" and r["repeat"] == 0]
    successes = sum(r["status"] == "ok" for r in primary)
    fixed = [r for r in records if r["arm"] == "F"]
    shown_fixed = [r for r in fixed if r["status"] == "ok"]
    false_adequate = sum(r["adequacy"] == "adequate" for r in shown_fixed)
    bounds = (f"{adequate}/{n} to {adequate + uncertain}/{n} "
              f"({adequate/n:.1%}–{(adequate+uncertain)/n:.1%})" if n else "not estimable")
    lines = ["# RQ1 evidence adequacy", "", f"Assessment: **{report['assessment_mode']}**.",
             report["assessment_limit"], "", "Primary outcome uses repeat 0, one U per case.",
             f"Enrolled U: **{n}**, from **{len({c.cluster_id for c in cases})}** blocks.",
             f"Adequate: **{adequate}**; inadequate: **{counts.get('inadequate', 0)}**; uncertain: **{uncertain}**.",
             f"Uncertainty bounds (unresolved assessments assigned both ways): **{bounds}**.",
             "These are identification bounds, not confidence intervals.", "",
             f"Retrieved nonempty excerpts: **{successes}/{n}**; acquisition failures stay in the enrolled denominator.",
             f"Adequate among retrieved primary U excerpts: **{adequate}/{successes}**." if successes else
             "Adequacy conditional on retrieval: not estimable (no U excerpts).", "",
             (f"Fixed controls: **{len(fixed)}** planned, **{len(shown_fixed)}** shown; "
              + (f"final false adequacy: **{false_adequate}/{len(shown_fixed)}** shown controls."
                 if shown_fixed else "false adequacy not estimable: no controls shown.")),
             "F controls test assessment discriminability; they are excluded from the primary RQ1 denominator.",
             "", "| Case | Acquisition | Adequacy | Rendered/source lines | Elements with no rendered line |",
             "|---|---|---|---|---|"]
    for r in primary:
        lines.append(f"| {r['case_id']} | {r['status']} | {r['adequacy']} | "
                     f"{r['rendered_lines']}/{r['source_lines']} | {r['elements_with_no_rendered_line'] or 'none'} |")
    lines += ["", "Line overlap is descriptive. A visible line does not establish its value, flow or causal relationship.",
              "Assessment explanations and mechanism correspondence are in `rq1_cases.csv`.",
              "Each reference role and line-overlap observation is in `rq1_element_visibility.csv`.", "",
              "Failure stages: " + ", ".join(f"{key}: {value}" for key, value in sorted(Counter(r['status'] for r in primary).items())),
              "", "D classification is outside this RQ1 run. No RQ2 or RQ3 conclusion follows.",
              "The small, source-curated Juliet sample and AI-assisted reference/assessment limit generalisation.",
              "No inter-rater reliability or independent human validation is claimed."]
    initial = report.get("initial_fixed_control_check")
    if initial:
        lines += ["", (f"Initial F false adequacy before matching/corrections: "
                       f"**{initial['initial_false_adequate']}/{initial['shown_F']}** shown case controls "
                       f"({initial['unique_shown_F_packets']} unique packets).")
                  if initial["shown_F"] else "Initial F false adequacy: not estimable (no F excerpts shown)."]
    (work / "rq1_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
