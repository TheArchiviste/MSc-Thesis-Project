"""Protocol gates: phase locks, finite witnesses, rules and score provenance."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidence_experiment.__main__ import _lock_detector, _lock_inputs, _require_witnesses
from evidence_experiment.calibration_runner import score_and_calibrate
from evidence_experiment.schema import append_jsonl, load_cases, run_specs
from evidence_experiment.validate import validate_witnesses


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "analysis.jsonl"
        (self.root / "u.c").write_text("int main(void){return 0;}\n")
        append_jsonl(self.manifest, {
            "case_id": "u", "cluster_id": "template-analysis", "cwe": "CWE-121",
            "sources": {"U": "u.c"}, "referent": {
                "elements": [{"id": "sink", "role": "sink", "lines": [1]}],
                "relations": ["documented mechanism"]},
        })
        self.cases = load_cases(self.manifest)
        self.work = self.root / "work"
        self.work.mkdir()
        self.config = self.root / "config.json"
        self.cfg = {"query_revision": "q-pin", "detector_revision": "d-pin",
                    "detector_base_revision": "base-pin", "detector_base_model": "base",
                    "joern_digest": "sha256:pin", "threshold": .5}
        self.config.write_text(json.dumps(self.cfg))

    def test_acquisition_can_precede_calibration_but_d_lock_cannot_change(self):
        _lock_inputs(self.work, self.manifest, self.config, self.cases)
        (self.work / "calibration.json").write_text('{"threshold":0.6}')
        self.cfg["threshold"] = .6
        self.config.write_text(json.dumps(self.cfg))
        _lock_inputs(self.work, self.manifest, self.config, self.cases)
        _lock_detector(self.work, self.config)
        (self.work / "calibration.json").write_text('{"threshold":0.7}')
        with self.assertRaisesRegex(ValueError, "D settings or calibration changed"):
            _lock_detector(self.work, self.config)

    def test_arm_specific_rules_and_original_probe(self):
        for name in ("tm.c", "tn.c"):
            (self.root / name).write_text("int main(void){return 0;}\n")
        record = json.loads(self.manifest.read_text())
        record["sources"].update(TM="tm.c", TN="tn.c")
        record["referent"]["elements"][0]["mapped_lines"] = {"TM": [1], "TN": [1]}
        record["validation"] = {key: "pass" for key in (
            "compile", "benign_behavior", "trigger", "mechanism_preserved",
            "line_map", "match", "control_purity")}
        record["rule_queries"] = {arm: [f"val {arm} = cpg.all.reachableByFlows(cpg.all)"]
                                  for arm in ("U", "TM", "TN")}
        self.manifest.write_text(json.dumps(record) + "\n")
        arms = [spec["arm"] for spec in run_specs(load_cases(self.manifest))]
        self.assertEqual({arm for arm in arms if arm.endswith("_rule")},
                         {"U_rule", "TM_rule", "TN_rule"})

    def test_no_benign_input_requires_reason_and_retains_trigger(self):
        for name in ("tm.c", "tn.c"):
            (self.root / name).write_text((self.root / "u.c").read_text())
        record = json.loads(self.manifest.read_text())
        record["sources"].update(TM="tm.c", TN="tn.c")
        record["referent"]["elements"][0]["mapped_lines"] = {"TM": [1], "TN": [1]}
        record["validation"] = {key: "pass" for key in (
            "compile", "trigger", "mechanism_preserved", "line_map", "match", "control_purity")}
        record["validation"]["benign_behavior"] = "not_applicable"
        record["benign_reason"] = "Every entry reaches the flaw; no benign route"
        self.manifest.write_text(json.dumps(record) + "\n")
        plan = self.root / "witness.jsonl"
        append_jsonl(plan, {"case_id": "u", "build_argv": ["cc", "{source}", "-o", "{binary}"],
                            "benign_inputs": [], "benign_reason": record["benign_reason"],
                            "trigger_input": "", "asan_class": "heap-use-after-free"})
        fake = {"compile": "pass", "build": {"exit_code": 0}, "benign": [],
                "trigger": {"status": "ok", "exit_code": 1,
                            "stderr": "==123==ERROR: AddressSanitizer: heap-use-after-free"}}
        with patch("evidence_experiment.validate._build_and_run", return_value=fake):
            rows = validate_witnesses(load_cases(self.manifest), self.manifest, plan,
                                      self.work / "witness_validation.jsonl")
        self.assertEqual(rows[0]["checks"], {
            "compile": "pass", "trigger": "pass", "benign_behavior": "not_applicable"})
        _require_witnesses(self.work, load_cases(self.manifest))

    def test_calibration_scores_are_traced_and_cluster_disjoint(self):
        manifest = self.root / "calibration.jsonl"
        for sid, split, label in (("v", "calibration", 1),
                                  ("s", "calibration", 0),
                                  ("held", "specificity", 0)):
            append_jsonl(manifest, {"sample_id": sid, "cluster_id": sid,
                                    "split": split, "label": label, "source": "u.c"})

        def write_q(cases, work, cfg, repeats):
            for spec in run_specs(cases, repeats):
                append_jsonl(work / "queries.jsonl", {"run_id": spec["run_id"], "status": "ok"})

        def write_slice(cases, work, cfg, repeats):
            for spec in run_specs(cases, repeats):
                append_jsonl(work / "slices.jsonl", {"run_id": spec["run_id"], "status": "ok"})

        def write_d(cases, work, cfg, repeats):
            for spec in run_specs(cases, repeats):
                append_jsonl(work / "detector.jsonl", {"run_id": spec["run_id"],
                                                         "status": "ok",
                                                         "p_vulnerable": .9 if spec["case_id"] == "v" else .1})

        with patch("evidence_experiment.calibration_runner.generate_queries", side_effect=write_q), \
             patch("evidence_experiment.calibration_runner.extract_slices", side_effect=write_slice), \
             patch("evidence_experiment.calibration_runner.classify_slices", side_effect=write_d):
            result = score_and_calibrate(self.cases, manifest, self.work, self.cfg)
        self.assertTrue(result["usability_gate_pass"])
        self.assertEqual(len((self.work / "calibration_scores.jsonl").read_text().splitlines()), 3)
        first = json.loads((self.work / "calibration_scores.jsonl").read_text().splitlines()[0])
        self.assertIn("run_id", first)
        self.assertIn("source_sha256", first)


if __name__ == "__main__":
    unittest.main()
