"""Fresh Docker/Scala process for every input; no previous case's REPL bindings."""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys

from evidence_experiment.bounded_joern import BoundedJoern
from evidence_experiment.schema import write_json
from llmxcpg.joern.client import JoernClient


def inspected_digest():
    def command(*args):
        return subprocess.run(args, text=True, capture_output=True, check=True,
                              timeout=30).stdout.strip()
    image = command("docker", "inspect", "llmxcpg_joern", "--format", "{{.Image}}")
    raw = command("docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}")
    values = {s.split("@", 1)[1] for s in json.loads(raw)
              if s.startswith("ghcr.io/joernio/joern@sha256:")}
    if len(values) != 1:
        raise ValueError("Cannot establish one inspected Joern digest")
    return values.pop()


@contextlib.contextmanager
def fresh_worker(cfg, work):
    from evidence_experiment.locks import work_lock

    from .setup import ROOT
    with work_lock(ROOT / "work/joern-service-lock"), _fresh_worker(cfg, work) as client:
        yield client


@contextlib.contextmanager
def _fresh_worker(cfg, work):
    from .setup import ROOT
    work.mkdir(parents=True, exist_ok=True)
    config = work / "worker-config.json"
    write_json(config, cfg)
    compose = ["docker", "compose", "-f", str(ROOT / "rq1/compose.yml")]
    try:
        with (work / "worker.log").open("a") as log:
            for args in (compose + ["up", "-d"], compose + ["restart", "joern"]):
                subprocess.run(args, cwd=ROOT, stdout=log, stderr=log, check=True, timeout=180)
            subprocess.run([sys.executable, "-m", "rq1.joern_readiness", "--config", str(config),
                            "--output", str(work / "startup.json")], cwd=ROOT, stdout=log,
                           stderr=log, check=True, timeout=330)
        if inspected_digest() != cfg["joern_digest"]:
            raise ValueError("The running Joern image differs from the configured digest")
        inner = JoernClient(host=cfg["joern_host"], port=cfg["joern_port"],
                            local_input_dir=ROOT / cfg["joern_input_dir"],
                            server_input_dir=cfg["server_input_dir"])
        client = BoundedJoern(inner, cfg["joern_rpc_timeout"], cfg["joern_case_timeout"])
        client.begin_case()
        yield client
    finally:
        # Capture failed startup as well as successful runs. Never replace the primary error.
        try:
            with (work / "server.log").open("w") as log:
                subprocess.run(["docker", "logs", "--timestamps", "llmxcpg_joern"],
                               stdout=log, stderr=subprocess.STDOUT, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
