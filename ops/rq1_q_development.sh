#!/usr/bin/env bash
# Collect original Q once on six development inputs; return only safe metadata.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
rq1_vm_ip=${1:?Usage: bash ops/rq1_q_development.sh CURRENT_VM_PUBLIC_IP PRIVATE_INSPECTION_ZIP EXPECTED_ZIP_SHA256}
rq1_inspection_zip=${2:?Supply the privately accepted inspection ZIP on D:}
rq1_inspection_sha=${3:?Supply the independently accepted inspection ZIP checksum}
[[ "$rq1_vm_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 2
[[ "$rq1_inspection_sha" =~ ^[a-f0-9]{64}$ ]] || exit 2
rq1_key="$HOME/.ssh/nebius_rq1"
rq1_exports=/mnt/d/Dissertation-RQ1/exports
[[ -r "$rq1_key" && -d "$rq1_exports" ]] || { echo 'Use the existing laptop SSH key and D: exports directory.' >&2; exit 2; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Preserve local changes; use clean committed main.' >&2; exit 2; }
.venv/bin/python - <<'PY'
from rq1.setup import DEFAULT_CONFIG, load_config, require_acquisition_freeze
from rq1.calibration import require_calibration
cfg = load_config(DEFAULT_CONFIG)
require_acquisition_freeze(cfg)
assert require_calibration(cfg)['accepted']
print('Local acquisition freeze and assessor acceptance: verified')
PY
rq1_receipt_sha=$(.venv/bin/python - "$rq1_inspection_zip" "$rq1_inspection_sha" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
import zipfile
from rq1.setup import corpus_contract
p, expected = Path(sys.argv[1]), sys.argv[2]
if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
    raise SystemExit('Private inspection archive differs from the independently accepted checksum.')
with zipfile.ZipFile(p) as zipped:
    files = [i for i in zipped.infolist() if i.filename.endswith('/q-vm-inspection.json')]
    if len(files) != 1 or files[0].file_size > 2_000_000:
        raise SystemExit('Expected the single privately accepted Q-host receipt.')
    raw = zipped.read(files[0])
receipt = json.loads(raw)
if receipt.get('technical_ready') is not True or receipt.get('core_contract') != corpus_contract():
    raise SystemExit('The private host receipt does not match the frozen acquisition contract.')
print(hashlib.sha256(raw).hexdigest())
PY
)
rq1_attempt=$(mktemp -d "$rq1_exports/rq1-q-development-session-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
rq1_sealed="$rq1_exports/sealed"
rq1_download="$rq1_attempt/sealed"
mkdir -p "$rq1_sealed" "$rq1_download"
exec > >(tee "$rq1_attempt/command.log") 2>&1
rq1_finish() {
    rq1_exit=$?
    trap - EXIT
    set +e
    python3 - "$rq1_attempt" "$rq1_exit" <<'PY'
from pathlib import Path
import json
import sys
attempt, code = Path(sys.argv[1]), int(sys.argv[2])
result = {'phase': 'query', 'split': 'development', 'expected_records': 6,
          'wrapper_exit_code': code, 'checkpoint_completed': code == 0,
          'instruction': 'Return this summary only. Keep raw archives unopened. Stop the VM and pause before local slicing.'}
path = attempt / 'remote-summary.json'
if path.is_file():
    try:
        source = json.loads(path.read_text())
        for key in ('exit_code', 'acquisition_sealed', 'seal_sha256', 'archive', 'archive_sha256'):
            if key in source:
                result[key] = source[key]
    except (ValueError, OSError):
        result['remote_summary_readable'] = False
result['local_archive_checksum_verified'] = (attempt / 'checksum-verified').is_file()
out = attempt.with_suffix('.summary.json')
out.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
print(f'RETURN_SUMMARY: {out}')
PY
    echo 'STOP the VM in the Nebius console and verify Stopped. Do not upload or open the sealed .tgz archive.'
    exit "$rq1_exit"
}
trap rq1_finish EXIT
rq1_ssh=(-i "$rq1_key" -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
rq1_remote_exit=0
ssh "${rq1_ssh[@]}" "rq1@$rq1_vm_ip" "bash -s -- $rq1_receipt_sha" <<'REMOTE' || rq1_remote_exit=$?
set -euo pipefail
cd "$HOME/rq1-project"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Preserve VM edits; use clean committed main.' >&2; exit 2; }
timeout 120 git fetch origin
git switch main
timeout 120 git pull --ff-only origin main
export HF_HOME="$HOME/rq1-storage/huggingface"
.venv-q/bin/python - "$1" <<'PY'
from pathlib import Path
import json
import os
import shutil
import sys
import torch
from rq1.setup import ROOT, CORPUS, DEFAULT_CONFIG, check_acquisition_ready, q_weights_cached
from evidence_experiment.schema import file_digest
from evidence_experiment.locks import environment, git_provenance, now
cfg = check_acquisition_ready(CORPUS / 'development.jsonl', DEFAULT_CONFIG, phase='query', sealed=True)
receipt = ROOT / 'work/rq1-v7/q-vm-inspection.json'
if sys.argv[1] != file_digest(receipt):
    raise SystemExit('The current Q-host receipt is not the independently accepted one.')
if json.loads(receipt.read_text())['environment'] != environment():
    raise SystemExit('Restore the accepted VM packages before Q acquisition.')
if torch.cuda.mem_get_info(0)[0] / 2**30 < 70:
    raise SystemExit('The Q host no longer has 70 GiB free GPU memory.')
cache = Path(os.environ['HF_HOME'])
existing = next(p for p in (cache, *cache.parents) if p.exists())
required = 15 if q_weights_cached(cache, cfg) else 100
if shutil.disk_usage(existing).free / 2**30 < required:
    raise SystemExit('The Q host no longer meets its accepted model-cache space requirement.')
work = ROOT / 'work/rq1-v7/development'
for name in ('q-wrapper-started.json', 'experiment_lock.json', 'queries.jsonl', 'query_sessions.jsonl',
             'query.sealed.log', 'query_load_errors.jsonl', 'query_runtime_errors.jsonl', 'query.seal.json'):
    if (work / name).exists():
        raise SystemExit('A development acquisition attempt already exists. Preserve it; return diagnostics without rerunning.')
work.mkdir(parents=True, exist_ok=True)
with (work / 'q-wrapper-started.json').open('x') as stream:
    json.dump({'utc': now(), 'provenance': git_provenance(), 'one_predeclared_attempt': True,
               'Q_host_receipt_sha256': file_digest(receipt)}, stream, indent=2)
print('Starting original Q on six fixed development U/F inputs; raw output remains sealed.', flush=True)
PY
rq1_collect_exit=0
.venv-q/bin/python -u -m ops.rq1_collect query --split development --exports work/rq1-v7/sealed-exports || rq1_collect_exit=$?
.venv-q/bin/python - <<'PY'
from pathlib import Path
import json
root = Path('work/rq1-v7/sealed-exports')
files = list(root.glob('rq1-sealed-development-query-*.summary.json'))
if len(files) != 1:
    raise SystemExit('Expected exactly one preserved development Q export summary; do not repeat acquisition.')
data = json.loads(files[0].read_text())
if data.get('split') != 'development' or data.get('phase') != 'query' or data.get('expected_records') != 6:
    raise SystemExit('Unexpected collector summary.')
target = root / 'development-query-return.json'
with target.open('x') as stream:
    json.dump(data, stream, indent=2)
PY
exit "$rq1_collect_exit"
REMOTE

scp "${rq1_ssh[@]}" "rq1@$rq1_vm_ip:rq1-project/work/rq1-v7/sealed-exports/development-query-return.json" "$rq1_attempt/remote-summary.json"
rq1_remote_archive=$(python3 - "$rq1_attempt/remote-summary.json" <<'PY'
from pathlib import PurePosixPath
import json
import re
import sys
d = json.load(open(sys.argv[1]))
p = PurePosixPath(d['archive'])
if (str(p.parent) != 'work/rq1-v7/sealed-exports' or
        not re.fullmatch(r'rq1-sealed-development-query-[0-9TZ]+\.tgz', p.name) or
        not re.fullmatch(r'[a-f0-9]{64}', d['archive_sha256'])):
    raise SystemExit('Unexpected archive metadata; preserve files and return the safe summary.')
print(p)
PY
)
scp "${rq1_ssh[@]}" "rq1@$rq1_vm_ip:rq1-project/$rq1_remote_archive" "rq1@$rq1_vm_ip:rq1-project/$rq1_remote_archive.sha256" "$rq1_download/"
python3 - "$rq1_attempt" "$rq1_download" "$rq1_sealed" <<'PY'
from pathlib import Path
import hashlib
import json
import shutil
import sys
attempt, directory, preserved = map(Path, sys.argv[1:])
d = json.loads((attempt / 'remote-summary.json').read_text())
p = directory / Path(d['archive']).name
actual = hashlib.sha256(p.read_bytes()).hexdigest()
if actual != d['archive_sha256'] or Path(str(p) + '.sha256').read_text().split() != [actual, p.name]:
    raise SystemExit('Sealed archive checksum failed. Preserve both copies and stop before local slicing.')
for source in (p, Path(str(p) + '.sha256')):
    target = preserved / source.name
    if target.exists() and hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
        raise SystemExit('A different local archive already exists. Both copies preserved; return the safe summary.')
for source in (p, Path(str(p) + '.sha256')):
    target = preserved / source.name
    if not target.exists():
        shutil.copyfile(source, target)
(attempt / 'checksum-verified').write_text(actual + '\n')
print('Full sealed development archive transferred and checksum-verified; contents remain unopened.')
PY
exit "$rq1_remote_exit"
