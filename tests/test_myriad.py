"""Cluster contracts and launch guards without contacting UCL or downloading weights."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evidence_experiment.runner import _models
from scripts.myriad.manage import doctor, render, sha256

REPO = Path(__file__).resolve().parents[1]


class MyriadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_context_and_memory_settings_reach_model_runtime(self):
        model = _models({"query_max_context": 4096, "query_gpu_memory_utilization": .92,
                         "query_tensor_parallel_size": 2, "detector_max_context": 8192,
                         "detector_dtype": "float16"})
        self.assertEqual(model.query_max_context, 4096)
        self.assertEqual(model.query_gpu_memory_utilization, .92)
        self.assertEqual(model.query_tensor_parallel_size, 2)
        self.assertEqual((model.detector_max_context, model.detector_dtype), (8192, "float16"))

    def test_render_uses_calibrated_threshold_without_mutating_frozen_config(self):
        cfg = {"joern_port": 8080, "threshold": .5, "query_revision": "q"}
        original = dict(cfg)
        output = self.root / "rendered.json"
        render(cfg, output, 45678, probe=True)
        result = json.loads(output.read_text())
        self.assertEqual(result["joern_port"], 45678)
        self.assertTrue(result["exploratory_probe_only"])
        self.assertNotIn("threshold", result)
        calibration = self.root / "calibration.json"
        calibration.write_text('{"threshold": 0.61}')
        render(cfg, output, 45679, calibration=calibration)
        result = json.loads(output.read_text())
        self.assertEqual(result["threshold"], .61)
        self.assertNotIn("exploratory_probe_only", result)
        self.assertEqual(cfg, original)

    def test_doctor_rejects_unverified_pipeline_pin(self):
        with patch("evidence_experiment.locks.git_provenance",
                   return_value={"q_joern_pin": "unverifiable"}), \
                self.assertRaisesRegex(RuntimeError, "full clone"):
            doctor({}, gpu=False)

    def test_doctor_refuses_multiple_visible_gpus(self):
        modules = {name: SimpleNamespace() for name in
                   ("vllm", "bitsandbytes", "peft", "transformers")}
        modules["torch"] = SimpleNamespace(cuda=SimpleNamespace(
            is_available=lambda: True, device_count=lambda: 4))
        with patch("evidence_experiment.locks.git_provenance",
                   return_value={"q_joern_pin": "matches_pin"}), \
                patch.dict("sys.modules", modules), \
                self.assertRaisesRegex(RuntimeError, "scheduler-assigned"):
            doctor({}, gpu=True)

    def test_launch_requires_scheduler_and_gpu_mask(self):
        script = str(REPO / "scripts" / "myriad" / "run.sh")
        env = {k: v for k, v in os.environ.items() if k not in ("JOB_ID", "CUDA_VISIBLE_DEVICES")}
        result = subprocess.run(["bash", script, "query"], env=env, capture_output=True,
                                text=True, cwd=self.root, timeout=5, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Use qsub", result.stderr)
        (self.root / "work" / "myriad").mkdir(parents=True)
        (self.root / "work" / "myriad" / "env.sh").write_text(
            f'MYRIAD_ROOT="{self.root}"\nMYRIAD_HF_CACHE="{self.root}"\n')
        (self.root / "bin").mkdir()
        module = self.root / "bin" / "module"
        module.write_text("#!/bin/bash\nexit 0\n")
        module.chmod(0o755)
        env.update(JOB_ID="123", TMPDIR=str(self.root), PATH=f"{self.root / 'bin'}:{env['PATH']}")
        result = subprocess.run(["bash", script, "query"], env=env, capture_output=True,
                                text=True, cwd=self.root, timeout=5, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Scheduler GPU mask missing", result.stderr)

    def test_failed_stage_cleans_up_server_and_has_no_success_marker(self):
        # Exercise the real shell lifecycle with a fake container boundary.
        # A slice failure must still kill Joern and retain a nonzero exit code.
        local = self.root / "work" / "myriad"
        local.mkdir(parents=True)
        images = self.root / "images"
        images.mkdir()
        runtime, joern = images / "runtime.sif", images / "joern.sif"
        runtime.write_bytes(b"fake runtime")
        joern.write_bytes(b"fake joern")
        (images / "SHA256SUMS").write_text(
            f"{sha256(runtime)}  {runtime}\n{sha256(joern)}  {joern}\n")
        config = self.root / "config.json"
        config.write_text(json.dumps({"runtime_image_sha256": sha256(runtime),
                                      "joern_digest": "sha256:test"}))
        (images / "provenance.json").write_text(json.dumps({
            "runtime_sha256": sha256(runtime), "joern_digest": "sha256:test"}))
        experiment = self.root / "results"
        settings = {"MYRIAD_ROOT": self.root, "MYRIAD_HF_CACHE": self.root,
                    "RUNTIME_SIF": runtime, "JOERN_SIF": joern,
                    "MYRIAD_CONFIG": config, "EXPERIMENT_WORK": experiment,
                    "PROBE_WORK": experiment, "CALIBRATION_WORK": experiment,
                    "ANALYSIS_MANIFEST": self.root / "cases.jsonl"}
        (local / "env.sh").write_text("".join(f'{k}="{v}"\n' for k, v in settings.items()))
        bindir = self.root / "bin"
        bindir.mkdir()
        (bindir / "module").write_text("#!/bin/bash\nexit 0\n")
        (bindir / "module").chmod(0o755)
        stub = bindir / "apptainer"
        stub.write_text("""#!/usr/bin/env python3
import os,signal,subprocess,sys,time
from pathlib import Path
args=sys.argv[1:]
if 'joern' in args:
    Path(os.environ['STUB_PID']).write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True: time.sleep(.01)
if 'wait-joern' in args or 'doctor' in args: sys.exit(0)
if '-m' in args: sys.exit(7)
i=args.index('python')
args=[a.replace('/repo',os.environ['STUB_REPO']) for a in args[i+1:]]
sys.exit(subprocess.call([sys.executable,*args],env={**os.environ,'PYTHONPATH':os.environ['STUB_REPO']}))
""")
        stub.chmod(0o755)
        pidfile = self.root / "server.pid"
        env = {**os.environ, "JOB_ID": "123", "TMPDIR": str(self.root),
               "STUB_PID": str(pidfile), "STUB_REPO": str(REPO),
               "PATH": f"{bindir}:{os.environ['PATH']}"}
        result = subprocess.run(["bash", str(REPO / "scripts/myriad/run.sh"), "slice"],
                                env=env, cwd=self.root, capture_output=True, text=True, timeout=10,
                                check=False)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual((experiment / "jobs/123/exit_code").read_text().strip(), "7")
        self.assertFalse((experiment / "slice.completed").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)


if __name__ == "__main__":
    unittest.main()
