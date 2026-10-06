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


def _assessments(path: Path, packets: dict[str, dict[str, str]], resolutions: Path | None,
                 min_reviewers: int = 2) -> tuple[dict[str, str], dict[str, int]]:
    """Require independent ratings; resolve disagreements only with a logged decision.

    The review export does not expose case labels or intervention arm. An
    assessor must justify an adequate judgement with lines and relationships.
    """
    by_review: dict[str, list[str]] = defaultdict(list)
    assessors: dict[str, set[str]] = defaultdict(set)
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
        assessors[rid].add(assessor)
        if not row.get("explanation"):
            raise ValueError(f"Missing assessment explanation for {rid}")
        if decision == "adequate" and (not row.get("cited_lines") or
                                       not row.get("relationships")):
            raise ValueError(f"Adequate judgement requires lines and relationships: {rid}")
        available = {int(n) for n in re.findall(r"(?m)^L(\d+):", packets[rid]["code"])}
        if not set(row.get("cited_lines", [])) <= available:
            raise ValueError(f"Assessment cites lines absent from the packet: {rid}")
        by_review[rid].append(decision)
    resolved: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(resolutions) if resolutions else []:
        rid = row["review_id"]
        if rid in resolved or rid not in packets or row.get("method") not in ("third_review", "consensus"):
            raise ValueError(f"Invalid or duplicate resolution for {rid}")
        if row.get("adequacy") not in ("adequate", "inadequate", "uncertain") or not row.get("reason"):
            raise ValueError(f"Resolution needs a decision and reason for {rid}")
        if row["method"] == "third_review" and (
                not row.get("assessor_id") or row["assessor_id"] in assessors[rid]):
            raise ValueError(f"Third reviewer must be independent for {rid}")
        if row["adequacy"] == "adequate":
            available = {int(n) for n in re.findall(r"(?m)^L(\d+):", packets[rid]["code"])}
            if (not row.get("cited_lines") or not row.get("relationships") or
                    not set(row["cited_lines"]) <= available):
                raise ValueError(f"Adequate resolution needs visible lines and relationship: {rid}")
        resolved[rid] = row
    decisions: dict[str, str] = {}
    stats = Counter()
    for rid, values in by_review.items():
        if len(values) < min_reviewers:
            stats["insufficient_reviewers"] += 1
            decisions[rid] = "uncertain"
        elif len(set(values)) == 1:
            stats["initial_agreement"] += 1
            decisions[rid] = values[0]
        else:
            stats["initial_disagreement"] += 1
            decisions[rid] = resolved[rid]["adequacy"] if rid in resolved else "uncertain"
            if rid in resolved:
                stats["resolved_disagreement"] += 1
    if set(resolved) - {rid for rid, values in by_review.items()
                        if len(values) >= min_reviewers and len(set(values)) > 1}:
        raise ValueError("Resolution supplied without an independently rated disagreement")
    return decisions, dict(stats)


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
            repeats: int = 3, bootstrap_draws: int = 2000, seed: int = 0,
            resolutions: Path | None = None, evidence_only: bool = False) -> dict[str, Any]:
    specs = run_specs(cases, repeats)
    queries = index_jsonl(work / "queries.jsonl", "run_id")
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    detector = index_jsonl(work / "detector.jsonl", "run_id")
    packets, joins = packet_index(cases, work, repeats)
    decisions, review_stats = _assessments(assessments, packets, resolutions)
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
        if slc is None or (det is None and not evidence_only):
            raise ValueError(f"Incomplete phase data for {rid}")
        if det is None:
            det = {"status": "not_run"}
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
                         "verdict": verdict, "detector_status": det["status"],
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

    def verdict_label(row: dict[str, Any]) -> str:
        if row["detector_status"] == "not_run":
            return "not_run"
        if row["verdict"] is True:
            return "detected"
        if row["verdict"] is False:
            return "missed"
        return "abstained"

    baseline = Counter(decision(case.case_id, "U") for case in cases)
    baseline_verdicts = Counter(
        verdict_label(r)
        for case in cases for r in groups[case.case_id, "U"] if r["repeat"] == 0)
    cross = Counter(
        (decision(case.case_id, "U"), verdict_label(groups[case.case_id, "U"][0]))
        for case in cases)
    paired: list[dict[str, Any]] = []
    eligible: list[tuple[str, str]] = []
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
        else:
            tm, tn = (decision(case.case_id, arm) for arm in ("TM", "TN"))
            eligible.append((tm, tn))
            if "uncertain" in (tm, tn):
                exclusions["transformed_evidence_uncertain"] += 1
                continue
            u_recall = groups[case.case_id, "U"][0]["element_recall"]
            tm_recall = groups[case.case_id, "TM"][0]["element_recall"]
            tn_recall = groups[case.case_id, "TN"][0]["element_recall"]
            paired.append({"case_id": case.case_id, "cluster_id": case.cluster_id,
                           "operator": case.operator, "cwe": case.cwe,
                           "loss_TM": int(tm == "inadequate"),
                           "loss_TN": int(tn == "inadequate"),
                           "selected_coverage_change_TM": (tm_recall - u_recall
                                                           if None not in (tm_recall, u_recall) else None),
                           "selected_coverage_change_TN": (tn_recall - u_recall
                                                           if None not in (tn_recall, u_recall) else None),
                           "TM_verdicts": [r["verdict"] for r in groups[case.case_id, "TM"]],
                           "TN_verdicts": [r["verdict"] for r in groups[case.case_id, "TN"]]})
    n = len(paired)
    tm_rate = sum(p["loss_TM"] for p in paired) / n if n else None
    tn_rate = sum(p["loss_TN"] for p in paired) / n if n else None
    delta = tm_rate - tn_rate if n else None
    n_clusters = len({p["cluster_id"] for p in paired})
    ci = _ci_cluster(paired, bootstrap_draws, seed) if n_clusters >= 2 and bootstrap_draws >= 20 else None
    n_eligible = len(eligible)
    bounds = None
    if n_eligible:
        bounds = {
            "TM_loss": [sum(tm == "inadequate" for tm, _ in eligible) / n_eligible,
                        sum(tm != "adequate" for tm, _ in eligible) / n_eligible],
            "TN_loss": [sum(tn == "inadequate" for _, tn in eligible) / n_eligible,
                        sum(tn != "adequate" for _, tn in eligible) / n_eligible],
            "difference": [sum((tm == "inadequate") - (tn != "adequate")
                               for tm, tn in eligible) / n_eligible,
                           sum((tm != "adequate") - (tn == "inadequate")
                               for tm, tn in eligible) / n_eligible],
        }

    failures = Counter((r["arm"], r["status"]) for r in outcomes.values())
    # The fixed and rule arms are probes. Different outputs alone do not prove
    # a unique causal stage; preserve observations and all competing results.
    diagnostics = []
    diagnostic_patterns = Counter()
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
            elif decision(case.case_id, arm) == "inadequate":
                earliest = "evidence_inadequate_stage_unresolved"
            elif decision(case.case_id, arm) == "uncertain":
                earliest = "evidence_uncertain"
            elif first["verdict"] is False:
                earliest = "classifier_disagreement_with_adequate_evidence"
            else:
                earliest = "no_observed_failure"
            pattern = (arm, decision(case.case_id, arm),
                       probes.get(f"{arm}_fixed", "not_run"),
                       probes.get(f"{arm}_rule", "not_run"), verdict_label(first))
            diagnostic_patterns[pattern] += 1
            diagnostics.append({"case_id": case.case_id, "arm": arm,
                                "first_observed_status": first["status"],
                                "earliest_observed_change": earliest,
                                "query_bundle_changed_from_U": changed_query,
                                "adequacy": decision(case.case_id, arm),
                                "verdict": first["verdict"], "probes": probes})
    retained_correct_after_loss = sum(
        p["loss_TM"] and any(v is True for v in p["TM_verdicts"]) for p in paired)
    u_query_variation = sum(len({str(queries.get(r["run_id"], {}).get("queries"))
                                 for r in groups[case.case_id, "U"]}) > 1 for case in cases)
    u_slice_variation = sum(len({(r["status"],
                                 tuple(slices[r["run_id"]].get("slice_lines", [])))
                                 for r in groups[case.case_id, "U"]}) > 1 for case in cases)
    u_adequacy_variation = sum(len({r["adequacy"] for r in groups[case.case_id, "U"]}) > 1
                               for case in cases)
    by_family = defaultdict(Counter)
    for case in cases:
        by_family[case.cwe][decision(case.case_id, "U")] += 1
    return {
        "scope": "evidence_only" if evidence_only else "full_pipeline",
        "review": review_stats,
        "rq1": {"cases": len(cases), "adequacy": dict(baseline),
                "adequacy_by_cwe": {family: dict(counts) for family, counts in by_family.items()},
                "verdicts_repeat0": dict(baseline_verdicts),
                "adequacy_by_verdict": [{"adequacy": a, "verdict": v, "count": count}
                                        for (a, v), count in sorted(cross.items())],
                "repeat_variation": ({"query_bundle_cases": u_query_variation,
                                      "selected_slice_cases": u_slice_variation,
                                      "adequacy_cases": u_adequacy_variation}
                                     if repeats > 1 else None)},
        "rq2": {"n_pairs": n, "n_eligible_including_uncertain": n_eligible,
                "n_clusters": n_clusters,
                "TM_adequacy_loss_rate": tm_rate, "TN_adequacy_loss_rate": tn_rate,
                "paired_risk_difference": delta, "cluster_bootstrap_95_ci": ci,
                "unresolved_outcome_bounds": bounds,
                "coverage_change_is_descriptive": True,
                "correct_verdict_despite_TM_evidence_loss": retained_correct_after_loss,
                "exclusions": dict(exclusions), "pairs": paired},
        "rq3": {"status_counts": [{"arm": a, "status": s, "count": count}
                                  for (a, s), count in sorted(failures.items())],
                "pattern_counts": [
                    {"arm": a, "regenerated_adequacy": r, "fixed_adequacy": f,
                     "rule_adequacy": q, "verdict": v, "count": count}
                    for (a, r, f, q, v), count in sorted(diagnostic_patterns.items())],
                "observations": diagnostics},
        "run_evidence": list(outcomes.values()),
    }
