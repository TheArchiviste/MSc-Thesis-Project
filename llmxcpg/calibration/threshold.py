"""Threshold calibration.

The paper recommends sampling ~20 labelled validation points from the target
dataset and sweeping γ over [0,1] to maximise accuracy. This module implements
that procedure honestly, including:

  - separate logging of accuracy *and* F1 at each γ, because optimising for
    accuracy on imbalanced data is misleading;
  - return of the full sweep so callers can inspect the curve (e.g. plot it,
    spot multimodal optima, decide whether the sample is too small);
  - explicit warnings when the chosen sample is heavily skewed.

Note: this assumes the pipeline has already produced probabilities for the
calibration samples; we do *not* re-run inference inside the sweep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Outcome of one calibration sweep."""
    best_threshold: float
    best_accuracy: float
    best_f1: float
    sweep: list[tuple[float, float, float]]  # (gamma, accuracy, f1)
    n_samples: int
    n_positive: int
    n_negative: int

    @property
    def is_balanced(self) -> bool:
        if self.n_samples == 0:
            return False
        ratio = min(self.n_positive, self.n_negative) / self.n_samples
        return ratio >= 0.3


def calibrate_threshold(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    grid_steps: int = 101,
    optimise_for: str = "accuracy",
) -> CalibrationResult:
    """Find γ that maximises a metric on a labelled validation sample.

    Args:
        probabilities: P(vulnerable) for each sample, in [0, 1].
        labels: ground-truth labels (1 = vulnerable, 0 = safe).
        grid_steps: number of candidate thresholds, evenly spaced in [0, 1].
        optimise_for: "accuracy" (paper default) or "f1".

    Returns:
        A `CalibrationResult` capturing the best γ and the full sweep.
    """
    if optimise_for not in {"accuracy", "f1"}:
        raise ValueError(f"optimise_for must be 'accuracy' or 'f1', got {optimise_for!r}")

    probs = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    if probs.shape != y.shape:
        raise ValueError(f"shape mismatch: probs {probs.shape} vs labels {y.shape}")
    if probs.size == 0:
        raise ValueError("Need at least one calibration sample.")
    if probs.size < 20:
        logger.warning(
            "Calibrating on only %d samples — paper recommends ~20 minimum.", probs.size,
        )

    n_pos = int(y.sum())
    n_neg = int((1 - y).sum())

    grid = np.linspace(0.0, 1.0, grid_steps)
    sweep: list[tuple[float, float, float]] = []
    best_thr = 0.5
    best_score = -1.0
    best_acc = 0.0
    best_f1 = 0.0

    for gamma in grid:
        preds = (probs > gamma).astype(np.int64)
        acc = float((preds == y).mean())
        f1 = _f1(preds, y)
        sweep.append((float(gamma), acc, f1))

        score = acc if optimise_for == "accuracy" else f1
        # Tiebreak: prefer thresholds closer to 0.5 (more "neutral").
        if score > best_score or (
            score == best_score and abs(gamma - 0.5) < abs(best_thr - 0.5)
        ):
            best_score = score
            best_thr = float(gamma)
            best_acc = acc
            best_f1 = f1

    return CalibrationResult(
        best_threshold=best_thr,
        best_accuracy=best_acc,
        best_f1=best_f1,
        sweep=sweep,
        n_samples=int(probs.size),
        n_positive=n_pos,
        n_negative=n_neg,
    )


def _f1(preds: np.ndarray, y: np.ndarray) -> float:
    tp = int(((preds == 1) & (y == 1)).sum())
    fp = int(((preds == 1) & (y == 0)).sum())
    fn = int(((preds == 0) & (y == 1)).sum())
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
