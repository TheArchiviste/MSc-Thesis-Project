"""Wait for Joern's real WebSocket greeting without importing experiment inputs."""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path


async def greeting(host, port):
    # Use the same transport and expected greeting as the pinned Joern client.
    from cpgqls_client.client import CPGQLSClient, CPGQLSTransport

    async with CPGQLSTransport().connect(f"ws://{host}:{port}/connect") as connection:
        message = await connection.recv()
        if message != CPGQLSClient.CPGQLS_MSG_CONNECTED:
            raise ValueError("Unexpected Joern WebSocket greeting")


def container_running():
    result = subprocess.run(
        ["docker", "inspect", "llmxcpg_joern", "--format", "{{.State.Running}}"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


async def wait_for_protocol(host, port, *, seconds=300, interval=3, attempt_seconds=5,
                            check_running=container_running, report=print):
    from websockets.exceptions import WebSocketException

    if seconds <= 0 or interval < 0 or attempt_seconds <= 0:
        raise ValueError("Invalid startup timeout or interval")
    started = time.monotonic()
    deadline = started + seconds
    next_notice = started
    result = {"protocol_ready": False, "attempts": [],
              "meaning": "WebSocket startup only; a real CPG import/query must still pass."}
    while time.monotonic() < deadline:
        try:
            running = check_running()
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["detail"] = f"Cannot inspect Joern container: {type(exc).__name__}"
            break
        if not running:
            result["detail"] = "Joern container stopped before protocol readiness"
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempt = {"elapsed_seconds": round(time.monotonic() - started, 3)}
        try:
            await asyncio.wait_for(greeting(host, port), min(attempt_seconds, remaining))
        except (OSError, TimeoutError, ValueError, WebSocketException) as exc:
            attempt.update(ok=False, detail=f"{type(exc).__name__}: {str(exc)[:250]}")
        else:
            attempt.update(ok=True, detail="Received Joern's connected greeting")
            result.update(protocol_ready=True, detail=attempt["detail"])
        result["attempts"].append(attempt)
        if result["protocol_ready"]:
            report("Joern WebSocket greeting received; checking real CPG import next.", flush=True)
            break
        if time.monotonic() >= next_notice:
            report(f"Waiting for Joern to finish startup: {attempt['detail']}", flush=True)
            next_notice = time.monotonic() + 30
        remaining = deadline - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(min(interval, remaining))
    result.setdefault("detail", "Joern WebSocket did not become ready within the startup budget")
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("work/rq1-v5/config.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    result = asyncio.run(wait_for_protocol(cfg.get("joern_host", "127.0.0.1"),
                                          cfg.get("joern_port", 8080)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if not result["protocol_ready"]:
        raise SystemExit(result["detail"] + "; return this attempt's logs.")


if __name__ == "__main__":
    main()
