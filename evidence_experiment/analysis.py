"""RQ1–RQ3 outcomes. Evidence adequacy is primary; verdicts are separate."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .review import duplicate_packets, packet_index, packet_lines
from .schema import DECOY_ARM, Case, digest, index_jsonl, read_jsonl, run_specs
from .stats import agreement_summary, mcnemar_exact_p, newcombe_paired

SEMANTIC_FAILURES = {"query_parse", "query_invalid", "query_exec", "path_binding",
                     "joern_import", "context_exec", "slice_exec", "empty_slice"}
INFRA_FAILURES = {"joern_transport", "timeout", "context_overflow",
                  "unknown_slice_failure"}


def _assessments(path: Path, packets: dict[str, dict[str, str]], resolutions: Path | None,
                 min_reviewers: int = 2
                 ) -> tuple[dict[str, str], dict[str, int], dict[str, dict[str, str]]]:
    """Require independent ratings; resolve disagreements only with a logged decision.

    The review export does not expose case labels or intervention arm. An
    assessor must justify an adequate judgement with lines and relationships.
    Returns final decisions, counts, and the raw ratings by packet and assessor.
    """
    by_review: dict[str, list[str]] = defaultdict(list)
    ratings: dict[str, dict[str, str]] = defaultdict(dict)
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
        if not set(row.get("cited_lines", [])) <= packet_lines(packets[rid]["code"]):
            raise ValueError(f"Assessment cites lines absent from the packet: {rid}")
        by_review[rid].append(decision)
        ratings[rid][assessor] = decision
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
        if row["adequacy"] == "adequate" and (
                not row.get("cited_lines") or not row.get("relationships") or
                not set(row["cited_lines"]) <= packet_lines(packets[rid]["code"])):
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
    return decisions, dict(stats), dict(ratings)


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
    detector = {} if evidence_only else index_jsonl(work / "detector.jsonl", "run_id")
    packets, joins = packet_index(cases, work, repeats)
    duplicates = duplicate_packets(cases, work, repeats)
    decisions, review_stats, ratings = _assessments(assessments, {**packets, **duplicates},
                                                    resolutions)
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
        if spec["arm"] == DECOY_ARM:
            # A decoy has no documented flaw to match: the blind rating is the outcome.
            adequacy = decisions.get(joins[rid], "uncertain") if status == "ok" else "not_shown"
        elif status == "ok":
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
    independent_candidates: list[dict[str, Any]] = []
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
            exclusions[f"original_evidence_{decision(case.case_id, 'U')}"] += 1
        else:
            tm, tn = (decision(case.case_id, arm) for arm in ("TM", "TN"))
            eligible.append((tm, tn))
            independent_candidates.append({
                "case_id": case.case_id, "cluster_id": case.cluster_id,
                "loss_TM": None if tm == "uncertain" else int(tm == "inadequate"),
                "loss_TN": None if tn == "uncertain" else int(tn == "inadequate")})
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
    one_per_cluster = _one_per_cluster(independent_candidates, seed)
    coverage = _coverage_all_admissible(cases, groups, slices)

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
                "one_case_per_cluster": one_per_cluster,
                "unresolved_outcome_bounds": bounds,
                "coverage_change_is_descriptive": True,
                "coverage_change_all_admissible": coverage,
                "correct_verdict_despite_TM_evidence_loss": retained_correct_after_loss,
                "exclusions": dict(exclusions), "pairs": paired},
        "rq3": {"status_counts": [{"arm": a, "status": s, "count": count}
                                  for (a, s), count in sorted(failures.items())],
                "pattern_counts": [
                    {"arm": a, "regenerated_adequacy": r, "fixed_adequacy": f,
                     "rule_adequacy": q, "verdict": v, "count": count}
                    for (a, r, f, q, v), count in sorted(diagnostic_patterns.items())],
                "observations": diagnostics},
        "review_quality": _review_quality(cases, specs, joins, decisions, ratings, duplicates,
                                          groups, decision, verdict_label),
        "run_evidence": list(outcomes.values()),
    }


def _one_per_cluster(paired: list[dict[str, Any]], seed: int) -> dict[str, Any] | None:
    """Select from baseline-eligible pairs before inspecting transformed resolution.

    An uncertain selected pair is retained in the selection report and is never
    replaced by another member of its cluster with resolved outcomes.
    """
    if not paired:
        return None
    chosen: dict[str, tuple[str, dict[str, Any]]] = {}
    for pair in paired:
        rank = digest(f"{seed}|{pair['cluster_id']}|{pair['case_id']}")
        current = chosen.get(pair["cluster_id"])
        if current is None or rank < current[0]:
            chosen[pair["cluster_id"]] = (rank, pair)
    selected = [pair for _, pair in chosen.values()]
    pairs = [p for p in selected if None not in (p["loss_TM"], p["loss_TN"])]
    both = sum(p["loss_TM"] and p["loss_TN"] for p in pairs)
    tm_only = sum(p["loss_TM"] and not p["loss_TN"] for p in pairs)
    tn_only = sum(p["loss_TN"] and not p["loss_TM"] for p in pairs)
    neither = len(pairs) - both - tm_only - tn_only
    n = len(pairs)
    def lower(value):
        return 0 if value is None else value

    def upper(value):
        return 1 if value is None else value

    bounds = {
        "TM_loss": [sum(lower(p["loss_TM"]) for p in selected) / len(selected),
                    sum(upper(p["loss_TM"]) for p in selected) / len(selected)],
        "TN_loss": [sum(lower(p["loss_TN"]) for p in selected) / len(selected),
                    sum(upper(p["loss_TN"]) for p in selected) / len(selected)],
        "difference": [sum(lower(p["loss_TM"]) - upper(p["loss_TN"]) for p in selected) / len(selected),
                       sum(upper(p["loss_TM"]) - lower(p["loss_TN"]) for p in selected) / len(selected)]}
    return {"seed": seed, "n_pairs": n, "n_selected": len(selected),
            "n_uncertain": len(selected) - n,
            "selection_population": "baseline_eligible_before_transformed_resolution",
            "case_ids": sorted(p["case_id"] for p in selected),
            "resolved_case_ids": sorted(p["case_id"] for p in pairs),
            "unresolved_outcome_bounds": bounds,
            "loss_both": both, "loss_TM_only": tm_only, "loss_TN_only": tn_only,
            "loss_neither": neither,
            "TM_adequacy_loss_rate": (both + tm_only) / n if n else None,
            "TN_adequacy_loss_rate": (both + tn_only) / n if n else None,
            "paired_risk_difference": (tm_only - tn_only) / n if n else None,
            "newcombe_95_ci": list(newcombe_paired(both, tm_only, tn_only, neither)) if n else None,
            "mcnemar_exact_p": mcnemar_exact_p(tm_only, tn_only) if n else None}


def _coverage_all_admissible(cases: list[Case], groups, slices) -> dict[str, Any]:
    """Reviewer-free referent coverage change for every admissible pair.

    Uses repeat 0 and source-coordinate mappings. A failed transformed slice
    counts as zero coverage; a failed original slice leaves no baseline.
    """
    rows, skipped = [], Counter()
    for case in cases:
        if not case.admissible:
            continue
        u = groups[case.case_id, "U"][0]
        if u["status"] != "ok":
            skipped["original_slice_failed"] += 1
            continue
        tm, tn = groups[case.case_id, "TM"][0], groups[case.case_id, "TN"][0]
        if None in (u["element_recall"], tm["element_recall"], tn["element_recall"]):
            skipped["unmapped_elements"] += 1
            continue
        selected = set(slices[u["run_id"]].get("slice_lines", []))
        rows.append({"case_id": case.case_id, "cluster_id": case.cluster_id,
                     "operator": case.operator,
                     "in_primary_population": bool(
                         _majority([r["adequacy"] for r in groups[case.case_id, "U"]]) == "adequate" and
                         set(case.referent.get("target_lines", [])) & selected and
                         set(case.referent.get("control_lines", [])) & selected),
                     "U": u["element_recall"], "TM": tm["element_recall"],
                     "TN": tn["element_recall"],
                     "change_TM": tm["element_recall"] - u["element_recall"],
                     "change_TN": tn["element_recall"] - u["element_recall"]})

    def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"n": 0}
        n = len(items)
        tm = sum(r["change_TM"] for r in items) / n
        tn = sum(r["change_TN"] for r in items) / n
        return {"n": n, "n_clusters": len({r["cluster_id"] for r in items}),
                "mean_change_TM": tm, "mean_change_TN": tn,
                "mean_paired_difference": tm - tn}

    return {"all": summary(rows),
            "primary_population": summary([r for r in rows if r["in_primary_population"]]),
            "skipped": dict(skipped), "pairs": rows}


def _review_quality(cases, specs, joins, decisions, ratings, duplicates, groups,
                    decision, verdict_label) -> dict[str, Any]:
    """Reviewer agreement by arm, fixed-variant decoys and disguised duplicates."""
    arms_for: dict[str, set[str]] = defaultdict(set)
    for spec in specs:
        rid = joins.get(spec["run_id"])
        if rid:
            arm = spec["arm"]
            arms_for[rid].add("probe" if arm.endswith(("_fixed", "_rule")) else arm)
    by_group: dict[str, list[list[str]]] = defaultdict(list)
    for rid, rated in ratings.items():
        values = list(rated.values())
        if rid in duplicates:
            group = "duplicate"
        else:
            arms = arms_for.get(rid, set())
            group = next(iter(arms)) if len(arms) == 1 else "shared_excerpt"
        by_group[group].append(values)
    agreement = {"all_packets": agreement_summary([v for g in by_group.values() for v in g]),
                 "by_arm": {group: agreement_summary(items)
                            for group, items in sorted(by_group.items())}}

    decoy_cases = [case for case in cases if DECOY_ARM in case.sources]
    decoy_status, decoy_rating, cross, decoy_verdicts = Counter(), Counter(), Counter(), Counter()
    identical = 0
    for case in decoy_cases:
        f_run = groups[case.case_id, DECOY_ARM][0]
        u_run = groups[case.case_id, "U"][0]
        decoy_status[f_run["status"]] += 1
        decoy_verdicts[verdict_label(f_run)] += 1
        if f_run["status"] != "ok":
            continue
        decoy_rating[f_run["adequacy"]] += 1
        cross[(decision(case.case_id, "U"), f_run["adequacy"])] += 1
        identical += f_run["review_id"] is not None and f_run["review_id"] == u_run["review_id"]
    shown = sum(decoy_rating.values())
    decided = decoy_rating["adequate"] + decoy_rating["inadequate"]
    decoys = {
        "cases_with_fixed_variant": len(decoy_cases),
        "slice_status": dict(decoy_status),
        "shown_to_reviewers": shown,
        "ratings": dict(decoy_rating),
        "false_adequacy_rate": decoy_rating["adequate"] / shown if shown else None,
        "false_adequacy_rate_excluding_uncertain": (decoy_rating["adequate"] / decided
                                                    if decided else None),
        "excerpt_identical_to_vulnerable": identical,
        "vulnerable_by_fixed_rating": [{"vulnerable_adequacy": u, "fixed_rating": f,
                                        "count": count} for (u, f), count in sorted(cross.items())],
        "detector_verdicts_on_fixed": dict(decoy_verdicts),
        "interpretation": ("A fixed variant rated adequate means the excerpt or the "
                           "reviewers do not discriminate the documented flaw."),
    }

    retest_items, final_pairs = [], Counter()
    for rid, dup in duplicates.items():
        original = dup["duplicate_of"]
        for assessor, value in ratings.get(rid, {}).items():
            if assessor in ratings.get(original, {}):
                retest_items.append([ratings[original][assessor], value])
        if rid in decisions and original in decisions:
            final_pairs["agree" if decisions[rid] == decisions[original] else "disagree"] += 1
    retest = {"duplicates_issued": len(duplicates),
              "same_assessor_retest": agreement_summary(retest_items),
              "final_decision_agreement": dict(final_pairs)}
    return {"agreement": agreement, "decoys": decoys, "duplicates": retest}
