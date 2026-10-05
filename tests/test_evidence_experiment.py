"""Tests of the revised estimand and population, independent of GPU/Joern."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evidence_experiment.analysis import analyze
from evidence_experiment.runner import _failure_status, packet_index
from evidence_experiment.schema import (REQUIRED_CHECKS, append_jsonl, load_cases,
                                        run_specs)


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
            append_jsonl(self.assessments, {
                "review_id": rid, "assessor_id": "blind_reader",
                "adequacy": "adequate" if adequate else "inadequate",
                "cited_lines": [1, 2] if adequate else [],
                "relationships": ["eight bytes into four"] if adequate else [],
                "explanation": "bound and sink visible" if adequate else "bound not established",
            })
        for cid, rid in set((s["case_id"], joins[s["run_id"]])
                            for s in run_specs(self.cases)):
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

    def test_manifest_rejects_missing_transformed_mapping(self):
        rows = [json.loads(x) for x in self.manifest.read_text().splitlines()]
        del rows[1]["referent"]["elements"][0]["mapped_lines"]["TM"]
        self.manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(ValueError, "line mappings"):
            load_cases(self.manifest)


if __name__ == "__main__":
    unittest.main()
