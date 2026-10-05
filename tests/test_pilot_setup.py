"""Checks for setup gates that otherwise fail late after a large download."""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from juliet_pilot.real_probe import preflight
from scripts.pilot_setup import _docker_digest, _gpu, pin_joern


class PilotSetupTests(unittest.TestCase):
    def test_pin_rejects_placeholder_and_records_complete_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text('{"joern_digest":"placeholder"}')
            with self.assertRaises(ValueError):
                pin_joern(config, "sha256:1234")
            self.assertEqual(json.loads(config.read_text())["joern_digest"], "placeholder")
            pin_joern(config, "sha256:" + "a" * 64)
            self.assertEqual(json.loads(config.read_text())["joern_digest"], "sha256:" + "a" * 64)

    def test_docker_digest_checks_running_image_id(self):
        digest = "sha256:" + "a" * 64
        response = [types.SimpleNamespace(returncode=0, stdout="sha256:local-id\n"),
                    types.SimpleNamespace(returncode=0, stdout=json.dumps([
                        "ghcr.io/joernio/joern@" + digest]))]
        with patch("scripts.pilot_setup.shutil.which", return_value="/usr/bin/docker"), \
             patch("scripts.pilot_setup._command", side_effect=response) as command:
            ok, _ = _docker_digest({"joern_digest": digest})
            self.assertTrue(ok)
            self.assertEqual(command.call_args_list[1].args[3], "sha256:local-id")
        with patch("scripts.pilot_setup.shutil.which", return_value="/usr/bin/docker"), \
             patch("scripts.pilot_setup._command", side_effect=response):
            ok, _ = _docker_digest({"joern_digest": "sha256:" + "b" * 64})
            self.assertFalse(ok)

    def test_six_gib_gpu_is_rejected_even_if_cuda_and_bf16_report_true(self):
        cuda = types.SimpleNamespace(
            is_available=lambda: True, device_count=lambda: 1,
            get_device_name=lambda _: "small gpu",
            get_device_properties=lambda _: types.SimpleNamespace(total_memory=6 * 2**30),
            is_bf16_supported=lambda: True,
        )
        with patch("scripts.pilot_setup.importlib.util.find_spec", return_value=object()), \
             patch.dict("sys.modules", {"torch": types.SimpleNamespace(cuda=cuda)}):
            ok, detail = _gpu()
        self.assertFalse(ok)
        self.assertIn("<70 GiB", detail)

    def test_real_probe_preflight_catches_laptop_before_loading_q(self):
        cuda = types.SimpleNamespace(
            is_available=lambda: True,
            get_device_properties=lambda _: types.SimpleNamespace(total_memory=6 * 2**30),
            is_bf16_supported=lambda: False,
        )
        with tempfile.TemporaryDirectory() as directory:
            template = Path(__file__).resolve().parents[1] / "juliet_pilot/real_probe.example.json"
            config = json.loads(template.read_text())
            config["joern_digest"] = "sha256:" + "a" * 64
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with patch("juliet_pilot.real_probe.importlib.util.find_spec", return_value=object()), \
                 patch("juliet_pilot.real_probe.shutil.which", return_value="/usr/bin/nvidia-smi"), \
                 patch("juliet_pilot.real_probe.socket.create_connection"), \
                 patch.dict("sys.modules", {"torch": types.SimpleNamespace(cuda=cuda)}):
                blockers = preflight(path)
        self.assertTrue(any("GPU 0 has 6.0 GiB" in item for item in blockers))
        self.assertTrue(any("does not support the BF16" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()
