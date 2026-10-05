"""Prepare and check the four-case pilot without downloading model weights.

Run from the repository root: python scripts/pilot_setup.py init|doctor ...
The doctor has separate local (CPU/Joern) and GPU profiles so a laptop cannot
accidentally be treated as a valid host for the released 33B query model.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def initialize(config: Path) -> None:
    from juliet_pilot.prepare import prepare

    os.chdir(ROOT)
    prepare()
    (ROOT / "work/joern-inputs").mkdir(parents=True, exist_ok=True)
    if config.exists():
        raise FileExistsError(f"{config} exists; edit it rather than overwriting it")
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "juliet_pilot/real_probe.example.json", config)


def pin_joern(config: Path, digest: str) -> None:
    from juliet_pilot.real_probe import SHA256_DIGEST

    if not SHA256_DIGEST.fullmatch(digest):
        raise ValueError("Expected a complete sha256:<64 hex digits> OCI image digest")
    data = json.loads(config.read_text(encoding="utf-8"))
    data["joern_digest"] = digest
    config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=15)


def _docker_digest(config: dict) -> tuple[bool, str]:
    """Confirm that the running container is the image named in the config."""
    if not shutil.which("docker"):
        return False, "Docker CLI unavailable; verify the Apptainer image digest separately"
    try:
        container = _command("docker", "inspect", "llmxcpg_joern", "--format", "{{.Image}}")
        if container.returncode:
            return False, "Joern container is not running under the expected name"
        image_id = container.stdout.strip()
        image = _command("docker", "image", "inspect", image_id, "--format", "{{json .RepoDigests}}")
        if image.returncode:
            return False, "Cannot inspect Joern container image digest"
        digests = json.loads(image.stdout)
        expected = config.get("joern_digest", "")
        if not any(d.startswith("ghcr.io/joernio/joern@") and d.endswith("@" + expected)
                   for d in digests):
            return False, f"Running Joern image does not match configured {expected}"
        return True, "Running Joern image matches the recorded digest"
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return False, f"Could not inspect Joern image: {exc}"


def _joern_import(config: dict) -> tuple[bool, str]:
    """Test server protocol AND the staged-source bind mount."""
    if importlib.util.find_spec("cpgqls_client") is None:
        return False, "Install the project first: python -m pip install -e ."
    from llmxcpg.joern.client import JoernClient

    try:
        with JoernClient(
            host=config.get("joern_host", "127.0.0.1"),
            port=int(config.get("joern_port", 8080)),
            local_input_dir=ROOT / config.get("joern_input_dir", "work/joern-inputs"),
            server_input_dir=config.get("server_input_dir", "/analysis/inputs"),
        ) as joern:
            joern.import_code("int main(void) { return 0; }", project_name="pilot_preflight")
            result = joern.run('cpg.method.name("main").size')
            if not result.success or not re.search(r"=\s*1\s*$", result.stdout.strip()):
                return False, f"Joern imported source but the CPG check failed: {result.stdout[:250]}"
        return True, "Joern imported staged C source and found main"
    except Exception as exc:  # server and client errors differ between Joern versions
        return False, f"Joern import/query failed: {exc}"


def _gpu() -> tuple[bool, str]:
    if importlib.util.find_spec("torch") is None:
        return False, "Install the inference dependencies first"
    import torch

    if not torch.cuda.is_available():
        return False, "PyTorch cannot see a CUDA GPU"
    devices = [(torch.cuda.get_device_name(i),
                torch.cuda.get_device_properties(i).total_memory / 2**30)
               for i in range(torch.cuda.device_count())]
    details = ", ".join(f"{name}: {size:.1f} GiB" for name, size in devices)
    if not torch.cuda.is_bf16_supported():
        return False, f"BF16 is unavailable on the selected GPU ({details})"
    # The released Q checkpoint is 65.5 GB before runtime/KV memory. This
    # probe uses tensor_parallel_size=1, so VRAM on separate cards does not add.
    if devices[0][1] < 70:
        return False, f"Selected GPU 0 has <70 GiB for released Q plus runtime ({details})"
    return True, f"CUDA/BF16 visible ({details}); a real load is still required"


def doctor(profile: str, config_path: Path, *, apptainer: bool = False) -> dict:
    from juliet_pilot.real_probe import preflight

    os.chdir(ROOT)
    checks: dict[str, dict[str, object]] = {}

    def add(name: str, ok: bool, detail: str, *, required: bool = True) -> None:
        checks[name] = {"ok": ok, "required": required, "detail": detail}

    from juliet_pilot.prepare import prepare
    prepare()
    add("cases", (ROOT / "juliet_pilot/generated/cases.jsonl").exists(),
        "Four-case manifest generated")
    if profile == "local":
        add("docker", bool(shutil.which("docker")),
            "Docker/Compose required for the laptop Joern service")
    else:
        for package in ("torch", "transformers", "vllm"):
            add(package, importlib.util.find_spec(package) is not None,
                f"{package} installed in this Python environment")
        if checks["torch"]["ok"]:
            add("gpu", *_gpu())
        else:
            add("gpu", False, "Install inference dependencies before GPU check")
        cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
        existing = next((p for p in (cache, *cache.parents) if p.exists()), None)
        free_gib = shutil.disk_usage(existing).free / 2**30 if existing else 0
        add("disk", free_gib >= 100,
            f"{free_gib:.1f} GiB free for HF_HOME={cache}; reserve >=100 GiB")
    if not config_path.exists():
        add("config", False, f"Missing {config_path}; run init first")
    else:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        blockers = preflight(config_path, check_runtime=False)
        # The local path does not require Q/D inference, but still checks
        # that a real probe config carries the correct model/provenance pins.
        add("config", not blockers, "; ".join(blockers) if blockers else "Pilot pins valid")
        add("joern", *_joern_import(cfg))
        if not apptainer:
            add("joern_image", *_docker_digest(cfg))
        else:
            add("joern_image", False,
                "Confirm the Apptainer OCI source uses the configured digest", required=False)
    return {"profile": profile, "ready": all(x["ok"] for x in checks.values() if x["required"]),
            "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="prepare cases and create a local probe config")
    init.add_argument("--config", type=Path, default=Path("work/real_probe.json"))
    pin = sub.add_parser("pin-joern", help="record the exact OCI image digest in the config")
    pin.add_argument("--config", type=Path, default=Path("work/real_probe.json"))
    pin.add_argument("--digest", required=True)
    check = sub.add_parser("doctor", help="check service, mount, provenance and hardware")
    check.add_argument("--profile", required=True, choices=("local", "gpu"))
    check.add_argument("--config", type=Path, default=Path("work/real_probe.json"))
    check.add_argument("--apptainer", action="store_true", help="external digest verification")
    args = parser.parse_args()
    if args.command == "init":
        initialize(ROOT / args.config)
        print(f"Created {args.config}; set joern_digest before doctor")
        return 0
    if args.command == "pin-joern":
        pin_joern(ROOT / args.config, args.digest)
        print(f"Recorded {args.digest} in {args.config}")
        return 0
    report = doctor(args.profile, ROOT / args.config, apptainer=args.apptainer)
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
