"""Classification metrics matching the paper's reporting style.

Tables 3, 4, 5, 7, 8 of the paper all use the same four metrics: accuracy,
precision, recall, F1. We report them at three granularities:

  - overall (Table 3, 5, 7)
  - per-CWE (Tables 4, 8)
  - per-transformation (Table 10)

Reduction-ratio statistics for the slicing stage match §4.3.1 of the paper
(the 67-91% range across datasets).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class Metrics:
    """Classification metrics for one set of (preds, labels)."""
    accuracy: float
    precision: float
    recall: float
    f1: float
    support: int
    total: int
    abstentions: int
    coverage: float
    tp: int
    fp: int
    tn: int
    fn: int

    def as_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "support": self.support,
            "total": self.total,
            "abstentions": self.abstentions,
            "coverage": self.coverage,
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
        }


def classification_metrics(
    predictions: Sequence[int | bool | None],
    labels: Sequence[int],
    *,
    failure_policy: str = "exclude",
) -> Metrics:
    """Compute the four headline metrics.

    `None` is an abstention, not a SAFE verdict. By default abstentions are
    excluded from discrimination metrics and reported through coverage. Set
    `failure_policy` to "safe" or "vulnerable" to include failures as an
    explicit predicted class, or "error" to reject any failed samples.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must align in length.")

    if failure_policy not in {"exclude", "safe", "vulnerable", "error"}:
        raise ValueError("failure_policy must be exclude, safe, vulnerable, or error.")

    abstentions = sum(p is None for p in predictions)
    if failure_policy == "error" and abstentions:
        raise ValueError(f"Received {abstentions} abstaining predictions.")

    pairs = [(p, l) for p, l in zip(predictions, labels) if p is not None]
    if failure_policy in {"safe", "vulnerable"}:
        fill = failure_policy == "vulnerable"
        pairs = [(fill if p is None else p, l) for p, l in zip(predictions, labels)]

    preds = np.array([int(bool(p)) for p, _ in pairs], dtype=np.int64)
    y = np.array([int(l) for _, l in pairs], dtype=np.int64)

    tp = int(((preds == 1) & (y == 1)).sum())
    fp = int(((preds == 1) & (y == 0)).sum())
    tn = int(((preds == 0) & (y == 0)).sum())
    fn = int(((preds == 0) & (y == 1)).sum())

    support = tp + fp + tn + fn
    total = len(labels)
    accuracy = (tp + tn) / support if support else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return Metrics(
        accuracy=accuracy, precision=precision, recall=recall, f1=f1,
        support=support,
        total=total,
        abstentions=abstentions,
        coverage=((total - abstentions) / total if total else 0.0),
        tp=tp, fp=fp, tn=tn, fn=fn,
    )


def metrics_by_cwe(
    predictions: Sequence[int | bool | None],
    labels: Sequence[int],
    cwes: Sequence[str],
    *,
    failure_policy: str = "exclude",
) -> dict[str, Metrics]:
    """Group metrics by CWE label, matching Tables 4 and 8 of the paper."""
    if not (len(predictions) == len(labels) == len(cwes)):
        raise ValueError("predictions, labels, cwes must align in length.")

    by_cwe: dict[str, list[int]] = {}
    for i, c in enumerate(cwes):
        by_cwe.setdefault(c, []).append(i)

    return {
        cwe: classification_metrics(
            [predictions[i] for i in idxs],
            [labels[i] for i in idxs],
            failure_policy=failure_policy,
        )
        for cwe, idxs in by_cwe.items()
    }


def reduction_ratio_stats(
    original_lengths: Sequence[int],
    slice_lengths: Sequence[int],
) -> dict:
    """Slice-construction reduction stats (§4.3.1)."""
    if not original_lengths:
        return {"mean_reduction": 0.0, "median_reduction": 0.0, "n": 0}
    orig = np.asarray(original_lengths, dtype=np.float64)
    slc = np.asarray(slice_lengths, dtype=np.float64)
    ratios = 1.0 - (slc / np.maximum(orig, 1.0))
    return {
        "mean_reduction": float(ratios.mean()),
        "median_reduction": float(np.median(ratios)),
        "p25_reduction": float(np.percentile(ratios, 25)),
        "p75_reduction": float(np.percentile(ratios, 75)),
        "n": int(orig.size),
    }
