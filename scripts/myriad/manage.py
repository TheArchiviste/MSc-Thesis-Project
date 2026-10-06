"""Small cluster helpers; inference runs inside the prepared Python 3.11 SIF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_joern() -> str:
    # Resolve the public tag once, then pull only the immutable manifest digest.
    url = "https://ghcr.io/token?service=ghcr.io&scope=repository:joernio/joern:pull"
    with urllib.request.urlopen(url, timeout=30) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        "https://ghcr.io/v2/joernio/joern/manifests/v4.0.0", headers={
            "Authorization": f"Bearer {token}",
            "Accept": ("application/vnd.oci.image.index.v1+json, "
                       "application/vnd.docker.distribution.manifest.list.v2+json, "
                       "application/vnd.oci.image.manifest.v1+json, "
                       "application/vnd.docker.distribution.manifest.v2+json")})
    with urllib.request.urlopen(request, timeout=30) as response:
        digest = response.headers.get("Docker-Content-Digest", "")
        body = response.read()
    if not DIGEST.fullmatch(digest) or digest != "sha256:" + hashlib.sha256(body).hexdigest():
        raise ValueError("Registry manifest digest could not be verified")
    return digest


def configure(path: Path, runtime: Path, joern_digest: str, base_revision: str = "",
              q_context: int = 4096, q_memory: float = .92) -> dict:
    from huggingface_hub import HfApi, hf_hub_download

    from evidence_experiment.runner import PINNED_PIPELINE_COMMIT
    from juliet_pilot.real_probe import D_REVISION, Q_REVISION

    if path.exists():
        raise ValueError("Config already exists; keep it frozen or choose a new run/config path")
    if not DIGEST.fullmatch(joern_digest) or q_context < 4096 or not 0 < q_memory < 1:
        raise ValueError("Supply a SHA256 Joern digest, Q context >=4096 and memory fraction in (0,1)")
    adapter_file = hf_hub_download("QCRI/LLMxCPG-D", "adapter_config.json", revision=D_REVISION)
    base_model = json.loads(Path(adapter_file).read_text())["base_model_name_or_path"]
    revision = base_revision or HfApi().model_info(base_model).sha
    if not SHA.fullmatch(revision):
        raise ValueError("D base revision must resolve to an immutable Hugging Face commit")
    cfg = {"pipeline_commit": PINNED_PIPELINE_COMMIT,
           "query_model": "QCRI/LLMxCPG-Q", "query_revision": Q_REVISION,
           "query_engine": "vllm", "query_temperature": 0.0,
           "query_max_context": q_context, "query_gpu_memory_utilization": q_memory,
           "query_tensor_parallel_size": 1,
           "detector_model": "QCRI/LLMxCPG-D", "detector_revision": D_REVISION,
           "detector_base_model": base_model, "detector_base_revision": revision,
           "detector_dtype": "bfloat16", "detector_max_context": 16384,
           "detector_calibration_abstentions": "fail", "joern_digest": joern_digest,
           "joern_host": "127.0.0.1", "joern_port": 8080,
           "joern_input_dir": "/analysis/inputs", "server_input_dir": "/analysis/inputs",
           "runtime_image_sha256": sha256(runtime)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    return cfg


def prefetch(cfg: dict, cache: Path) -> None:
    from huggingface_hub import snapshot_download

    cache.mkdir(parents=True, exist_ok=True)
    for model, revision in ((cfg["query_model"], cfg["query_revision"]),
                            (cfg["detector_model"], cfg["detector_revision"]),
                            (cfg["detector_base_model"], cfg["detector_base_revision"])):
        snapshot_download(repo_id=model, revision=revision, cache_dir=str(cache / "hub"))


def render(cfg: dict, destination: Path, port: int, *, probe: bool = False,
           calibration: Path | None = None) -> None:
    cfg = {**cfg, "joern_port": port}
    cfg.pop("threshold", None)
    cfg.pop("exploratory_probe_only", None)
    if probe:
        cfg["exploratory_probe_only"] = True
    if calibration is not None:
        cfg["threshold"] = json.loads(calibration.read_text())["threshold"]
    destination.write_text(json.dumps(cfg, indent=2) + "\n")


def wait_joern(port: int, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError("Joern did not start; inspect the retained joern.log")


def doctor(cfg: dict, *, gpu: bool, joern: bool = True) -> dict:
    from evidence_experiment.locks import ALL_PACKAGES, git_provenance, package_versions
    from scripts.pilot_setup import _joern_import

    provenance = git_provenance()
    if provenance["q_joern_pin"] != "matches_pin":
        raise RuntimeError("Q/Joern pin unverifiable or changed; use a full clone and restore pinned files")
    report = {"hostname": socket.gethostname(), "job_id": os.environ.get("JOB_ID"),
              "provenance": provenance, "packages": package_versions(ALL_PACKAGES)}
    if gpu:
        import bitsandbytes  # noqa: F401 - verify native library import
        import peft  # noqa: F401
        import torch
        import transformers  # noqa: F401
        import vllm

        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("Expected exactly one scheduler-assigned visible CUDA GPU. "
                               "Check CUDA_VISIBLE_DEVICES with UCL support; do not guess a device ID")
        device = torch.cuda.get_device_properties(0)
        if device.total_memory < 70 * 2**30 or not torch.cuda.is_bf16_supported():
            raise RuntimeError("Need an A100 80 GB with BF16; request gpu=1 and allow=UV")
        # Exercises CUDA allocation and a BF16 kernel without loading any model.
        a = torch.ones((32, 32), device="cuda", dtype=torch.bfloat16)
        if (a @ a).sum().item() != 32768:
            raise RuntimeError("BF16 CUDA smoke check failed")
        del a
        torch.cuda.empty_cache()
        report["gpu"] = {"name": device.name, "vram_gib": device.total_memory / 2**30,
                         "cuda": torch.version.cuda, "vllm": vllm.__version__,
                         "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}
    if joern:
        ok, detail = _joern_import(cfg)
        if not ok:
            raise RuntimeError(detail)
        report["joern"] = detail
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("resolve-joern", "configure", "prefetch",
                                            "render", "wait-joern", "doctor"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--joern-digest")
    parser.add_argument("--base-revision", default="")
    parser.add_argument("--q-context", type=int, default=4096)
    parser.add_argument("--q-memory", type=float, default=.92)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--without-joern", action="store_true")
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args()
    if args.command == "resolve-joern":
        print(resolve_joern())
        return
    if args.command == "configure":
        configure(args.config, args.runtime, args.joern_digest, args.base_revision,
                  args.q_context, args.q_memory)
        return
    if args.command == "wait-joern":
        wait_joern(args.port)
        return
    cfg = json.loads(args.config.read_text())
    if args.command == "prefetch":
        prefetch(cfg, args.cache)
    elif args.command == "render":
        render(cfg, args.output, args.port, probe=args.probe, calibration=args.calibration)
    else:
        print(json.dumps(doctor(cfg, gpu=args.gpu, joern=not args.without_joern), indent=2))


if __name__ == "__main__":
    main()
