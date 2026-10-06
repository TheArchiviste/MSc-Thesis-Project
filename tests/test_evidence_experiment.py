"""Tests of the revised estimand and population, independent of GPU/Joern."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evidence_experiment.analysis import analyze
from evidence_experiment.runner import _failure_status, packet_index
from evidence_experiment.schema import REQUIRED_CHECKS, append_jsonl, load_cases, run_specs


class ExperimentAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        (self.root / "original.c").write_text("char buf[4];\nmemcpy(buf,p,8);\n")
        (self.root / "treated.c").write_text("char *alias=buf;\nmemcpy(alias,p,8);\n")
        (self.root / "control.c").write_text("char buf[4];\nmemcpy(buf,p,8);\n")
        (self.root / "missed.c").write_text("memcpy(p,q,8);\n")
        self.manifest = self.root / "cases.jsonl"
        append_jsonl(self.manifest, {
            "case_id": "missed", "cluster_id": "family_a", "cwe": "CWE-121",
            "sources": {"U": "missed.c"},
            "referent": {"elements": [{"id": "sink", "role": "sink", "lines": [1]}],
                         "relations": ["bounds and length"]},
        })
        append_jsonl(self.manifest, {
            "case_id": "paired", "cluster_id": "family_b", "cwe": "CWE-121",
            "sources": {"U": "original.c", "TM": "treated.c", "TN": "control.c"},
            "referent": {"elements": [
                {"id": "sink", "role": "sink", "lines": [2],
                 "mapped_lines": {"TM": [2], "TN": [2]}},
                {"id": "bound", "role": "allocation", "lines": [1],
                 "mapped_lines": {"TM": [1], "TN": [1]}}],
                "relations": ["copy length exceeds buffer"],
                "target_lines": [2], "control_lines": [1]},
            "operator": "alias", "validation": {key: "pass" for key in REQUIRED_CHECKS},
            "control_in_slice": True,
        })
        self.cases = load_cases(self.manifest)
        for spec in run_specs(self.cases):
            arm, cid = spec["arm"], spec["case_id"]
            selected = [1] if cid == "missed" else [2] if arm.startswith("TM") else [1, 2]
            source = next(c for c in self.cases if c.case_id == cid).source_for(arm)
            append_jsonl(self.work / "slices.jsonl", {
                "run_id": spec["run_id"], "status": "ok", "slice_lines": selected,
                "rendered_lines": selected, "slice_code": source,
            })
            append_jsonl(self.work / "detector.jsonl", {
                "run_id": spec["run_id"], "status": "ok", "verdict": cid == "paired",
                "p_vulnerable": .8 if cid == "paired" else .2,
            })
        packets, joins = packet_index(self.cases, self.work)
        self.assessments = self.root / "assessments.jsonl"
        self.adjudications = self.root / "adjudications.jsonl"
        for rid, packet in packets.items():
            adequate = "char buf[4]" in packet["code"] and "memcpy(buf,p,8)" in packet["code"]
            for assessor in ("blind_reader_1", "blind_reader_2"):
                append_jsonl(self.assessments, {
                    "review_id": rid, "assessor_id": assessor,
                    "adequacy": "adequate" if adequate else "inadequate",
                    "cited_lines": [1, 2] if adequate else [],
                    "relationships": ["eight bytes into four"] if adequate else [],
                    "explanation": "bound and sink visible" if adequate else "bound not established",
                })
        for cid, rid in {(s["case_id"], joins[s["run_id"]])
                         for s in run_specs(self.cases)}:
            append_jsonl(self.adjudications, {
                "case_id": cid, "review_id": rid, "match": "yes",
                "reason": "Checked against documented mechanism",
            })

    def test_baseline_includes_missed_and_paired_loss_ignores_verdict(self):
        report = analyze(self.cases, self.work, self.assessments, self.adjudications,
                         bootstrap_draws=100, seed=4)
        self.assertEqual(report["rq1"]["cases"], 2)
        self.assertEqual(report["rq1"]["adequacy"], {"inadequate": 1, "adequate": 1})
        self.assertEqual(report["rq1"]["verdicts_repeat0"]["missed"], 1)
        self.assertEqual(report["rq2"]["n_pairs"], 1)
        self.assertEqual(report["rq2"]["n_eligible_including_uncertain"], 1)
        self.assertIsNone(report["rq2"]["cluster_bootstrap_95_ci"])
        self.assertEqual(report["rq2"]["paired_risk_difference"], 1.0)
        self.assertEqual(report["rq2"]["correct_verdict_despite_TM_evidence_loss"], 1)

    def test_adjudication_uncertainty_excludes_pair(self):
        rows = [json.loads(x) for x in self.adjudications.read_text().splitlines()]
        for row in rows:
            if row["case_id"] == "paired":
                row["match"] = "uncertain"
        self.adjudications.write_text("".join(json.dumps(row) + "\n" for row in rows))
        report = analyze(self.cases, self.work, self.assessments, self.adjudications)
        self.assertEqual(report["rq2"]["n_pairs"], 0)
        self.assertEqual(report["rq1"]["adequacy"]["uncertain"], 1)

    def test_unknown_failure_is_not_silently_query_invalid(self):
        self.assertEqual(_failure_status("Some new error"), "unknown_slice_failure")
        self.assertEqual(_failure_status("Interacters query failed: x"), "context_exec")

    def test_two_reviewers_and_resolution_are_required_for_adequacy(self):
        rows = [json.loads(x) for x in self.assessments.read_text().splitlines()]
        adequate_id = next(r["review_id"] for r in rows if r["adequacy"] == "adequate")
        # A disagreement without independent resolution remains uncertain.
        for row in rows:
            if row["review_id"] == adequate_id and row["assessor_id"] == "blind_reader_2":
                row["adequacy"] = "inadequate"
                row["cited_lines"] = []
                row["relationships"] = []
        self.assessments.write_text("".join(json.dumps(row) + "\n" for row in rows))
        uncertain = analyze(self.cases, self.work, self.assessments, self.adjudications)
        self.assertEqual(uncertain["review"]["initial_disagreement"], 1)
        self.assertEqual(uncertain["rq2"]["n_pairs"], 0)
        resolutions = self.root / "resolutions.jsonl"
        append_jsonl(resolutions, {"review_id": adequate_id, "method": "third_review",
                                   "assessor_id": "third_reader", "adequacy": "adequate",
                                   "cited_lines": [1, 2], "relationships": ["copy exceeds bound"],
                                   "reason": "Both bound and copy are visible"})
        resolved = analyze(self.cases, self.work, self.assessments, self.adjudications,
                           resolutions=resolutions)
        self.assertEqual(resolved["rq2"]["n_pairs"], 1)

    def test_evidence_only_does_not_call_missing_d_an_abstention(self):
        (self.work / "detector.jsonl").unlink()
        report = analyze(self.cases, self.work, self.assessments, self.adjudications,
                         evidence_only=True)
        self.assertEqual(report["rq1"]["verdicts_repeat0"], {"not_run": 2})
        self.assertEqual(report["scope"], "evidence_only")

    def test_uncertain_transformation_stays_in_eligible_denominator_and_bounds(self):
        _, joins = packet_index(self.cases, self.work)
        tm_run = next(spec["run_id"] for spec in run_specs(self.cases)
                      if spec["case_id"] == "paired" and spec["arm"] == "TM")
        tm_packet = joins[tm_run]
        rows = [json.loads(x) for x in self.assessments.read_text().splitlines()]
        for row in rows:
            if row["review_id"] == tm_packet:
                row["adequacy"] = "uncertain"
                row["cited_lines"] = []
                row["relationships"] = []
        self.assessments.write_text("".join(json.dumps(row) + "\n" for row in rows))
        report = analyze(self.cases, self.work, self.assessments, self.adjudications)
        self.assertEqual(report["rq2"]["n_pairs"], 0)
        self.assertEqual(report["rq2"]["n_eligible_including_uncertain"], 1)
        self.assertEqual(report["rq2"]["unresolved_outcome_bounds"]["TM_loss"], [0.0, 1.0])

    def test_manifest_rejects_missing_transformed_mapping(self):
        rows = [json.loads(x) for x in self.manifest.read_text().splitlines()]
        del rows[1]["referent"]["elements"][0]["mapped_lines"]["TM"]
        self.manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(ValueError, "line mappings"):
            load_cases(self.manifest)


if __name__ == "__main__":
    unittest.main()
