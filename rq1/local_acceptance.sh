#!/usr/bin/env bash
# One local checkpoint: CPU witnesses + tokenizer + full selector. ZIP always goes to D:.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
rq1_exports=/mnt/d/Dissertation-RQ1/exports
[[ -d /mnt/d ]] || { echo 'Use D-backed Ubuntu-24.04 WSL.' >&2; exit 1; }
mkdir -p "$rq1_exports" work/rq1-v6
rq1_attempt=$(mktemp -d "work/rq1-v6/local-attempt-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$rq1_attempt/command.log") 2>&1
rq1_finish() {
    rq1_exit=$?
    trap - EXIT
    set +e
    docker logs --timestamps llmxcpg_joern > "$rq1_attempt/docker.log" 2>&1
    docker inspect llmxcpg_joern > "$rq1_attempt/container.json" 2>&1
    docker compose -f rq1/compose.yml stop --timeout 10 joern >> "$rq1_attempt/docker.log" 2>&1
    python3 - "$rq1_attempt" "$rq1_exit" "$rq1_exports" <<'PY'
import json
import shutil
import sys
from pathlib import Path
attempt, code, exports = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
(attempt / 'checkpoint.json').write_text(json.dumps({'exit_code': code, 'passed': code == 0,
    'meaning': 'CPU technical readiness only; assessor calibration remains pending. No generated queries or evidence-adequacy results.'}, indent=2)+'\n')
# Collect the exact new inputs and diagnostics; historical work/rq1 files are preserved.
for rel in ('config.json', 'token-audit.json', 'joern-capability', 'local-doctor', 'development', 'main', 'calibration'):
    source = Path('work/rq1-v6') / rel
    target = attempt / 'inputs' / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir(): shutil.copytree(source, target)
    elif source.is_file(): shutil.copyfile(source, target)
archive = shutil.make_archive(str(exports / attempt.name), 'zip', attempt.parent, attempt.name)
print(f"\nCPU technical checkpoint: {'PASS' if code == 0 else 'BLOCKED'}\nReturn this ZIP: {archive}")
PY
    exit "$rq1_exit"
}
trap rq1_finish EXIT
if [[ $# -eq 0 ]]; then
    bash rq1/local_prepare.sh
    bash rq1/local_joern.sh
else
    echo 'Usage: bash rq1/local_acceptance.sh (v6 needs fresh CPU receipts; preserve v4/v5 evidence)' >&2
    exit 2
fi
printf '%s\n' 'RQ1_LOCAL_CPU_CHECKPOINT_OK: assessor calibration is the next checkpoint; pause here and return the ZIP before any cloud work.'
