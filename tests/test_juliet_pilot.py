"""Pilot provenance and line-map checks independent of detector output."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from evidence_experiment.schema import load_cases
from juliet_pilot.prepare import OUTPUT, ROOT, prepare
from juliet_pilot.real_probe import preflight
from juliet_pilot.smoke import run as smoke_run


class JulietPilotTests(unittest.TestCase):
    def test_label_free_mapped_referent_and_controls(self):
        prepared = prepare()
        cases = load_cases(OUTPUT / "cases.jsonl")
        self.assertEqual(len(cases), 4)
        self.assertEqual(len(prepared), 4)
        self.assertTrue(all(not c.admissible for c in cases))
        source_files = {row["case_id"]: row["source_file"] for row in
                        json.loads((ROOT / "spec.json").read_text())["cases"]}
        for case in prepared:
            upstream = (ROOT / "upstream" / source_files[case["case_id"]]).read_text()
            # Verify that each cited line maps to the intended upstream line.
            for element in case["referent"]["elements"]:
                mapping = json.loads((OUTPUT / case["line_maps"]["U"]).read_text())[
                    "upstream_line_for_generated_line"]
                self.assertEqual([mapping[line - 1] for line in element["lines"]],
                                 element["upstream_lines"])
                self.assertTrue(all(upstream.splitlines()[n - 1].strip()
                                    for n in element["upstream_lines"]))
            for arm in ("U", "control"):
                source = (OUTPUT / case["sources"].get(arm, case["control_source"])).read_text()
                self.assertNotRegex(source, re.compile(r"CWE\d+|\b(?:bad|good|FLAW|FIX)\b", re.IGNORECASE))
                self.assertIn("void case_entry(void)", source)

    def test_four_case_smoke_and_resume_keep_review_uncertain(self):
        prepare()
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            first = smoke_run(work)
            self.assertEqual([first[k] for k in ("query_runs", "slice_runs",
                                                 "detector_runs")], [12, 12, 12])
            self.assertEqual(first["joern_resets"], 12)
            self.assertEqual(first["baseline_adequacy"], {"uncertain": 4})
            analysis = json.loads((work / "analysis.json").read_text())
            self.assertEqual(analysis["rq2"]["n_pairs"], 0)
            self.assertTrue(all(obs["earliest_observed_change"] == "evidence_uncertain"
                                for obs in analysis["rq3"]["observations"]))
            second = smoke_run(work)
            self.assertEqual(second["query_runs"], 12)
            self.assertEqual(second["joern_resets"], 0)
            self.assertEqual(second["resumed_from_detector"], 12)

    def test_real_probe_requires_digest_and_never_accepts_dummy_mode(self):
        config = ROOT / "real_probe.example.json"
        self.assertEqual(preflight(config, check_runtime=False),
                         ["Replace joern_digest with the deployed image's sha256 digest"])
        with tempfile.TemporaryDirectory() as temp:
            changed = json.loads(config.read_text())
            changed["query_engine"] = "dummy"
            changed["allow_dummy"] = True
            changed["joern_digest"] = "sha256:" + "0" * 64
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(changed))
            self.assertIn("Use the local vLLM Q engine without dummy mode",
                          preflight(path, check_runtime=False))


if __name__ == "__main__":
    unittest.main()
