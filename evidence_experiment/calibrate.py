"""Disjoint threshold calibration and detector usability screen."""

from __future__ import annotations

from typing import Any


def _auc(positives: list[float], negatives: list[float]) -> float:
    if not positives or not negatives:
        raise ValueError("AUC requires positives and negatives")
    return sum((p > n) + .5 * (p == n) for p in positives for n in negatives) / (
        len(positives) * len(negatives))


def calibrate(rows: list[dict[str, Any]], analysis_clusters: set[str]) -> dict[str, Any]:
    """Scores must be emitted by Q -> slice -> D on predeclared separate splits."""
    from llmxcpg.calibration.threshold import calibrate_threshold

    ids: set[str] = set()
    splits: dict[str, set[str]] = {"calibration": set(), "specificity": set()}
    for row in rows:
        split = row["split"]
        if split not in splits or row["sample_id"] in ids:
            raise ValueError("Unknown split or duplicate sample_id")
        ids.add(row["sample_id"])
        splits[split].add(row["cluster_id"])
        if row["cluster_id"] in analysis_clusters:
            raise ValueError("Calibration/specificity cluster overlaps analysis")
        if row["label"] not in (0, 1) or not 0 <= row["p_vulnerable"] <= 1:
            raise ValueError("Invalid label or probability")
    if splits["calibration"] & splits["specificity"]:
        raise ValueError("Calibration and specificity clusters overlap")
    calibration = [r for r in rows if r["split"] == "calibration"]
    specificity = [r for r in rows if r["split"] == "specificity"]
    if not calibration or not specificity or any(r["label"] != 0 for r in specificity):
        raise ValueError("Need mixed-label calibration and held-out safe specificity set")
    labels = [r["label"] for r in calibration]
    if set(labels) != {0, 1}:
        raise ValueError("Calibration requires both safe and vulnerable examples")
    result = calibrate_threshold([r["p_vulnerable"] for r in calibration], labels)
    threshold = result.best_threshold
    fpr = sum(r["p_vulnerable"] >= threshold for r in specificity) / len(specificity)
    auc = _auc([r["p_vulnerable"] for r in calibration if r["label"] == 1],
               [r["p_vulnerable"] for r in specificity])
    return {"threshold": threshold, "sweep": result.sweep,
            "n_calibration": len(calibration), "n_specificity": len(specificity),
            "specificity_fpr": fpr, "screen_auc": auc,
            "usability_gate_pass": auc >= .65 and fpr < .8,
            "gate_scope": "AUC contrasts calibration positives with held-out safe cases; descriptive screen."}
