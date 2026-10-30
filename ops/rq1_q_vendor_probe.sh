#!/usr/bin/env bash
# Check the existing Q host's metadata only. Never invoke Q or modify its records.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ops/rq1_ssh_ready.sh
rq1_vm_ip=${1:?Supply CURRENT_VM_PUBLIC_IP FAILED_Q_ARCHIVE ARCHIVE_SHA256 PRIVATE_INSPECTION_ZIP INSPECTION_SHA256}
rq1_archive=${2:?Supply the preserved failed Q archive on D:}
rq1_archive_sha=${3:?Supply its independently returned SHA256}
rq1_inspection=${4:?Supply the accepted private inspection ZIP}
rq1_inspection_sha=${5:?Supply its accepted SHA256}
[[ "$rq1_vm_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 2
[[ "$rq1_archive_sha" =~ ^[a-f0-9]{64}$ && "$rq1_inspection_sha" =~ ^[a-f0-9]{64}$ ]] || exit 2
rq1_key="$HOME/.ssh/nebius_rq1"
rq1_exports=/mnt/d/Dissertation-RQ1/exports
[[ -r "$rq1_key" && -d "$rq1_exports" ]] || exit 2
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Preserve local changes; use clean committed main.' >&2; exit 2; }
rq1_receipt_sha=$(python3 - "$rq1_archive" "$rq1_archive_sha" "$rq1_inspection" "$rq1_inspection_sha" <<'PY'
from pathlib import Path
import re
import sys
from ops.rq1_q_diagnose import diagnose, inspection_reference
archive, sha, inspection, inspection_sha = sys.argv[1:]
p = Path(archive)
if not re.fullmatch(r'rq1-sealed-development-query-[0-9TZ]+\.tgz', p.name):
    raise SystemExit('Unexpected archive filename; preserve it.')
reference = inspection_reference(Path(inspection), inspection_sha)
result = diagnose(p, sha, reference)
assert result['provenance_validation']['failed_checks'] == ['runtime_matches_stage_lock']
assert result['inspection_reference']['acquisition_contract_matches']
assert result['inspection_reference']['receipt_matches_attempt_marker']
assert result['environment_comparisons'][0]['stage_matches_accepted_inspection']
print(reference['receipt_sha256'])
PY
)
rq1_archive_name=$(basename "$rq1_archive")
rq1_attempt=$(mktemp -d "$rq1_exports/rq1-q-vendor-proof-session-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
rq1_run_name=$(basename "$rq1_attempt")
exec > >(tee "$rq1_attempt/command.log") 2>&1
rq1_finish() {
    rq1_exit=$?
    trap - EXIT
    set +e
    python3 - "$rq1_attempt" "$rq1_exit" "$rq1_archive_sha" "$rq1_archive" "$rq1_receipt_sha" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
import tarfile
from ops.rq1_q_diagnose import digest
attempt, code, original_sha = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
archive, receipt_sha = Path(sys.argv[4]), sys.argv[5]
result = {'checkpoint': 'Q runtime metadata probe', 'wrapper_exit_code': code,
          'checkpoint_completed': False, 'probe_passed': False,
          'instruction': 'Stop the VM in the Nebius console. Return this summary only; preserve the proof and original Q archive.'}
proof, summary = attempt / 'proof.json', attempt / 'remote-summary.json'
if proof.is_file() and summary.is_file():
    try:
        source, body = json.loads(summary.read_text()), json.loads(proof.read_text())
        verified = digest(proof) == source['proof_sha256']
        if body.get('probe_passed'):
            with tarfile.open(archive, 'r:gz') as tar:
                archived_hashes = {name: hashlib.sha256(tar.extractfile('work/rq1-v7/development/' + name).read()).hexdigest()
                                   for name in body['original_file_hashes']}
            verified = (verified and body['original_archive_sha256'] == original_sha and
                        body['protocol'] == 'rq1-v7-bundled-metadata-probe-v2' and
                        digest(archive) == original_sha and archived_hashes == body['original_file_hashes'] and
                        body['accepted_inspection_receipt_sha256'] == receipt_sha and
                        body['probe_code_sha256'] == digest(Path('ops/rq1_q_vendor_probe.py')) and
                        body['query_record_count'] == 6 and
                        body['checks'] and all(value is True for value in body['checks'].values()))
        result['local_proof_checksum_verified'] = bool(verified)
        if verified:
            for key in ('protocol', 'probe_passed', 'checks', 'blocked_check', 'model_loaded', 'generation_repeated',
                        'query_record_count', 'changed_package_count', 'original_archive_sha256', 'unexplained_package_names'):
                if key in body:
                    result[key] = body[key]
            result['proof_sha256'] = digest(proof)
            result['checkpoint_completed'] = code == 0 and body['probe_passed'] is True
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError):
        result['local_proof_checksum_verified'] = False
if code == 0 and not result['checkpoint_completed']:
    result['wrapper_exit_code'] = 1
output = attempt.with_suffix('.summary.json')
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
print(f'RETURN_SUMMARY: {output}')
raise SystemExit(result['wrapper_exit_code'])
PY
    rq1_exit=$?
    echo 'STOP the VM in the Nebius console and verify Stopped. Do not rerun Q.'
    exit "$rq1_exit"
}
trap rq1_finish EXIT
rq1_wait_for_ssh "$rq1_vm_ip" "$rq1_key" "$rq1_attempt/ssh-readiness.log"
rq1_ssh=(-i "$rq1_key" -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
rq1_remote_exit=0
ssh "${rq1_ssh[@]}" "rq1@$rq1_vm_ip" "bash -s -- $rq1_receipt_sha $rq1_archive_name $rq1_archive_sha $rq1_run_name" <<'REMOTE' || rq1_remote_exit=$?
set -euo pipefail
cd "$HOME/rq1-project"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Preserve VM edits; use clean committed main.' >&2; exit 2; }
timeout 120 git pull --ff-only origin main
.venv-q/bin/python -u -m ops.rq1_q_vendor_probe \
    "work/rq1-v7/sealed-exports/$2" "$3" "$1" "work/rq1-v7/vendor-probes/$4.json"
REMOTE
rq1_remote_proof="rq1-project/work/rq1-v7/vendor-probes/$rq1_run_name"
scp "${rq1_ssh[@]}" "rq1@$rq1_vm_ip:$rq1_remote_proof.json" "$rq1_attempt/proof.json" || true
scp "${rq1_ssh[@]}" "rq1@$rq1_vm_ip:$rq1_remote_proof.summary.json" "$rq1_attempt/remote-summary.json" || true
exit "$rq1_remote_exit"
