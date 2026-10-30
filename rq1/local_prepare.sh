#!/usr/bin/env bash
# CPU-only setup; preserve previous runs. Use the D-backed Ubuntu distribution.
set -euo pipefail
ulimit -c 0
cd "$(dirname "${BASH_SOURCE[0]}")/.."
rq1_store=/mnt/d/Dissertation-RQ1
[[ -d /mnt/d ]] || { echo 'Run inside your D-backed Ubuntu-24.04 WSL distribution.' >&2; exit 1; }
mkdir -p "$rq1_store/exports" "$rq1_store/huggingface"
export HF_HOME="$rq1_store/huggingface"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
rq1_python="$PWD/.venv/bin/python"
"$rq1_python" -m pip install --no-cache-dir -r rq1/requirements-local.txt -r rq1/requirements-tokenizer.txt
"$rq1_python" -m pip install --no-cache-dir --no-deps -e .
"$rq1_python" -m rq1.setup verify
if [[ ! -f work/rq1-v6/config.json ]]; then "$rq1_python" -m rq1.setup init; fi
for rq1_split in development main; do
    if [[ ! -f "work/rq1-v6/$rq1_split/witness_validation.jsonl" ]]; then
        "$rq1_python" -m rq1.setup validate --split "$rq1_split"
    fi
done
"$rq1_python" - <<'PY'
from pathlib import Path
from evidence_experiment.locks import require_witnesses
from evidence_experiment.schema import load_cases
for split in ('development', 'main'):
    cases = load_cases(Path('rq1') / f'{split}.jsonl')
    require_witnesses(Path('work/rq1-v6') / split, cases)
    print(f'RQ1_WITNESSES_VERIFIED {split}: {len(cases)} cases / {2*len(cases)} U/F sources')
PY
"$rq1_python" -m rq1.calibration prepare
"$rq1_python" -m rq1.setup token-audit
printf '%s\n' 'RQ1_LOCAL_PREPARATION_OK: 15 cases, 30 U/F inputs; no Q weights loaded.'
