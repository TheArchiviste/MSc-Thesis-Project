"""Acquisition and detector locks: what is frozen, and what may move."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidence_experiment import locks
from evidence_experiment.schema import append_jsonl, load_cases

REPO = Path(__file__).resolve().parents[1]


class LockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "u.c").write_text("int main(void){return 0;}\n")
        self.manifest = self.root / "cases.jsonl"
        append_jsonl(self.manifest, {
            "case_id": "u", "cluster_id": "t", "cwe": "CWE-121", "sources": {"U": "u.c"},
            "referent": {"elements": [{"id": "sink", "role": "sink", "lines": [1]}],
                         "relations": ["documented mechanism"]}})
        self.cases = load_cases(self.manifest)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"query_revision": "q", "joern_digest": "sha256:j",
                                           "threshold": .5, "detector_revision": "d"}))
        self.work = self.root / "work"
        self.work.mkdir()
        self.versions = {"cpgqls-client": "1", "websocket-client": "1", "vllm": "0.6.3",
                         "torch": "2.4.0", "transformers": "4.45.0", "peft": "0.13.0",
                         "bitsandbytes": "0.44.0", "accelerate": "0.34.0", "numpy": "2.0"}
        fake = patch.object(locks, "package_versions",
                            side_effect=lambda names: {n: self.versions.get(n) for n in names})
        fake.start()
        self.addCleanup(fake.stop)
        git = patch.object(locks, "git_provenance", return_value={"q_joern_pin": "matches_pin"})
        git.start()
        self.addCleanup(git.stop)

    def lock(self, phase):
        return locks.lock_inputs(self.work, self.manifest, self.config, self.cases, 1, phase=phase)

    def test_q_joern_packages_are_enforced_only_while_acquiring(self):
        self.lock("query")
        self.versions["peft"] = "0.14.0"  # D-only package: acquisition is unaffected
        self.lock("slice")
        self.versions["torch"] = "2.5.0"
        self.lock("packets")
        self.lock("analyze")
        with self.assertRaisesRegex(ValueError, r"Q/Joern packages changed \(torch 2.4.0 -> 2.5.0\)"):
            self.lock("query")
        phases = [json.loads(line)["phase"]
                  for line in (self.work / "phase_log.jsonl").read_text().splitlines()]
        self.assertEqual(phases, ["query", "slice", "packets", "analyze"])

    def test_detector_lock_owns_the_d_packages(self):
        locks.lock_detector(self.work, self.config)
        self.versions["vllm"] = "0.7.0"
        locks.lock_detector(self.work, self.config)
        self.versions["bitsandbytes"] = "0.45.0"
        with self.assertRaisesRegex(ValueError, "D packages changed"):
            locks.lock_detector(self.work, self.config)

    def test_threshold_and_detector_settings_do_not_touch_acquisition(self):
        self.lock("query")
        cfg = json.loads(self.config.read_text())
        cfg.update(threshold=.61, detector_base_revision="b")
        self.config.write_text(json.dumps(cfg))
        self.lock("query")
        cfg["query_temperature"] = 0.7
        self.config.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, "Inputs or code changed"):
            self.lock("query")

    def test_pinned_q_joern_code_divergence_blocks_acquisition_only(self):
        diverged = {"commit": "x", "modified_tracked_files": [], "q_joern_pin": "differs_from_pin"}
        with patch.object(locks, "git_provenance", return_value=diverged):
            with self.assertRaisesRegex(ValueError, "differs from pinned commit"):
                self.lock("query")
            self.lock("analyze")

    def test_unverifiable_pin_blocks_real_acquisition(self):
        with patch.object(locks, "git_provenance", return_value={"q_joern_pin": "unverifiable"}), \
                self.assertRaisesRegex(ValueError, "full git clone"):
            self.lock("query")

    def test_job_local_transport_changes_do_not_change_acquisition(self):
        self.lock("query")
        cfg = json.loads(self.config.read_text())
        cfg.update(joern_port=45678, joern_input_dir="/another/job")
        self.config.write_text(json.dumps(cfg))
        self.lock("slice")

    def test_locks_from_older_engine_are_refused(self):
        (self.work / "experiment_lock.json").write_text('{"fingerprint": "old"}')
        with self.assertRaisesRegex(ValueError, "older engine"):
            self.lock("analyze")

    def test_fingerprint_does_not_depend_on_checkout_location(self):
        copy = self.root / "relocated"
        shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(
            ".git", "work", "__pycache__", "*.egg-info", ".venv"))
        code = ("import sys; from pathlib import Path; "
                "from evidence_experiment.locks import acquisition_fingerprint; "
                "from evidence_experiment.schema import load_cases; "
                "m, c, w = map(Path, sys.argv[1:4]); "
                "print(acquisition_fingerprint(m, c, load_cases(m), 1, w))")
        args = [str(self.manifest), str(self.config), str(self.work)]
        prints = [subprocess.run([sys.executable, "-c", code, *args], cwd=where, check=True,
                                 capture_output=True, text=True).stdout
                  for where in (REPO, copy)]
        self.assertEqual(prints[0], prints[1])


if __name__ == "__main__":
    unittest.main()
