"""Tests for the pieces that don't require a Joern server or GPU.

Covers:
  - line-anchored slice reconstruction
  - threshold calibration sweep
  - ESBMC -> CWE mapping
  - prompt rendering
  - CPGQL query templates
  - audit-harness alignment scoring and Fleiss' kappa

Run with: pytest tests/ -v
"""

from __future__ import annotations

import pytest

from llmxcpg.calibration.threshold import calibrate_threshold
from llmxcpg.data.esbmc_cwe_mapping import esbmc_error_to_cwe
from llmxcpg.evaluation.audit import (
    audit_queries, fleiss_kappa, _alignment_score,
)
from llmxcpg.evaluation.metrics import classification_metrics, metrics_by_cwe
from llmxcpg.joern.queries import build_interacters_query
from llmxcpg.prompts import render_query_prompt, render_detection_prompt
from llmxcpg.slicing.reconstruction import reconstruct_code_from_lines


# --------------------------------------------------------------------------- #
# Reconstruction
# --------------------------------------------------------------------------- #
SAMPLE_C = """\
#include <string.h>

void process(char *src, int n) {
    char buf[16];
    int i = 0;
    if (n < 0) return;
    memcpy(buf, src, n);
    i = 1;
}

int main(void) {
    char input[64];
    process(input, 100);
    return 0;
}
"""


def test_reconstruction_includes_function_anchor():
    # Slice picks just the memcpy line. Reconstruction should bring back the
    # function header and closing brace so the snippet is parseable.
    slice_lines = [7]  # the memcpy
    snippet = reconstruct_code_from_lines(SAMPLE_C, slice_lines)
    assert "memcpy(buf, src, n);" in snippet
    assert "void process" in snippet  # header anchor
    assert "}" in snippet              # close-brace anchor


def test_reconstruction_with_empty_slice():
    assert reconstruct_code_from_lines(SAMPLE_C, []) == ""


def test_reconstruction_ignores_out_of_range_lines():
    snippet = reconstruct_code_from_lines("a\nb\nc\n", [99])
    assert snippet == ""


def test_reconstruction_preserves_order():
    snippet = reconstruct_code_from_lines(SAMPLE_C, [4, 7], add_function_anchors=False)
    lines = snippet.splitlines()
    assert lines[0].strip().startswith("char buf")
    # there's a blank gap between line 4 and line 7
    assert "" in lines


# --------------------------------------------------------------------------- #
# Threshold calibration
# --------------------------------------------------------------------------- #
def test_calibration_perfect_separation():
    probs = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9] * 4  # 24 samples, 12 vs 12
    labels = [0, 0, 0, 1, 1, 1] * 4
    cal = calibrate_threshold(probs, labels)
    assert cal.best_accuracy == 1.0
    assert 0.3 <= cal.best_threshold <= 0.7
    assert cal.is_balanced


def test_calibration_returns_full_sweep():
    cal = calibrate_threshold([0.1, 0.9] * 10, [0, 1] * 10, grid_steps=11)
    assert len(cal.sweep) == 11
    for gamma, acc, f1 in cal.sweep:
        assert 0.0 <= gamma <= 1.0
        assert 0.0 <= acc <= 1.0
        assert 0.0 <= f1 <= 1.0


def test_calibration_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        calibrate_threshold([0.5], [0, 1])


def test_calibration_optimise_for_f1():
    # All-positive labels: accuracy is maximised by predicting all positive
    # (γ → 0), but F1 also peaks there — so they should agree.
    probs = [0.1, 0.2, 0.3, 0.4]
    labels = [1, 1, 1, 1]
    cal = calibrate_threshold(probs, labels, optimise_for="f1")
    assert cal.best_threshold < 0.1
    assert cal.best_f1 == 1.0


# --------------------------------------------------------------------------- #
# ESBMC mapping
# --------------------------------------------------------------------------- #
def test_esbmc_mapping_known_patterns():
    assert esbmc_error_to_cwe("dereference failure: array bounds violated") == "CWE-119"
    assert esbmc_error_to_cwe("arithmetic overflow on add") == "CWE-190"
    assert esbmc_error_to_cwe("Double free detected at line 42") == "CWE-415"
    assert esbmc_error_to_cwe("use after free") == "CWE-416"


def test_esbmc_mapping_unknown():
    assert esbmc_error_to_cwe("VERIFICATION SUCCESSFUL") is None
    assert esbmc_error_to_cwe("") is None
    assert esbmc_error_to_cwe(None) is None


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
def test_prompts_substitute_code():
    rendered = render_query_prompt("int main() { return 0; }")
    assert "int main()" in rendered
    assert "<CODE>" not in rendered

    rendered_d = render_detection_prompt("memcpy(a, b, n);")
    assert "memcpy(a, b, n);" in rendered_d
    assert "VULNERABLE" in rendered_d
    assert "SAFE" in rendered_d


# --------------------------------------------------------------------------- #
# CPGQL query construction
# --------------------------------------------------------------------------- #
def test_interacters_query_requires_execution_path_var():
    # Builder should reject a binding that doesn't define `execution_path`.
    with pytest.raises(ValueError):
        build_interacters_query("val foo = cpg.method.l")


def test_interacters_query_accepts_valid_binding():
    q = build_interacters_query("val execution_path = sink.reachableByFlows(source).l")
    assert "execution_path" in q
    assert "interacters" in q


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def test_classification_metrics_basic():
    preds = [1, 1, 0, 0, 1, 0]
    labels = [1, 0, 0, 1, 1, 0]
    m = classification_metrics(preds, labels)
    assert m.tp == 2
    assert m.fp == 1
    assert m.tn == 2
    assert m.fn == 1
    assert m.support == 6
    assert pytest.approx(m.accuracy, rel=1e-6) == 4 / 6


def test_classification_metrics_treats_none_as_safe():
    # Pipeline failures are conservative SAFE predictions
    preds = [None, None, 1, 0]
    labels = [1, 0, 1, 0]
    m = classification_metrics(preds, labels)
    assert m.fn == 1   # one None on a vulnerable sample → false negative
    assert m.tn == 2   # one None on a safe + one real-safe correct → 2


def test_metrics_by_cwe_groups_correctly():
    preds = [1, 0, 1, 0]
    labels = [1, 0, 0, 0]
    cwes = ["CWE-119", "CWE-119", "CWE-416", "CWE-416"]
    out = metrics_by_cwe(preds, labels, cwes)
    assert set(out) == {"CWE-119", "CWE-416"}
    assert out["CWE-119"].support == 2
    assert out["CWE-119"].accuracy == 1.0


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def test_alignment_score_picks_up_relevant_apis():
    queries = [
        'val source = cpg.call.name("malloc").l',
        'val sink = cpg.call.name("memcpy").l',
        "val execution_path = sink.reachableByFlows(source).l",
    ]
    score_122 = _alignment_score(queries, "CWE-122")  # heap overflow
    score_415 = _alignment_score(queries, "CWE-415")  # double free
    assert score_122 > score_415


def test_audit_flags_invalid_queries():
    audit = audit_queries("s1", queries=["bad"], cwe="CWE-119",
                          joern_validity=False, non_empty_path=False)
    assert not audit.valid
    assert "rejected" in audit.notes
    assert "no flows" in audit.notes


def test_fleiss_kappa_perfect_agreement():
    # 3 raters, 4 subjects, all rate "yes" → kappa is undefined-but-1.
    ratings = [[3, 0], [3, 0], [3, 0], [3, 0]]
    assert fleiss_kappa(ratings) == 1.0


def test_fleiss_kappa_validates_input():
    with pytest.raises(ValueError):
        fleiss_kappa([[3, 0], [2, 0]])  # uneven rater counts


def test_fleiss_kappa_chance_level():
    # Random-looking judgements; just ensure the value is in [-1, 1] and that
    # mixed agreement gives a value below 1.
    ratings = [[2, 1], [1, 2], [2, 1], [1, 2], [3, 0], [0, 3]]
    k = fleiss_kappa(ratings)
    assert -1.0 <= k <= 1.0
    assert k < 1.0
