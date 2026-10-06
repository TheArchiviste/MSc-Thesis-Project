"""Small-sample statistics for paired adequacy loss and reviewer agreement.

No external dependencies, so the reporter runs on a laptop without SciPy.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

Z95 = 1.959963984540054
CATEGORIES = ("adequate", "inadequate", "uncertain")


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denominator = 1 + z * z / n
    return max(0.0, (centre - half) / denominator), min(1.0, (centre + half) / denominator)


def newcombe_paired(both: int, first_only: int, second_only: int, neither: int,
                    z: float = Z95) -> tuple[float, float]:
    """Newcombe (1998) method 10 interval for p1 - p2 from paired binary data.

    ``both`` and ``neither`` are concordant pairs; ``first_only`` counts pairs
    where only the first outcome occurred (here: loss under TM only).
    """
    n = both + first_only + second_only + neither
    if n == 0:
        return -1.0, 1.0
    p1, p2 = (both + first_only) / n, (both + second_only) / n
    l1, u1 = wilson(both + first_only, n, z)
    l2, u2 = wilson(both + second_only, n, z)
    denominator = math.sqrt((both + first_only) * (second_only + neither) *
                            (both + second_only) * (first_only + neither))
    numerator = both * neither - first_only * second_only
    # Method 10 corrects positive association towards zero (section 5).
    # The uncorrected coefficient is method 8 and gives a zero-width interval
    # for perfectly concordant, nonconstant pairs.
    if numerator > 0:
        numerator = max(0.0, numerator - n / 2)
    phi = numerator / denominator if denominator else 0.0
    d = p1 - p2
    delta = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    epsilon = math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    return max(-1.0, d - delta), min(1.0, d + epsilon)


def mcnemar_exact_p(first_only: int, second_only: int) -> float:
    """Two-sided exact McNemar (binomial) p-value on the discordant pairs."""
    n = first_only + second_only
    if n == 0:
        return 1.0
    k = min(first_only, second_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _usable(items: Sequence[Sequence[str]]) -> list[Sequence[str]]:
    return [item for item in items if len(item) >= 2]


def percent_agreement(items: Sequence[Sequence[str]]) -> float | None:
    """Mean pairwise agreement within items (packets) rated at least twice."""
    usable = _usable(items)
    if not usable:
        return None
    scores = []
    for item in usable:
        counts = Counter(item)
        m = len(item)
        scores.append(sum(c * (c - 1) for c in counts.values()) / (m * (m - 1)))
    return sum(scores) / len(scores)


def _prevalence(usable: list[Sequence[str]], categories: Sequence[str]) -> dict[str, float]:
    total = sum(len(item) for item in usable)
    counts = Counter(rating for item in usable for rating in item)
    return {c: counts[c] / total for c in categories}


def fleiss_kappa(items: Sequence[Sequence[str]],
                 categories: Sequence[str] = CATEGORIES) -> float | None:
    """Fleiss' kappa, generalised to a varying number (>= 2) of raters per item."""
    usable = _usable(items)
    observed = percent_agreement(usable)
    if observed is None:
        return None
    expected = sum(p * p for p in _prevalence(usable, categories).values())
    return None if expected == 1 else (observed - expected) / (1 - expected)


def gwet_ac1(items: Sequence[Sequence[str]],
             categories: Sequence[str] = CATEGORIES) -> float | None:
    """Gwet's AC1, which is less distorted than kappa when one rating dominates."""
    usable = _usable(items)
    observed = percent_agreement(usable)
    if observed is None or len(categories) < 2:
        return None
    prevalence = _prevalence(usable, categories)
    expected = sum(p * (1 - p) for p in prevalence.values()) / (len(categories) - 1)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def agreement_summary(items: Sequence[Sequence[str]]) -> dict[str, float | int | None]:
    usable = _usable(items)
    return {"packets": len(usable), "ratings": sum(len(item) for item in usable),
            "percent_agreement": percent_agreement(usable),
            "fleiss_kappa": fleiss_kappa(usable), "gwet_ac1": gwet_ac1(usable)}
