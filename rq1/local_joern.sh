#!/usr/bin/env bash
# Local CPU acceptance only. Preserves every attempt; does not generate Q queries.
set -euo pipefail
ulimit -c 0
cd "$(dirname "${BASH_SOURCE[0]}")/.."
rq1_python="$PWD/.venv/bin/python"
[[ -x "$rq1_python" && -f work/rq1-config.json ]] || {
    printf '%s\n' 'Complete rq1/local_prepare.sh first.' >&2
    exit 1
}
[[ ! -f work/rq1-freeze.json ]] || {
    printf '%s\n' 'Main policy is frozen; preserve it and report this checkpoint request.' >&2
    exit 1
}
mkdir -p work/rq1 work/joern-inputs
rq1_run=$(mktemp -d "work/rq1/local-readiness-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$rq1_run/command.log") 2>&1

rq1_finish() {
    rq1_result=$?
    trap - EXIT
    set +e
    docker compose -f rq1/compose.yml logs --no-color --tail=200 joern > "$rq1_run/joern.log" 2>&1
    docker inspect llmxcpg_joern --format '{{json .State}}' > "$rq1_run/container-state.json" 2>&1
    docker top llmxcpg_joern -eo pid,args > "$rq1_run/processes.txt" 2>&1
    docker exec llmxcpg_joern sh -c 'ls -1 "$JOERN_HOME"/lib/*joern-cli*' > "$rq1_run/joern-libraries.txt" 2>&1
    docker stats --no-stream llmxcpg_joern > "$rq1_run/memory.txt" 2>&1
    free -h >> "$rq1_run/memory.txt"
    cp work/rq1-config.json "$rq1_run/config.json"
    "$rq1_python" - "$rq1_run" "$rq1_result" <<'PY'
import json
import shutil
import sys
from pathlib import Path

work = Path(sys.argv[1])
ok = sys.argv[2] == "0"
result = {"checkpoint": "local_cpu_joern", "passed": ok, "exit_code": int(sys.argv[2]),
          "interpretation": "Readiness only; no Q generation or RQ1 adequacy results."}
(work / "checkpoint.json").write_text(json.dumps(result, indent=2) + "\n")
print(f"\nLocal CPU Joern: {'PASS' if ok else 'BLOCKED'}")
print(result["interpretation"])
print(f"Reports and diagnostic logs: {work}")
exports = Path("/mnt/d/Dissertation-RQ1/exports")
if exports.is_dir():
    archive = shutil.make_archive(str(exports / work.name), "zip", work.parent, work.name)
    print(f"Return this ZIP: {archive}")
PY
    exit "$rq1_result"
}
trap rq1_finish EXIT

"$rq1_python" -m rq1.setup verify
docker compose -f rq1/compose.yml config > "$rq1_run/compose-resolved.yml"
docker compose -f rq1/compose.yml up -d joern

# A bounded startup wait avoids mistaking a still-starting server for a failed import.
# The socket is only a startup signal: doctor below must import and query a real CPG.
"$rq1_python" - <<'PY'
import socket
import subprocess
import time

deadline = time.monotonic() + 300
next_notice = 0
while time.monotonic() < deadline:
    state = subprocess.run(["docker", "inspect", "llmxcpg_joern", "--format", "{{.State.Running}}"],
                           capture_output=True, text=True, timeout=10)
    if state.returncode or state.stdout.strip() != "true":
        raise SystemExit("Joern container stopped; return this attempt's logs.")
    try:
        with socket.create_connection(("127.0.0.1", 8080), timeout=2):
            print("Joern port is reachable; checking actual CPG import next.", flush=True)
            break
    except OSError:
        if time.monotonic() >= next_notice:
            print("Waiting for Joern startup (maximum five minutes)...", flush=True)
            next_notice = time.monotonic() + 30
        time.sleep(3)
else:
    raise SystemExit("Joern did not open its port within five minutes; return the logs.")
PY

"$rq1_python" -m rq1.setup pin-joern
timeout --kill-after=10s 660s "$rq1_python" -m rq1.setup doctor --profile local --work "$rq1_run"
cat "$rq1_run/readiness.md"
