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

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np


@dataclass
class Metrics:
    """Classification metrics for one set of (preds, labels)."""
    accuracy: float
    precision: float
    recall: float
    f1: float
    support: int
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
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
        }


def classification_metrics(
    predictions: Sequence[int | bool | None],
    labels: Sequence[int],
    *,
    abstain_value: int = 0,
) -> Metrics:
    """Compute the four headline metrics.

    `None` predictions (e.g. pipeline failures) are treated as `abstain_value`
    by default — i.e. counted as predicting "safe". This is the conservative
    choice for vulnerability detection: we'd rather miss a bug than panic an
    auditor with bad slices, and it matches how the paper reports failures.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must align in length.")

    preds = np.array(
        [abstain_value if p is None else int(bool(p)) for p in predictions],
        dtype=np.int64,
    )
    y = np.array([int(l) for l in labels], dtype=np.int64)

    tp = int(((preds == 1) & (y == 1)).sum())
    fp = int(((preds == 1) & (y == 0)).sum())
    tn = int(((preds == 0) & (y == 0)).sum())
    fn = int(((preds == 0) & (y == 1)).sum())

    support = tp + fp + tn + fn
    accuracy = (tp + tn) / support if support else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return Metrics(
        accuracy=accuracy, precision=precision, recall=recall, f1=f1,
        support=support, tp=tp, fp=fp, tn=tn, fn=fn,
    )


def metrics_by_cwe(
    predictions: Sequence[int | bool | None],
    labels: Sequence[int],
    cwes: Sequence[str],
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
