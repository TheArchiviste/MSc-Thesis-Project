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

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from llmxcpg.calibration.threshold import calibrate_threshold
from llmxcpg.data.esbmc_cwe_mapping import esbmc_error_to_cwe
from llmxcpg.evaluation.audit import (
    audit_queries, fleiss_kappa, _alignment_score,
)
from llmxcpg.evaluation.metrics import classification_metrics, metrics_by_cwe
from llmxcpg.data.prepare import build_d_training_set
from llmxcpg.inference.pipeline import LLMxCPGPipeline
from llmxcpg.inference.query_generator import QueryGenerationOutput, QueryGenerator
from llmxcpg.joern.queries import build_interacters_query, validate_generated_query
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
    assert cal.best_threshold <= 0.1
    assert cal.best_f1 == 1.0


def test_calibration_threshold_boundary_matches_inference():
    cal = calibrate_threshold([0.5], [1], grid_steps=3)
    assert cal.best_threshold == 0.5


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
    assert "## Instruction:" in rendered_d
    assert "## Input:" in rendered_d
    assert rendered_d.endswith("## Response:\n")
    assert "One word: VULNERABLE or BENIGN" in rendered_d


def test_detector_training_data_uses_released_labels_and_prompt():
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "d.jsonl"
        count = build_d_training_set([
            {"slice": "free(ptr);", "is_vulnerable": True},
            {"slice": "return 0;", "is_vulnerable": False},
        ], output)
        records = [json.loads(line) for line in output.read_text().splitlines()]
    assert count == 2
    assert [record["output"] for record in records] == ["Yes", "No"]
    assert all(record["instruction"].endswith("## Response:\n") for record in records)


def test_query_parser_requires_final_reachable_by_flows():
    output = QueryGenerator._parse('{"queries": ["cpg.call.l"]}')
    assert not output.parsed_ok
    assert "reachableByFlows" in output.error


def test_dummy_query_generator_obeys_query_contract():
    output = QueryGenerator("unused", engine="dummy").generate("int main() {}")
    assert output.parsed_ok
    assert "reachableByFlows" in output.queries[-1]


def test_pipeline_preserves_abstention_contract_and_cleans_joern():
    class FakeQ:
        uses_local_gpu = False

        def generate(self, code):
            return QueryGenerationOutput(
                ['val execution_path = sink.reachableByFlows(source).l'], "", True,
            )

    class FakeD:
        def classify(self, code, threshold):
            return SimpleNamespace(
                is_vulnerable=True,
                probability_vulnerable=0.9,
                probability_safe=0.1,
            )

    class FakeJoern:
        resets = 0

        def reset(self):
            self.resets += 1

    joern = FakeJoern()
    pipeline = LLMxCPGPipeline(FakeQ(), FakeD(), joern)
    pipeline.slicer = SimpleNamespace(
        extract=lambda source, queries, project_name: SimpleNamespace(code=source),
    )
    result = pipeline.detect("int main() {}")
    assert result.succeeded
    assert result.is_vulnerable is True
    assert result.probability_vulnerable == 0.9
    assert joern.resets == 1


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


def test_generated_query_guard_rejects_process_execution():
    with pytest.raises(ValueError):
        validate_generated_query('Runtime.getRuntime().exec("id")')
    with pytest.raises(ValueError):
        validate_generated_query('System.getProperty("user.home")')


def test_generated_query_guard_accepts_cpg_traversal():
    validate_generated_query('val execution_path = sink.reachableByFlows(source).l')


def test_joern_client_stages_container_path_and_cleans_up():
    import llmxcpg.joern.client as client_module

    calls = []

    class FakeClient:
        def __init__(self, endpoint, auth_credentials=None):
            self.endpoint = endpoint

        def execute(self, query):
            calls.append(query)
            return {"stdout": "val1: String = ok", "stderr": "", "success": True}

    original_client = client_module.CPGQLSClient
    original_import = client_module.import_code_query
    client_module.CPGQLSClient = FakeClient
    client_module.import_code_query = lambda path, project: f"importCode({path!r}, {project!r})"
    try:
        with tempfile.TemporaryDirectory() as directory:
            client = client_module.JoernClient(
                local_input_dir=directory, server_input_dir="/analysis/inputs",
            )
            client.import_code("int main(void) { return 0; }", project_name="unsafe name")
            assert "/analysis/inputs/llmxcpg_" in calls[-1]
            staged = list(Path(directory).iterdir())
            assert len(staged) == 1
            assert (staged[0] / "unsafe_name.c").exists()
            loaded = client._project_loaded
            client.reset()
            assert calls[-1] == f'delete("{loaded}")'
            assert list(Path(directory).iterdir()) == []
    finally:
        client_module.CPGQLSClient = original_client
        client_module.import_code_query = original_import


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


def test_classification_metrics_reports_abstentions_and_coverage():
    preds = [None, None, 1, 0]
    labels = [1, 0, 1, 0]
    m = classification_metrics(preds, labels)
    assert m.fn == 0
    assert m.tn == 1
    assert m.support == 2
    assert m.total == 4
    assert m.abstentions == 2
    assert m.coverage == 0.5


def test_classification_metrics_can_count_abstentions_as_safe():
    preds = [None, None, 1, 0]
    labels = [1, 0, 1, 0]
    m = classification_metrics(preds, labels, failure_policy="safe")
    assert m.fn == 1
    assert m.tn == 2
    assert m.support == 4
    assert m.coverage == 0.5


def test_classification_metrics_rejects_unknown_failure_policy():
    with pytest.raises(ValueError):
        classification_metrics([None], [1], failure_policy="guess")


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
