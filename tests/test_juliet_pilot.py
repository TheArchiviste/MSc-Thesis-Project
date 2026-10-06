"""Pilot provenance and line-map checks independent of detector output."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from evidence_experiment.schema import load_cases
from juliet_pilot.prepare import OUTPUT, ROOT, prepare
from juliet_pilot.real_probe import preflight, probe_readouts
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

    def test_probe_readouts_distinguish_guard_loss_and_fixed_control(self):
        prepare()
        case = next(c for c in load_cases(OUTPUT / "cases.jsonl")
                    if c.case_id == "J121-index-01")
        from dataclasses import replace

        from evidence_experiment.schema import run_specs

        control = (OUTPUT / f"{case.case_id}_control.c").read_text()
        case = replace(case, sources={**case.sources, "F": control},
                       source_paths={**case.source_paths, "F": f"{case.case_id}_control.c"})
        original_lines = {e["role"]: e["lines"] for e in case.referent["elements"]}
        # A data-flow slice that keeps the extent and write but drops the guard.
        selected = original_lines["array_extent"] + original_lines["out_of_bounds_write"]
        rows = {spec["run_id"]: {"status": "ok", "slice_lines": selected,
                                 "slice_code": "same rendered excerpt"}
                for spec in run_specs([case])}
        readout = probe_readouts([case], rows)[0]
        self.assertFalse(next(e["selected"] for e in readout["element_roles"]
                              if e["role"] == "insufficient_guard"))
        # The only differences are the guard (21) and an error string (31).
        self.assertEqual(readout["fix_site_lines_U"], [21, 31])
        self.assertFalse(readout["fix_site_selected_in_U"])
        self.assertFalse(readout["fix_site_selected_in_fixed"])
        self.assertTrue(readout["fixed_excerpt_text_identical"])

    def test_probe_with_fixed_controls_runs_decoys_through_the_same_stages(self):
        from unittest.mock import patch

        from evidence_experiment.schema import append_jsonl, run_specs
        from juliet_pilot import real_probe

        prepare()

        def fake_queries(cases, work, cfg, repeats):
            for spec in run_specs(cases, repeats):
                append_jsonl(work / "queries.jsonl", {"run_id": spec["run_id"], "status": "ok",
                                                      "queries": ["q"]})

        def fake_slices(cases, work, cfg, repeats):
            by_case = {c.case_id: c for c in cases}
            for spec in run_specs(cases, repeats):
                source = by_case[spec["case_id"]].source_for(spec["arm"])
                lines = list(range(1, len(source.splitlines()) + 1))
                append_jsonl(work / "slices.jsonl", {
                    "run_id": spec["run_id"], "status": "ok", "slice_lines": lines,
                    "rendered_lines": lines, "slice_code": source})

        with tempfile.TemporaryDirectory() as temp, \
                patch.object(real_probe, "preflight", return_value=[]), \
                patch.object(real_probe, "generate_queries", side_effect=fake_queries), \
                patch.object(real_probe, "extract_slices", side_effect=fake_slices):
            work = Path(temp)
            report = real_probe.probe(ROOT / "real_probe.example.json", work,
                                      include_fixed_controls=True)
            self.assertEqual(report["query_status"], {"ok": 16})
            self.assertEqual(report["fixed_variant_decoys"], 4)
            key = [json.loads(x) for x in (work / "review_key.jsonl").read_text().splitlines()]
            self.assertEqual(sorted(row["kind"] for row in key), ["decoy"] * 4 + ["evidence"] * 4)
            readouts = json.loads((work / "probe_readouts.json").read_text())
            self.assertTrue(all(row["fix_site_selected_in_U"] for row in readouts))
            self.assertTrue(all(row["fixed_excerpt_text_identical"] is False for row in readouts))

    def test_pilot_claims_and_clusters_use_fixed_templates(self):
        from evidence_experiment.review import claim_problem, render_claim

        prepare()
        cases = load_cases(OUTPUT / "cases.jsonl")
        self.assertEqual({c.cluster_id for c in cases},
                         {"CWE121-CWE131-copy", "CWE121-CWE129",
                          "CWE122-c-CWE193-copy", "CWE416-malloc-free"})
        for case in cases:
            self.assertIsNone(claim_problem(case.referent))
            self.assertTrue(render_claim(case.referent).startswith("Does this excerpt justify"))

    def test_template_clusters_merge_sources_types_and_flow_variants(self):
        from juliet_pilot.templates import census, template_cluster

        base = "testcases/CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__"
        self.assertEqual(template_cluster(base + "CWE129_fgets_01.c"),
                         template_cluster(base + "CWE129_rand_44.c"))
        self.assertEqual(template_cluster(base + "CWE805_char_alloca_memcpy_01.c"),
                         template_cluster(base + "CWE805_int_declare_memmove_63a.c"))
        self.assertNotEqual(template_cluster(base + "CWE805_char_alloca_memcpy_01.c"),
                            template_cluster(base + "CWE805_char_alloca_loop_01.c"))
        result = census([base + "CWE129_fgets_01.c", base + "CWE129_fgets_41.c",
                         base + "CWE129_rand_63a.c", base + "CWE129_rand_63b.c"])
        row = result["by_cwe"]["CWE121"]
        self.assertEqual(row["templates"], 1)
        self.assertEqual(row["templates_with_single_file_cross_function_variants"], 1)
        self.assertEqual(row["templates_with_multi_file_variants"], 1)


if __name__ == "__main__":
    unittest.main()
