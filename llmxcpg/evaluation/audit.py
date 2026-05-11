"""Query-quality audit harness.

The literature review's strongest critique of LLMxCPG is that **a wrong query
yields a misleading slice that the detector confidently mislabels**, and the
paper's own audit found that 40% of false-classification cases stem from queries
targeting the wrong CWE and 32% from missing critical context.

If you're going to deploy this, you cannot leave that as a footnote. This
module collects exactly the metrics the paper's auditors reported, in a form
you can run yourself:

  - **Validity**: did Joern accept the queries? (cheap, fully automated)
  - **Path coverage**: did the queries return a non-empty execution path?
  - **CWE alignment** (semi-automated): does the query's API surface plausibly
    target the labelled CWE? We use a coarse heuristic — a mapping from
    CWE → "API names you'd expect to see if the query were on-target" — and
    flag mismatches for human review.
  - **Inter-rater agreement**: helper for Fleiss' kappa across 3+ reviewers.

The point is to make the failure breakdown visible, not to fully automate it.
Three security-expert reviewers in the paper achieved Fleiss' κ ≈ 0.64 on 25
samples; this harness records their judgements in the same shape.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence


logger = logging.getLogger(__name__)


# Coarse CWE → expected-API-substring map. NOT a definitive oracle; just a
# heuristic that flags "the query mentions free() and the label is integer
# overflow" so a human reviewer notices.
EXPECTED_APIS: Mapping[str, tuple[str, ...]] = {
    "CWE-119": ("memcpy", "strcpy", "strcat", "memmove", "buffer", "size", "len"),
    "CWE-120": ("strcpy", "strcat", "gets", "sprintf", "buffer", "size"),
    "CWE-121": ("alloca", "stack", "buffer", "strcpy", "memcpy"),
    "CWE-122": ("malloc", "calloc", "realloc", "heap", "memcpy"),
    "CWE-125": ("read", "buffer", "index", "size", "len", "memcmp", "memcpy"),
    "CWE-190": ("+", "*", "<<", "size", "len", "count", "INT_MAX"),
    "CWE-415": ("free", "double", "realloc"),
    "CWE-416": ("free", "use", "ptr", "after"),
    "CWE-787": ("write", "memcpy", "strcpy", "buffer", "index"),
}


@dataclass
class QueryAudit:
    """Audit record for one (code, query bundle, label) triple."""
    sample_id: str
    cwe: str | None
    queries: list[str]
    valid: bool                  # did Joern accept all queries?
    non_empty_path: bool         # did the path query return any flows?
    cwe_alignment_score: float   # in [0, 1], heuristic
    notes: str = ""


def audit_queries(
    sample_id: str,
    queries: Sequence[str],
    cwe: str | None,
    *,
    joern_validity: bool = True,
    non_empty_path: bool = True,
) -> QueryAudit:
    """Run the *automated* portion of the audit on a single sample."""
    score = _alignment_score(queries, cwe) if cwe else 0.0
    notes = []
    if not joern_validity:
        notes.append("Joern rejected one or more queries.")
    if not non_empty_path:
        notes.append("Path query returned no flows.")
    if cwe and score < 0.2:
        notes.append(f"Queries do not surface APIs typical of {cwe}.")

    return QueryAudit(
        sample_id=sample_id,
        cwe=cwe,
        queries=list(queries),
        valid=joern_validity,
        non_empty_path=non_empty_path,
        cwe_alignment_score=score,
        notes=" ".join(notes),
    )


def _alignment_score(queries: Sequence[str], cwe: str) -> float:
    """Fraction of expected-API substrings present anywhere in the queries."""
    expected = EXPECTED_APIS.get(cwe)
    if not expected:
        return 0.0
    blob = "\n".join(queries).lower()
    hits = sum(1 for token in expected if token.lower() in blob)
    return hits / len(expected)


# --------------------------------------------------------------------------- #
# Inter-rater agreement (Fleiss' kappa)
# --------------------------------------------------------------------------- #
def fleiss_kappa(ratings: list[list[int]]) -> float:
    """Compute Fleiss' kappa for inter-rater agreement.

    `ratings` is a list of rows; each row is a per-category count over the
    raters. For binary "matches vulnerability pattern? yes/no" judgements
    across 3 reviewers, each row would be e.g. [2, 1] (2 yes, 1 no).

    Returns kappa in roughly [-1, 1]; >0.6 = substantial agreement (Landis &
    Koch, the same scale the paper cites).
    """
    if not ratings:
        return 0.0
    n_subjects = len(ratings)
    n_raters = sum(ratings[0])
    if any(sum(row) != n_raters for row in ratings):
        raise ValueError("All rows must sum to the same number of raters.")
    if n_raters < 2:
        raise ValueError("Need at least 2 raters for kappa.")
    n_categories = len(ratings[0])

    # P_i: per-subject agreement
    p_i = []
    for row in ratings:
        s = sum(c * (c - 1) for c in row)
        p_i.append(s / (n_raters * (n_raters - 1)))
    p_bar = sum(p_i) / n_subjects

    # P_e: chance agreement
    p_j = [
        sum(row[j] for row in ratings) / (n_subjects * n_raters)
        for j in range(n_categories)
    ]
    p_e_bar = sum(pj * pj for pj in p_j)

    if p_e_bar == 1.0:
        return 1.0
    return (p_bar - p_e_bar) / (1.0 - p_e_bar)


# --------------------------------------------------------------------------- #
# Aggregate audit summary in the form the paper reports
# --------------------------------------------------------------------------- #
def summarise_audit(audits: list[QueryAudit]) -> dict:
    """Produce the same shape of summary the paper provides in §4.3.1."""
    if not audits:
        return {}
    n = len(audits)
    valid_rate = sum(1 for a in audits if a.valid) / n
    path_rate = sum(1 for a in audits if a.non_empty_path) / n
    avg_alignment = sum(a.cwe_alignment_score for a in audits) / n
    note_buckets = Counter()
    for a in audits:
        if a.notes:
            note_buckets[a.notes] += 1
    return {
        "n": n,
        "joern_validity_rate": valid_rate,
        "non_empty_path_rate": path_rate,
        "mean_cwe_alignment": avg_alignment,
        "common_failure_notes": note_buckets.most_common(5),
    }
