"""RQ1 scientific safeguards; simulations here are tests, never observations."""
from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from evidence_experiment.analysis import analyze
from evidence_experiment.bounded_joern import BoundedJoern
from evidence_experiment.locks import (
    check_stage_receipts,
    lock_inputs,
    require_witnesses,
    write_stage_receipt,
)
from evidence_experiment.review import packet_index
from evidence_experiment.rq1_report import initial_decoy_summary, write_report
from evidence_experiment.runner import PINNED_PIPELINE_COMMIT, extract_slices, generate_queries
from evidence_experiment.schema import append_jsonl, load_cases, read_jsonl, run_specs
from evidence_experiment.validate import validate_witnesses
from llmxcpg.inference.query_generator import QueryGenerationOutput
from llmxcpg.joern.client import JoernError
from rq1 import assess, setup


@pytest.fixture
def baseline(tmp_path):
    (tmp_path / "u.c").write_text("char buf[4];\nmemcpy(buf,p,8);\n")
    (tmp_path / "f.c").write_text("char buf[8];\nmemcpy(buf,p,8);\n")
    manifest = tmp_path / "cases.jsonl"
    append_jsonl(manifest, {"case_id": "one", "cluster_id": "one_block", "cwe": "CWE121",
                           "sources": {"U": "u.c", "F": "f.c"}, "referent": {
                               "elements": [{"id": "capacity", "role": "capacity", "lines": [1]},
                                            {"id": "sink", "role": "sink", "lines": [2]}],
                               "relations": ["eight bytes exceed four"]}})
    cases = load_cases(manifest)
    return tmp_path, manifest, cases


def evidence(baseline, repeats=1, primary="inadequate", failure=None):
    work, _, cases = baseline
    for spec in run_specs(cases, repeats):
        selected = [2] if spec["arm"] == "U" and spec["repeat"] == 0 and primary == "inadequate" else [1, 2]
        append_jsonl(work / "slices.jsonl", {**spec, "status": failure or "ok",
                                            "slice_lines": selected, "rendered_lines": selected})
    packets, joins = packet_index(cases, work, repeats)
    ratings, matches = work / "ratings.jsonl", work / "matches.jsonl"
    ratings.touch()
    matches.touch()
    for rid, packet in packets.items():
        good = "char buf[4]" in packet["code"]
        append_jsonl(ratings, {"review_id": rid, "assessor_id": "codex_ai_assessor",
                              "adequacy": "adequate" if good else "inadequate",
                              "cited_lines": [1, 2] if good else [],
                              "relationships": ["copy exceeds capacity"] if good else [],
                              "explanation": "The visible size comparison suffices" if good else "No visible support for the claimed violation"})
    for rid in set(joins.values()):
        append_jsonl(matches, {"case_id": "one", "review_id": rid, "match": "yes",
                              "reason": "Visible explanation matches the source-grounded violation"})
    return ratings, matches


def test_single_ai_is_explicit_and_default_still_requires_independence(baseline):
    work, _, cases = baseline
    ratings, matches = evidence(baseline, primary="adequate")
    (work / "detector.jsonl").write_text("invalid irrelevant D data\n")
    default = analyze(cases, work, ratings, matches, repeats=1, evidence_only=True)
    assert default["rq1"]["adequacy"] == {"uncertain": 1}
    report = analyze(cases, work, ratings, matches, repeats=1,
                     evidence_only=True, assessment_mode="assistant")
    assert report["rq1"]["adequacy"] == {"adequate": 1}
    assert report["rq1"]["verdicts_repeat0"] == {"not_run": 1}
    assert report["review_quality"]["agreement"]["inter_rater_reliability"] is None
    assert "AI-assisted" in report["assessment_limit"]


def test_primary_repeat_does_not_become_a_majority_vote(baseline):
    work, _, cases = baseline
    ratings, matches = evidence(baseline, repeats=3)
    report = analyze(cases, work, ratings, matches, repeats=3,
                     evidence_only=True, assessment_mode="assistant")
    assert report["rq1"]["adequacy"] == {"inadequate": 1}
    assert report["primary_run_rule"] == "repeat_0"


@pytest.mark.parametrize("failure", ["query_parse", "context_overflow", "joern_transport", "timeout", "worker_reset_failed"])
def test_terminal_no_evidence_stays_in_enrolled_denominator(baseline, failure):
    work, _, cases = baseline
    ratings, matches = evidence(baseline, failure=failure)
    report = analyze(cases, work, ratings, matches, repeats=1,
                     evidence_only=True, assessment_mode="assistant")
    assert report["rq1"]["cases"] == 1
    assert report["rq1"]["adequacy"] == {"inadequate": 1}
    write_report(cases, work, report, ratings, matches)
    assert "false adequacy not estimable" in (work / "rq1_report.md").read_text()


def test_readable_report_separates_line_overlap_from_adequacy(baseline):
    work, _, cases = baseline
    ratings, matches = evidence(baseline)
    report = analyze(cases, work, ratings, matches, repeats=1,
                     evidence_only=True, assessment_mode="assistant")
    write_report(cases, work, report, ratings, matches)
    assert "identification bounds, not confidence intervals" in (work / "rq1_report.md").read_text()
    assert "capacity" in (work / "rq1_cases.csv").read_text()
    assert "any_line_rendered" in (work / "rq1_element_visibility.csv").read_text()


def test_initial_f_false_adequacy_is_preserved_separately(baseline):
    work, _, cases = baseline
    ratings, matches = evidence(baseline)
    report = analyze(cases, work, ratings, matches, repeats=1,
                     evidence_only=True, assessment_mode="assistant")
    initial = work / "initial.jsonl"
    packets, _ = packet_index(cases, work, 1)
    for row in read_jsonl(ratings):
        row["adequacy"] = "adequate"
        row["cited_lines"] = [2]
        row["relationships"] = ["Deliberately mistaken initial size assumption"]
        append_jsonl(initial, row)
    summary = initial_decoy_summary(cases, work, report, initial, 1)
    assert summary["initial_false_adequate"] == summary["shown_F"] == 1
    assert len(packets) == 2
    assert next(r for r in report["run_evidence"] if r["arm"] == "F")["adequacy"] == "inadequate"


def test_gpu_query_and_cpu_slicing_use_separate_environment_locks(baseline, monkeypatch):
    work, manifest, cases = baseline
    config = work / "config.json"
    config.write_text(json.dumps({"pipeline_commit": PINNED_PIPELINE_COMMIT, "allow_dummy": True}))
    from evidence_experiment import locks
    monkeypatch.setattr(locks, "package_versions", lambda names: {n: "gpu_version" for n in names})
    lock_inputs(work, manifest, config, cases, 1, phase="query")
    monkeypatch.setattr(locks, "package_versions", lambda names: {n: "cpu_version" for n in names})
    lock_inputs(work, manifest, config, cases, 1, phase="slice")
    with pytest.raises(ValueError, match="packages changed"):
        lock_inputs(work, manifest, config, cases, 1, phase="query")


def test_completed_outputs_cannot_be_edited(baseline):
    work, _, _ = baseline
    (work / "queries.jsonl").write_text("original bytes")
    write_stage_receipt(work, "query")
    (work / "queries.jsonl").write_text("edited bytes")
    with pytest.raises(ValueError, match="stage output changed"):
        check_stage_receipts(work)


def test_one_oversized_prompt_does_not_abort_other_inputs(baseline, monkeypatch):
    work, _, cases = baseline
    from evidence_experiment import runner
    def check(generator, source):
        if "buf[4]" in source:
            raise ValueError("Too long")
        return 12
    monkeypatch.setattr(runner, "_check_q_context", check)
    q = SimpleNamespace(generate_batch=lambda codes: [QueryGenerationOutput(["val source = 1"], "test", True) for _ in codes])
    generate_queries(cases, work, {"query_batch_size": 2}, repeats=1, generator=q)
    rows = read_jsonl(work / "queries.jsonl")
    assert [r["status"] for r in rows] == ["context_overflow", "ok"]
    assert rows[1]["prompt_tokens"] == 12


def test_real_source_corpus_has_disjoint_blocks_and_twelve_main_cases():
    assert setup.verify_corpus() == {"development": 3, "main": 12}
    statuses = [r["status"] for r in read_jsonl(setup.CORPUS / "selection_ledger.jsonl")]
    assert statuses.count("excluded_before_inference") == 2
    assert statuses.count("reserve_not_enrolled") == 3
    assert len(read_jsonl(setup.CORPUS / "referents.jsonl")) == 15


def test_tampered_line_map_is_rejected(tmp_path, monkeypatch):
    copy = tmp_path / "rq1"
    shutil.copytree(setup.CORPUS, copy)
    monkeypatch.setattr(setup, "CORPUS", copy)
    path = copy / "generated/D01_U.map.json"
    obj = json.loads(path.read_text())
    obj["upstream_line_for_generated_line"][0] += 1
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="Line map changed"):
        setup.verify_corpus()


@pytest.mark.skipif(not shutil.which("gcc"), reason="Real LP64 GCC/ASan witness")
def test_baseline_witness_executes_u_and_f_and_enforces_plan_hash(tmp_path):
    manifest = setup.CORPUS / "development.jsonl"
    cases = load_cases(manifest)[:1]
    validate_witnesses(cases, manifest, setup.CORPUS / "witness_plan.jsonl",
                       tmp_path / "witness_validation.jsonl")
    require_witnesses(tmp_path, cases)
    row = read_jsonl(tmp_path / "witness_validation.jsonl")[0]
    assert row["checks"]["trigger"] == row["checks"]["fixed"] == "pass"
    assert "gcc" in row["compiler"]["stdout"].lower()
    row["witness_plan_sha256"] = "changed"
    (tmp_path / "witness_validation.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="witness missing, failed or changed"):
        require_witnesses(tmp_path, cases)


def test_main_is_blocked_until_real_development_freeze(tmp_path):
    cfg = json.loads((setup.CORPUS / "config.example.json").read_text())
    cfg["joern_digest"] = "sha256:" + "a" * 64
    cfg["rq1_freeze_file"] = str(tmp_path / "not_frozen.json")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match="blocked until the real development report"):
        setup.check_acquisition_ready(setup.CORPUS / "main.jsonl", path)


def test_rpc_timeout_becomes_transport_outcome():
    def fail(query):
        raise TimeoutError("RPC timeout test")
    bounded = BoundedJoern(SimpleNamespace(run=fail), 1, 2)
    bounded.begin_case()
    with pytest.raises(JoernError, match="RPC timeout"):
        bounded.run("test")


def test_transport_retries_are_capped_and_logged(baseline):
    work, _, cases = baseline
    cases = [replace(cases[0], sources={"U": cases[0].sources["U"]})]
    spec = run_specs(cases, 1)[0]
    append_jsonl(work / "queries.jsonl", {"run_id": spec["run_id"], "status": "ok", "queries": [
        'val source = cpg.identifier.name("buf").l',
        'val sink = cpg.call.name("memcpy").l',
        'val execution_path = sink.reachableByFlows(source).l']})
    class Disconnected:
        def import_code(self, *args, **kwargs):
            raise JoernError("connection refused")
        def reset(self):
            pass
    for _ in range(3):
        with pytest.raises(RuntimeError, match="(Infrastructure|Terminal infrastructure)"):
            extract_slices(cases, work, {"infrastructure_attempts": 3}, 1, Disconnected())
    extract_slices(cases, work, {"infrastructure_attempts": 3}, 1, Disconnected())
    assert len(read_jsonl(work / "slice_attempts.jsonl")) == 3
    assert len(read_jsonl(work / "slices.jsonl")) == 1


def test_saved_semantic_failure_is_not_retried(baseline):
    work, _, cases = baseline
    cases = [replace(cases[0], sources={"U": cases[0].sources["U"]})]
    spec = run_specs(cases, 1)[0]
    append_jsonl(work / "queries.jsonl", {"run_id": spec["run_id"], "status": "ok", "queries": []})
    append_jsonl(work / "slice_attempts.jsonl", {"run_id": spec["run_id"], "attempt": 1,
                                               "outcome": {"status": "query_exec", "trace": []}})
    extract_slices(cases, work, {"infrastructure_attempts": 3}, 1, object())
    assert read_jsonl(work / "slices.jsonl")[0]["status"] == "query_exec"
    assert len(read_jsonl(work / "slice_attempts.jsonl")) == 1


def test_short_reassessment_delay_is_reported_honestly(tmp_path):
    first, second = tmp_path / "first.jsonl", tmp_path / "second.jsonl"
    now = datetime.now(timezone.utc)
    for rid in ("a", "b", "c", "d"):
        append_jsonl(tmp_path / "assessment_order.jsonl", {"review_id": rid, "code": "test"})
        append_jsonl(first, {"review_id": rid, "assessor_id": "codex_ai_assessor", "adequacy": "uncertain",
                            "assessed_utc": (now - timedelta(hours=72)).isoformat()})
    assess.reassessment_plan(tmp_path, first)
    plan = json.loads((tmp_path / "reassessment_plan.json").read_text())
    assert len(plan["subset"]) == 1
    append_jsonl(second, {"review_id": plan["subset"][0]["review_id"], "assessor_id": "codex_ai_assessor",
                         "adequacy": "uncertain", "assessed_utc": (now - timedelta(hours=48)).isoformat()})
    assess.consistency(tmp_path, first, second)
    result = json.loads((tmp_path / "consistency.json").read_text())
    assert result["all_met_48_hours"] is False
    assert result["agreement"] == 1
