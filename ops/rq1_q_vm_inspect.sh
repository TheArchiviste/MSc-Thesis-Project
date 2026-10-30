#!/usr/bin/env bash
# One existing-VM technical checkpoint. No Q load, downloads or inference.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ops/rq1_ssh_ready.sh
rq1_vm_ip=${1:?Usage: bash ops/rq1_q_vm_inspect.sh CURRENT_VM_PUBLIC_IP}
[[ "$rq1_vm_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Supply the current IPv4 address from the Nebius console.' >&2; exit 2; }
rq1_key="$HOME/.ssh/nebius_rq1"
rq1_exports=/mnt/d/Dissertation-RQ1/exports
rq1_bundle="$rq1_exports/rq1-q-inputs-20261030T204312205833Z.tgz"
[[ -r "$rq1_key" && -d "$rq1_exports" && -r "$rq1_bundle" && -r "$rq1_bundle.sha256" ]] || {
    echo 'The existing SSH key, accepted archive/checksum and D: exports directory must be present.' >&2
    exit 2
}
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Preserve local edits; use the clean committed checkout.' >&2; exit 2; }
python3 - "$rq1_bundle" <<'PY'
import hashlib
import sys
from pathlib import Path
p = Path(sys.argv[1])
expected = '8499daf11a7c85fdf7d4899ab82f34497e602856d79250cd586389b41106b367'
if (hashlib.sha256(p.read_bytes()).hexdigest() != expected or
        Path(str(p) + '.sha256').read_text().split() != [expected, p.name]):
    raise SystemExit('Accepted Q-input archive/checksum differs; stop before VM transfer.')
print('Accepted Q-input archive checksum: PASS')
PY

rq1_attempt=$(mktemp -d "$rq1_exports/rq1-q-vm-inspection-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$rq1_attempt/command.log") 2>&1
rq1_finish() {
    rq1_exit=$?
    trap - EXIT
    set +e
    python3 - "$rq1_attempt" "$rq1_exit" <<'PY'
import json
import shutil
import sys
from pathlib import Path
attempt, code = Path(sys.argv[1]), int(sys.argv[2])
(attempt / 'checkpoint.json').write_text(json.dumps({
    'exit_code': code, 'checkpoint_completed': code == 0,
    'meaning': 'Technical Q-host inspection only. No model weights loaded or inference performed. Inspect the returned receipts separately.'
}, indent=2) + '\n')
archive = shutil.make_archive(str(attempt), 'zip', attempt.parent, attempt.name)
print(f'RETURN_ARCHIVE: {archive}')
PY
    echo 'STOP the existing VM in the Nebius console and verify Stopped. Return the inspection ZIP; pause before Q loading.'
    exit "$rq1_exit"
}
trap rq1_finish EXIT

rq1_wait_for_ssh "$rq1_vm_ip" "$rq1_key" "$rq1_attempt/ssh-readiness.log"
rq1_ssh=(-i "$rq1_key" -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
scp "${rq1_ssh[@]}" "$rq1_bundle" "$rq1_bundle.sha256" "rq1@$rq1_vm_ip:~/"
rq1_remote_exit=0
ssh "${rq1_ssh[@]}" "rq1@$rq1_vm_ip" 'bash -s' <<'REMOTE' || rq1_remote_exit=$?
set -euo pipefail
cd "$HOME"
sha256sum -c rq1-q-inputs-20261030T204312205833Z.tgz.sha256
cd "$HOME/rq1-project"
[[ -x .venv-q/bin/python ]] || { echo 'Preserve the existing Q environment; .venv-q is missing.' >&2; exit 2; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Preserve VM edits; inspection requires a clean checkout.' >&2; exit 2; }
timeout 120 git fetch origin
git switch main
timeout 120 git pull --ff-only origin main
export HF_HOME="$HOME/rq1-storage/huggingface"

.venv-q/bin/python - <<'PY'
from pathlib import Path
import hashlib
import json
import tarfile

root = Path.cwd().resolve()
archive = Path.home() / 'rq1-q-inputs-20261030T204312205833Z.tgz'
expected = '8499daf11a7c85fdf7d4899ab82f34497e602856d79250cd586389b41106b367'
if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
    raise SystemExit('Remote archive differs from the independently accepted checksum.')
for split in ('development', 'main'):
    if any((root / 'work/rq1-v7' / split / name).exists() for name in ('queries.jsonl', 'slices.jsonl', 'experiment_lock.json')):
        raise SystemExit('Existing v7 acquisition found. Preserve it and return diagnostics; do not reinstall inputs.')
with tarfile.open(archive, 'r:gz') as tar:
    members = tar.getmembers()
    if len({m.name for m in members}) != len(members):
        raise SystemExit('Duplicate archive paths.')
    data = {}
    allowed = (root / 'work/rq1-v7').resolve()
    for member in members:
        target = root / member.name
        if (not member.isfile() or member.issym() or member.islnk() or
                member.name.startswith('/') or '..' in Path(member.name).parts or
                not target.resolve().is_relative_to(allowed)):
            raise SystemExit('Unexpected archive entry; preserve the VM files.')
        data[member.name] = tar.extractfile(member).read()
manifest_name = 'work/rq1-v7/q-transfer-manifest.json'
manifest = json.loads(data[manifest_name])
payload = {n: hashlib.sha256(b).hexdigest() for n, b in data.items() if n != manifest_name}
if len(payload) != 167 or manifest['files'] != payload:
    raise SystemExit('Incomplete or changed Q-transfer payload.')
for name, content in data.items():
    target = root / name
    if target.exists() and (not target.is_file() or target.is_symlink() or target.read_bytes() != content):
        raise SystemExit(f'Preserving conflicting VM input: {name}')
for name, content in data.items():
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(content)
print('Q input transfer installed: all 167 payload hashes match; existing evidence preserved.')
PY

.venv-q/bin/python -m rq1.setup verify
df -h "$HF_HOME"
timeout 180 .venv-q/bin/python -u -m ops.rq1_q_handoff inspect
REMOTE

# Retrieve available technical receipts even when the inspection blocked.
for rq1_name in gpu-doctor/readiness.json q-vm-inspection.json; do
    rq1_dest=${rq1_name//\//-}
    scp "${rq1_ssh[@]}" "rq1@$rq1_vm_ip:rq1-project/work/rq1-v7/$rq1_name" "$rq1_attempt/$rq1_dest" || true
done
exit "$rq1_remote_exit"
