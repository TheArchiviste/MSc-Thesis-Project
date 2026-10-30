#!/usr/bin/env bash
# Complete CPU selector conformance; no Q generation.
set -euo pipefail
ulimit -c 0
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -x .venv/bin/python && -f work/rq1-v7/config.json ]] || { echo 'Run rq1/local_prepare.sh first.' >&2; exit 1; }
if [[ -f work/rq1-v7/acquisition-freeze.json ]]; then
    .venv/bin/python - <<'PY'
from pathlib import Path
from rq1.setup import load_config, require_acquisition_freeze
require_acquisition_freeze(load_config(Path('work/rq1-v7/config.json')))
print('RQ1_ACQUISITION_ALREADY_FROZEN: no repeated corpus scan')
PY
    exit 0
fi
.venv/bin/python -m rq1.setup conformance
.venv/bin/python -m rq1.setup doctor --profile local --work work/rq1-v7/local-doctor
.venv/bin/python -m rq1.setup acquisition-freeze
.venv/bin/python -m ops.rq1_api_calibration inspect
printf '%s\n' 'RQ1_LOCAL_SELECTOR_OK'
