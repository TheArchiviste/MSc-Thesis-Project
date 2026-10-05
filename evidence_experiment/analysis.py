"""RQ1–RQ3 outcomes. Evidence adequacy is primary; verdicts are separate."""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .runner import packet_index
from .schema import Case, index_jsonl, read_jsonl, run_specs

SEMANTIC_FAILURES = {"query_parse", "query_invalid", "query_exec", "path_binding",
                     "joern_import", "context_exec", "slice_exec", "empty_slice"}
INFRA_FAILURES = {"joern_transport", "timeout", "context_overflow",
                  "unknown_slice_failure"}


def _assessments(path: Path, packets: dict[str, dict[str, str]]) -> dict[str, str]:
    """Unanimous independent assessments; disagreement remains uncertain.

    The review export does not expose case labels or intervention arm. An
    assessor must justify an adequate judgement with lines and relationships.
    """
    by_review: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in read_jsonl(path):
        rid, assessor, decision = row["review_id"], row["assessor_id"], row["adequacy"]
        if rid not in packets:
            raise ValueError(f"Assessment for unknown review_id {rid}")
        if decision not in ("adequate", "inadequate", "uncertain"):
            raise ValueError(f"Invalid adequacy: {decision}")
        if (rid, assessor) in seen:
            raise ValueError(f"Repeated assessor {assessor!r} for review_id {rid}")
        seen.add((rid, assessor))
        if not row.get("explanation"):
            raise ValueError(f"Missing assessment explanation for {rid}")
        if decision == "adequate" and (not row.get("cited_lines") or
                                       not row.get("relationships")):
            raise ValueError(f"Adequate judgement requires lines and relationships: {rid}")
        available = {int(n) for n in re.findall(r"(?m)^L(\d+):", packets[rid]["code"])}
        if not set(row.get("cited_lines", [])) <= available:
            raise ValueError(f"Assessment cites lines absent from the packet: {rid}")
        by_review[rid].append(decision)
    return {rid: values[0] if len(set(values)) == 1 else "uncertain"
            for rid, values in by_review.items()}


def _majority(values: list[str]) -> str:
    if not values or any(v == "uncertain" for v in values):
        return "uncertain"
    counts = Counter(values)
    return counts.most_common(1)[0][0] if counts.most_common(1)[0][1] > len(values) / 2 else "uncertain"


def _ci_cluster(pairs: list[dict[str, Any]], draws: int, seed: int) -> dict[str, list[float]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        clusters[p["cluster_id"]].append(p)
    keys = list(clusters)
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {"TM": [], "TN": [], "difference": []}
    for _ in range(draws):
        sampled = [p for _ in keys for p in clusters[rng.choice(keys)]]
        tm = sum(p["loss_TM"] for p in sampled) / len(sampled)
        tn = sum(p["loss_TN"] for p in sampled) / len(sampled)
        samples["TM"].append(tm)
        samples["TN"].append(tn)
        samples["difference"].append(tm - tn)
    return {name: [sorted(values)[int(.025 * (draws - 1))],
                   sorted(values)[int(.975 * (draws - 1))]]
            for name, values in samples.items()}


def _element_recall(case: Case, arm: str, selected: list[int]) -> float | None:
    """Element coverage is descriptive, not a substitute for sufficiency."""
    selected_set = set(selected)
    original_arm = arm.split("_")[0]
    elements = case.referent["elements"]
    mapped: list[list[int]] = []
    for element in elements:
        if original_arm == "U":
            lines = element["lines"]
        else:
            lines = element.get("mapped_lines", {}).get(original_arm)
            if lines is None:
                return None  # never compare source coordinates across programs
        mapped.append(lines)
    return sum(bool(selected_set.intersection(lines)) for lines in mapped) / len(elements)


def analyze(cases: list[Case], work: Path, assessments: Path, adjudications: Path,
            repeats: int = 3, bootstrap_draws: int = 2000, seed: int = 0) -> dict[str, Any]:
    specs = run_specs(cases, repeats)
    queries = index_jsonl(work / "queries.jsonl", "run_id")
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    detector = index_jsonl(work / "detector.jsonl", "run_id")
    packets, joins = packet_index(cases, work, repeats)
    decisions = _assessments(assessments, packets)
    adjudicated: dict[tuple[str, str], str] = {}
    for row in read_jsonl(adjudications):
        key = (row["case_id"], row["review_id"])
        if key in adjudicated or row["match"] not in ("yes", "no", "uncertain"):
            raise ValueError(f"Duplicate or invalid adjudication: {key}")
        if not row.get("reason"):
            raise ValueError(f"Adjudication requires a reason: {key}")
        adjudicated[key] = row["match"]
    by_case = {case.case_id: case for case in cases}
    outcomes: dict[str, dict[str, Any]] = {}
    for spec in specs:
        rid = spec["run_id"]
        slc = slices.get(rid)
        det = detector.get(rid)
        if slc is None or det is None:
            raise ValueError(f"Incomplete phase data for {rid}")
        status = slc["status"]
        if status == "ok" and det["status"] == "context_overflow":
            status = "context_overflow"
        if status == "ok":
            blind = decisions.get(joins[rid], "uncertain")
            match = adjudicated.get((spec["case_id"], joins[rid]), "uncertain")
            adequacy = ("inadequate" if blind == "inadequate" or match == "no" else
                        "adequate" if blind == "adequate" and match == "yes" else
                        "uncertain")
        else:
            adequacy = "inadequate" if status in SEMANTIC_FAILURES else "uncertain"
        if det["status"] == "ok":
            verdict = det["verdict"]
        else:
            verdict = None  # abstention is not a SAFE verdict
        case = by_case[spec["case_id"]]
        outcomes[rid] = {**spec, "status": status, "adequacy": adequacy,
                         "verdict": verdict,
                         "element_recall": (_element_recall(case, spec["arm"], slc["slice_lines"])
                                            if status == "ok" else 0.0),
                         "rendered_element_recall": (
                             _element_recall(case, spec["arm"], slc["rendered_lines"])
                             if status == "ok" else 0.0),
                         "review_id": joins.get(rid)}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in outcomes.values():
        groups[item["case_id"], item["arm"]].append(item)
    for group in groups.values():
        group.sort(key=lambda item: item["repeat"])

    def decision(case_id: str, arm: str) -> str:
        return _majority([r["adequacy"] for r in groups.get((case_id, arm), [])])

    baseline = Counter(decision(case.case_id, "U") for case in cases)
    baseline_verdicts = Counter(
        "detected" if r["verdict"] else "missed" if r["verdict"] is False else "abstained"
        for case in cases for r in groups[case.case_id, "U"] if r["repeat"] == 0)
    cross = Counter(
        (decision(case.case_id, "U"),
         "detected" if groups[case.case_id, "U"][0]["verdict"] else
         "missed" if groups[case.case_id, "U"][0]["verdict"] is False else "abstained")
        for case in cases)
    paired: list[dict[str, Any]] = []
    exclusions = Counter()
    for case in cases:
        if not case.paired:
            exclusions["no_transformation_pair"] += 1
        elif not case.admissible:
            exclusions["invalid_or_indeterminate_transformation"] += 1
        elif not case.referent.get("target_lines") or not case.referent.get("control_lines"):
            exclusions["target_or_control_line_missing"] += 1
        elif not (set(case.referent["target_lines"]) &
                  set(slices[groups[case.case_id, "U"][0]["run_id"]].get("slice_lines", []))):
            exclusions["target_not_in_original_slice"] += 1
        elif not (set(case.referent["control_lines"]) &
                  set(slices[groups[case.case_id, "U"][0]["run_id"]].get("slice_lines", []))):
            exclusions["control_not_in_original_slice"] += 1
        elif decision(case.case_id, "U") != "adequate":
            exclusions["original_evidence_not_adequate_or_uncertain"] += 1
        elif any(decision(case.case_id, arm) == "uncertain" for arm in ("TM", "TN")):
            exclusions["transformed_evidence_uncertain"] += 1
        else:
            paired.append({"case_id": case.case_id, "cluster_id": case.cluster_id,
                           "operator": case.operator, "cwe": case.cwe,
                           "loss_TM": int(decision(case.case_id, "TM") == "inadequate"),
                           "loss_TN": int(decision(case.case_id, "TN") == "inadequate"),
                           "TM_verdicts": [r["verdict"] for r in groups[case.case_id, "TM"]],
                           "TN_verdicts": [r["verdict"] for r in groups[case.case_id, "TN"]]})
    n = len(paired)
    tm_rate = sum(p["loss_TM"] for p in paired) / n if n else None
    tn_rate = sum(p["loss_TN"] for p in paired) / n if n else None
    delta = tm_rate - tn_rate if n else None
    ci = _ci_cluster(paired, bootstrap_draws, seed) if n and bootstrap_draws >= 20 else None

    failures = Counter((r["arm"], r["status"]) for r in outcomes.values())
    # The fixed and rule arms are probes. Different outputs alone do not prove
    # a unique causal stage; preserve observations and all competing results.
    diagnostics = []
    for case in cases:
        baseline_q = queries.get(groups[case.case_id, "U"][0]["run_id"], {}).get("queries")
        for arm in ("U", "TM", "TN"):
            if not groups.get((case.case_id, arm)):
                continue
            first = groups[case.case_id, arm][0]
            probes = {probe: decision(case.case_id, probe)
                      for probe in (f"{arm}_fixed", f"{arm}_rule")
                      if (case.case_id, probe) in groups}
            q_bundle = queries.get(first["run_id"], {}).get("queries")
            changed_query = (q_bundle != baseline_q if arm != "U" and
                             q_bundle is not None and baseline_q is not None else None)
            if first["status"] in SEMANTIC_FAILURES | INFRA_FAILURES:
                earliest = first["status"]
            elif changed_query:
                earliest = "query_bundle_changed"  # a difference, not necessarily a failure
            elif decision(case.case_id, arm) == "inadequate":
                earliest = "evidence_inadequate_stage_unresolved"
            elif first["verdict"] is False:
                earliest = "classifier_disagreement_with_adequate_evidence"
            else:
                earliest = "no_observed_failure"
            diagnostics.append({"case_id": case.case_id, "arm": arm,
                                "first_observed_status": first["status"],
                                "earliest_observed_change": earliest,
                                "query_bundle_changed_from_U": changed_query,
                                "adequacy": decision(case.case_id, arm),
                                "verdict": first["verdict"], "probes": probes})
    retained_correct_after_loss = sum(
        p["loss_TM"] and any(v is True for v in p["TM_verdicts"]) for p in paired)
    u_instability = sum(len({r["adequacy"] for r in groups[case.case_id, "U"]}) > 1
                        for case in cases)
    by_family = defaultdict(Counter)
    for case in cases:
        by_family[case.cwe][decision(case.case_id, "U")] += 1
    return {
        "rq1": {"cases": len(cases), "adequacy": dict(baseline),
                "adequacy_by_cwe": {family: dict(counts) for family, counts in by_family.items()},
                "verdicts_repeat0": dict(baseline_verdicts),
                "adequacy_by_verdict": [dict(adequacy=a, verdict=v, count=count)
                                        for (a, v), count in sorted(cross.items())],
                "unmodified_cases_with_assessment_variation": u_instability},
        "rq2": {"n_pairs": n, "n_clusters": len({p["cluster_id"] for p in paired}),
                "TM_adequacy_loss_rate": tm_rate, "TN_adequacy_loss_rate": tn_rate,
                "paired_risk_difference": delta, "cluster_bootstrap_95_ci": ci,
                "correct_verdict_despite_TM_evidence_loss": retained_correct_after_loss,
                "exclusions": dict(exclusions), "pairs": paired},
        "rq3": {"status_counts": [dict(arm=a, status=s, count=count)
                                  for (a, s), count in sorted(failures.items())],
                "observations": diagnostics},
        "run_evidence": list(outcomes.values()),
    }
