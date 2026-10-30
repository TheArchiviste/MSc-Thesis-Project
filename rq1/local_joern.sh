#!/usr/bin/env bash
# Complete CPU selector conformance; no Q generation.
set -euo pipefail
ulimit -c 0
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -x .venv/bin/python && -f work/rq1-v2/config.json ]] || { echo 'Run rq1/local_prepare.sh first.' >&2; exit 1; }
.venv/bin/python -m rq1.setup conformance
.venv/bin/python -m rq1.setup doctor --profile local --work work/rq1-v2/local-doctor
printf '%s\n' 'RQ1_LOCAL_SELECTOR_OK'
