"""Blind review queue: templated claims, fixed-variant decoys and duplicates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evidence_experiment.analysis import analyze
from evidence_experiment.review import (
    build_queue,
    claim_problem,
    duplicate_packets,
    packet_index,
    packet_lines,
    render_claim,
    write_queue,
)
from evidence_experiment.schema import REQUIRED_CHECKS, append_jsonl, load_cases, run_specs
from evidence_experiment.stats import (
    fleiss_kappa,
    gwet_ac1,
    mcnemar_exact_p,
    newcombe_paired,
    percent_agreement,
    wilson,
)

CLAIM = {"flaw_class": "stack buffer overflow", "operation": "memcpy call"}


class ClaimTemplateTests(unittest.TestCase):
    def test_structured_claim_renders_one_granularity(self):
        self.assertIsNone(claim_problem({"review_claim": CLAIM}))
        self.assertEqual(render_claim({"review_claim": CLAIM}),
                         "Does this excerpt justify a stack buffer overflow at the memcpy call?")
        self.assertIn("an integer overflow", render_claim(
            {"review_claim": {"flaw_class": "integer overflow", "operation": "addition"}}))

    def test_claim_cannot_carry_the_mechanism(self):
        for operation in ("memcpy of 40 bytes", "strcpy without terminator space",
                          "write beyond the guard", "a very long operation description here"):
            self.assertIsNotNone(claim_problem(
                {"review_claim": {"flaw_class": "heap buffer overflow", "operation": operation}}),
                operation)
        self.assertIsNotNone(claim_problem({"review_claim": {"flaw_class": "memory bug",
                                                             "operation": "memcpy call"}}))
        self.assertIsNotNone(claim_problem({"review_claim": "Free text claim"}))


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        sources = {
            "u.c": "char buf[4];\nmemcpy(buf,p,8);\n",
            "tm.c": "char *alias=buf;\nmemcpy(alias,p,8);\n",
            "tn.c": "char buf[4];\nmemcpy(buf,p,8);\n",
            "f.c": "char buf[8];\nmemcpy(buf,p,8);\n",
            "g.c": "char q[4];\nmemcpy(q,p,8);\n",
            "gf.c": "char q[8];\nmemcpy(q,p,8);\n",  # fix site is line 1
        }
        for name, text in sources.items():
            (self.root / name).write_text(text)
        self.manifest = self.root / "cases.jsonl"
        append_jsonl(self.manifest, {
            "case_id": "paired", "cluster_id": "template_a", "cwe": "CWE-121",
            "sources": {"U": "u.c", "TM": "tm.c", "TN": "tn.c", "F": "f.c"},
            "referent": {"review_claim": CLAIM, "elements": [
                {"id": "sink", "role": "sink", "lines": [2], "mapped_lines": {"TM": [2], "TN": [2]}},
                {"id": "bound", "role": "capacity", "lines": [1],
                 "mapped_lines": {"TM": [1], "TN": [1]}}],
                "relations": ["copy exceeds buffer"], "target_lines": [2], "control_lines": [1]},
            "operator": "alias", "validation": {key: "pass" for key in REQUIRED_CHECKS},
        })
        append_jsonl(self.manifest, {
            "case_id": "second", "cluster_id": "template_b", "cwe": "CWE-121",
            "sources": {"U": "g.c", "F": "gf.c"},
            "referent": {"review_claim": CLAIM,
                         "elements": [{"id": "sink", "role": "sink", "lines": [2]}],
                         "relations": ["copy exceeds buffer"]},
        })
        self.cases = load_cases(self.manifest)
        for spec in run_specs(self.cases, repeats=1):
            arm = spec["arm"]
            # The second case's slices omit its fix site, so U and F look the same.
            selected = [2] if spec["case_id"] == "second" or arm.startswith("TM") else [1, 2]
            append_jsonl(self.work / "slices.jsonl", {
                "run_id": spec["run_id"], "status": "ok", "slice_lines": selected,
                "rendered_lines": selected, "slice_code": "x"})

    def _rate(self, rule):
        """Two independent assessors per packet using `rule(code) -> adequacy`."""
        rows = []
        for packet in json.loads("[" + ",".join(
                (self.work / "blind_review_packets.jsonl").read_text().splitlines()) + "]"):
            decision = rule(packet["code"])
            lines = sorted(packet_lines(packet["code"]))
            for assessor in ("r1", "r2"):
                rows.append({"review_id": packet["review_id"], "assessor_id": assessor,
                             "adequacy": decision,
                             "cited_lines": lines if decision == "adequate" else [],
                             "relationships": ["copy exceeds buffer"] if decision == "adequate" else [],
                             "explanation": "visible lines checked"})
        path = self.root / "reviews.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        adjudications = self.root / "matches.jsonl"
        _, joins = packet_index(self.cases, self.work, 1)
        seen = set()
        with adjudications.open("w") as stream:
            for spec in run_specs(self.cases, repeats=1):
                key = (spec["case_id"], joins[spec["run_id"]])
                if spec["arm"] != "F" and key not in seen:
                    seen.add(key)
                    stream.write(json.dumps({"case_id": key[0], "review_id": key[1],
                                             "match": "yes", "reason": "matches"}) + "\n")
        return path, adjudications

    def test_decoys_share_the_claim_and_duplicates_are_disguised(self):
        packets, key = build_queue(self.cases, self.work, 1, duplicate_fraction=0.5, seed=7)
        kinds = {row["kind"] for row in key}
        self.assertEqual(kinds, {"evidence", "decoy", "evidence_and_decoy", "duplicate"})
        self.assertEqual({p["claim"] for p in packets}, {render_claim({"review_claim": CLAIM})})
        duplicate = next(row for row in key if row["kind"] == "duplicate")
        original = next(p for p in packets if p["review_id"] == duplicate["duplicate_of"])
        copy = next(p for p in packets if p["review_id"] == duplicate["review_id"])
        self.assertNotEqual(original["code"], copy["code"])
        self.assertEqual({n + duplicate["line_offset"] for n in packet_lines(original["code"])},
                         packet_lines(copy["code"]))
        self.assertTrue(all(set(p) == {"review_id", "claim", "code"} for p in packets))

    def test_issued_queue_is_frozen_and_duplicates_are_verified(self):
        settings = {"duplicate_fraction": 0.5, "seed": 7, "repeats": 1}
        packets, key = build_queue(self.cases, self.work, 1, duplicate_fraction=0.5, seed=7)
        write_queue(self.work, packets, key, settings)
        write_queue(self.work, packets, key, settings)  # identical regeneration is fine
        other, other_key = build_queue(self.cases, self.work, 1, duplicate_fraction=0.5, seed=8)
        with self.assertRaisesRegex(ValueError, "frozen"):
            write_queue(self.work, other, other_key, {**settings, "seed": 8})
        rebuilt = duplicate_packets(self.cases, self.work, 1)
        self.assertEqual(set(rebuilt), {row["review_id"] for row in key
                                        if row["kind"] == "duplicate"})

    def test_false_adequacy_discriminability_and_retest_are_reported(self):
        packets, key = build_queue(self.cases, self.work, 1, duplicate_fraction=0.5, seed=7)
        write_queue(self.work, packets, key, {"duplicate_fraction": 0.5, "seed": 7, "repeats": 1})
        # Reviewers call anything with a copy "adequate", including the fixed variants.
        reviews, matches = self._rate(lambda code: "adequate" if "memcpy" in code else "inadequate")
        report = analyze(self.cases, self.work, reviews, matches, repeats=1, evidence_only=True)
        decoys = report["review_quality"]["decoys"]
        self.assertEqual(decoys["cases_with_fixed_variant"], 2)
        self.assertEqual(decoys["false_adequacy_rate"], 1.0)
        self.assertEqual(decoys["excerpt_identical_to_vulnerable"], 1)
        self.assertEqual(report["rq1"]["cases"], 2)  # decoys never enter RQ1
        retest = report["review_quality"]["duplicates"]
        self.assertGreaterEqual(retest["duplicates_issued"], 1)
        self.assertEqual(retest["same_assessor_retest"]["percent_agreement"], 1.0)
        self.assertIn("F", report["review_quality"]["agreement"]["by_arm"])


class StatisticsTests(unittest.TestCase):
    def test_paired_interval_and_exact_test(self):
        self.assertEqual(mcnemar_exact_p(8, 1), 20 / 512)
        self.assertEqual(mcnemar_exact_p(0, 0), 1.0)
        low, high = newcombe_paired(2, 8, 1, 19)
        self.assertLess(low, (8 - 1) / 30)
        self.assertGreater(high, (8 - 1) / 30)
        self.assertGreater(low, 0)  # strongly unbalanced discordance excludes zero
        low, high = newcombe_paired(0, 0, 0, 10)
        self.assertLess(low, 0)
        self.assertGreater(high, 0)
        self.assertAlmostEqual(wilson(0, 10)[1], 0.2775, places=4)

    def test_agreement_statistics(self):
        perfect = [["adequate", "adequate"], ["inadequate", "inadequate"]]
        self.assertEqual(fleiss_kappa(perfect), 1.0)
        self.assertEqual(gwet_ac1(perfect), 1.0)
        mixed = [["adequate", "adequate"]] * 8 + [["adequate", "inadequate"]] * 2
        self.assertEqual(percent_agreement(mixed), 0.8)
        # Kappa is depressed when one rating dominates; AC1 much less so.
        self.assertLess(fleiss_kappa(mixed), gwet_ac1(mixed))


if __name__ == "__main__":
    unittest.main()
