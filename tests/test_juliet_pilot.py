"""Pilot provenance and line-map checks independent of detector output."""

import json
import re
import unittest
from evidence_experiment.schema import load_cases
from juliet_pilot.prepare import OUTPUT, ROOT, prepare


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
                self.assertNotRegex(source, re.compile(r"CWE\d+|\b(?:bad|good|FLAW|FIX)\b", re.I))
                self.assertIn("void case_entry(void)", source)


if __name__ == "__main__":
    unittest.main()
