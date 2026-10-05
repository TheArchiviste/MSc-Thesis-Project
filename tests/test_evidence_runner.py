"""Interface test against the actual llmxcpg modules, without Joern/GPU."""

import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace

from llmxcpg.inference.query_generator import QueryGenerationOutput
from llmxcpg.joern.client import JoernError, QueryResult

from evidence_experiment.runner import (classify_slices, extract_one, extract_slices,
                                        generate_queries)
from evidence_experiment.calibrate import calibrate
from evidence_experiment.schema import REQUIRED_CHECKS, load_cases, read_jsonl


SOURCE = "void f0()\n{\n char buf[10];\n char *data = buf;\n memcpy(data, src, 100);\n}\n"
QUERIES = [
    'val source = cpg.identifier.name("buf").l',
    'val sink = cpg.call.name("memcpy").l',
    'val execution_path = sink.reachableByFlows(source).l',
]


class FakeJoern:
    def __init__(self, mode="ok"):
        self.mode = mode
        self.resets = 0

    def import_code(self, source, project_name="snippet"):
        if self.mode == "import_fail":
            raise JoernError("Failed to import code: parser rejected source")

    def run(self, query):
        if self.mode == "exec_fail" and query == QUERIES[0]:
            return QueryResult("error: not found: value buf", None, False)
        if "slice_lines" in query:
            return QueryResult("val9: List[Int] = List(4, 5)", "List(4, 5)", True)
        return QueryResult("val1: List[X] = List()", "List()", True)

    def reset(self):
        self.resets += 1


class ExtractorInterfaceTests(unittest.TestCase):
    def test_calibration_rejects_cluster_leak_and_screens_detector(self):
        rows = [
            {"sample_id": "b", "cluster_id": "bad_cluster", "split": "calibration",
             "label": 1, "p_vulnerable": .9},
            {"sample_id": "g", "cluster_id": "good_cluster", "split": "calibration",
             "label": 0, "p_vulnerable": .1},
            {"sample_id": "h", "cluster_id": "heldout", "split": "specificity",
             "label": 0, "p_vulnerable": .2},
        ]
        self.assertTrue(calibrate(rows, {"analysis_cluster"})["usability_gate_pass"])
        with self.assertRaisesRegex(ValueError, "overlaps analysis"):
            calibrate(rows, {"bad_cluster"})

    def test_full_trace_rendering_and_cleanup(self):
        fake = FakeJoern()
        out = extract_one(fake, SOURCE, QUERIES, "test")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["slice_lines"], [4, 5])
        self.assertEqual(out["rendered_lines"], [1, 4, 5, 6])
        self.assertEqual(len(out["trace"]), 1 + len(QUERIES) + 3)
        self.assertEqual(fake.resets, 1)

    def test_query_execution_failure_is_recorded(self):
        fake = FakeJoern("exec_fail")
        out = extract_one(fake, SOURCE, QUERIES, "test")
        self.assertEqual(out["status"], "query_exec")
        self.assertFalse(out["trace"][-1]["success"])
        self.assertEqual(fake.resets, 1)

    def test_graph_import_failure_is_recorded(self):
        fake = FakeJoern("import_fail")
        out = extract_one(fake, SOURCE, QUERIES, "test")
        self.assertEqual(out["status"], "joern_import")
        self.assertEqual(out["trace"][0]["stage"], "graph_import")
        self.assertEqual(fake.resets, 1)

    def test_resumable_three_phase_grid_uses_real_extractor_contract(self):
        class FakeQ:
            def generate_batch(self, sources):
                return [QueryGenerationOutput(QUERIES, "fake generated JSON", True)
                        for _ in sources]

        class FakeD:
            def classify(self, code, threshold):
                return SimpleNamespace(is_vulnerable=True, probability_vulnerable=.9,
                                       probability_safe=.1, raw_logits=(2.2, -2.2))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("u.c", "tm.c", "tn.c"):
                (root / name).write_text(SOURCE)
            manifest = root / "cases.jsonl"
            manifest.write_text(json.dumps({
                "case_id": "c", "cluster_id": "functional_variant", "cwe": "CWE-121",
                "sources": {"U": "u.c", "TM": "tm.c", "TN": "tn.c"},
                "referent": {"elements": [{"id": "sink", "role": "sink", "lines": [5],
                                            "mapped_lines": {"TM": [5], "TN": [5]}}],
                             "relations": ["out of bounds copy"],
                             "target_lines": [5], "control_lines": [4]},
                "validation": {key: "pass" for key in REQUIRED_CHECKS},
            }) + "\n")
            cases = load_cases(manifest)
            cfg = {"threshold": .5}
            joern = FakeJoern()
            generate_queries(cases, root, cfg, generator=FakeQ())
            generate_queries(cases, root, cfg, generator=FakeQ())  # idempotent
            self.assertEqual(len(read_jsonl(root / "queries.jsonl")), 9)
            extract_slices(cases, root, cfg, joern=joern)
            extract_slices(cases, root, cfg, joern=joern)
            self.assertEqual(len(read_jsonl(root / "slices.jsonl")), 11)
            self.assertEqual(joern.resets, 11)
            classify_slices(cases, root, cfg, classifier=FakeD())
            classify_slices(cases, root, cfg, classifier=FakeD())
            self.assertEqual(len(read_jsonl(root / "detector.jsonl")), 11)


if __name__ == "__main__":
    unittest.main()
