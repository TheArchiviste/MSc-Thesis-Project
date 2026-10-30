"""Run one bounded assessor calibration session, preserving responses and stopping our server."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from evidence_experiment.locks import environment, git_provenance, now, work_lock
from evidence_experiment.schema import file_digest, index_jsonl, read_jsonl, write_json
from ops.rq1_vm_checkpoint import MODEL, WORK, plan, verify_manifest


def validate_preflight(receipt, current_environment, core_contract, cache_path):
    if (receipt.get('technical_ready') is not True or
            receipt.get('environment') != current_environment or
            receipt.get('core_contract') != core_contract or
            Path(receipt['cache_path']).resolve() != cache_path.resolve()):
        raise ValueError('Restore the accepted VM environment, source contract and HF_HOME before loading a model')


def validate_models(payload):
    if MODEL not in {row.get('id') for row in payload.get('data', [])}:
        raise ValueError('The running server does not report the pinned assessor model')


def wait_for_server(process, destination, *, timeout=1800):
    deadline = time.monotonic() + timeout
    # All polling is GET-only; it generates no smoke answers or calibration retries.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Assessor server exited during startup; inspect server.log')
        try:
            with opener.open('http://127.0.0.1:8001/v1/models', timeout=3) as response:
                models = json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(5)
            continue
        validate_models(models)
        write_json(destination, {'utc': now(), 'response': models})
        return
    raise TimeoutError('Assessor startup exceeded 30 minutes; partial downloads are retained')


def proc_namespace_matches():
    try:
        raw = Path('/proc/self/stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        return int(raw.split(' ', 1)[0]) == os.getpid() and int(fields[2]) == os.getpgrp()
    except (OSError, ValueError, IndexError):
        return False


def live_group_members(group, *, proc_root=Path('/proc')):
    """Linux process states distinguish live workers from already-dead zombie entries."""
    if proc_root == Path('/proc') and not proc_namespace_matches():
        raise RuntimeError('Cannot confirm shutdown: /proc and Python process namespaces differ')
    members = []
    for directory in proc_root.iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            raw = (directory / 'stat').read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        # comm may contain spaces and parentheses; state is the first field after its closing ).
        fields = raw[raw.rfind(')') + 2:].split()
        if int(fields[2]) == group and fields[0] not in {'Z', 'X', 'x'}:
            members.append(int(directory.name))
    return sorted(members)


def stop_owned_server(process):
    """Reap our launcher and wait for its live process-group workers after each signal."""
    for sig, timeout in ((signal.SIGINT, 20), (signal.SIGTERM, 10), (signal.SIGKILL, 10)):
        process.poll()
        if not live_group_members(process.pid):
            process.wait(timeout=10)
            return True
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            process.wait(timeout=10)
            return True
        deadline = time.monotonic() + timeout
        while True:
            process.poll()
            if not live_group_members(process.pid):
                process.wait(timeout=10)
                return True
            if time.monotonic() >= deadline:
                break
            time.sleep(.1)
    return False


def bundle(root, session):
    """Export public inputs and actual results/logs, excluding private keys and model caches."""
    calibration = root / WORK / 'calibration'
    files = [*session.rglob('*'), calibration / 'public/packets.jsonl', calibration / 'public/requests.jsonl']
    files += [calibration / name for name in (
        'responses.jsonl', 'responses.errors.jsonl', 'assessments.initial.jsonl',
        'assessments.initial.provenance.json')]
    files += [root / WORK / name for name in (
        'config.json', 'assessor.vm.json', 'assessor.vm-plan.json',
        'assessor.vm-token-audit.json', 'assessor-server-command.json',
        'vm-preflight/vm-preflight.json', 'vm-preflight/readiness.json')]
    files = sorted({p for p in files if p.is_file()})
    if any(p.is_symlink() for p in files):
        raise ValueError('Do not export symlink targets')
    manifest = {'utc': now(), 'files': {str(p.relative_to(root)): file_digest(p) for p in files},
                'contains_model_weights': False, 'calibration_accepted': False}
    manifest_path = session / 'export-manifest.json'
    write_json(manifest_path, manifest, exclusive=True)
    exports = root / WORK / 'calibration-exports'
    exports.mkdir(parents=True, exist_ok=True)
    archive = exports / f'rq1-assessor-calibration-{session.name}.tgz'
    with tarfile.open(archive, 'x:gz') as tar:
        for path in [*files, manifest_path]:
            tar.add(path, arcname=str(path.relative_to(root)), recursive=False)
    archive.with_suffix('.tgz.sha256').write_text(file_digest(archive) + '  ' + archive.name + '\n')
    return archive


def acquire(root, session, summary):
    from rq1.calibration import bank
    from rq1.judge import execute, import_responses
    from rq1.setup import corpus_contract, verify_implementation

    calibration = root / WORK / 'calibration'
    # No automatic resumption, repair or replacement of an earlier acquired response set.
    if any((calibration / name).exists() for name in (
            'responses.jsonl', 'responses.errors.jsonl', 'assessments.initial.jsonl', 'acceptance.json')):
        raise ValueError('Prior calibration acquisition exists; preserve it and return diagnostics before continuing')
    verify_implementation()
    manifest = verify_manifest(root)
    provenance = git_provenance()
    if provenance['modified_tracked_files'] or not provenance['commit']:
        raise ValueError('Use a clean committed checkout')
    receipt = json.loads((root / WORK / 'vm-preflight/vm-preflight.json').read_text())
    cache = Path(os.environ.get('HF_HOME', Path.home() / '.cache/huggingface'))
    validate_preflight(receipt, environment(), corpus_contract(), cache)
    if not proc_namespace_matches():
        raise RuntimeError('Cannot manage an owned server safely: /proc and Python process namespaces differ')
    packets, _ = bank()
    if index_jsonl(calibration / 'public/packets.jsonl', 'review_id') != packets:
        raise ValueError('The public calibration bank differs from the frozen 12 anchors')
    requests = read_jsonl(calibration / 'public/requests.jsonl')
    if (len(requests) != 12 or {r['review_id'] for r in requests} != packets.keys() or
            any(r['pass_id'] != 'calibration' for r in requests)):
        raise ValueError('Use exactly the 12 frozen calibration requests')
    summary['provenance'] = provenance
    summary['core_contract'] = manifest['core_contract']
    summary['environment'] = environment()
    summary['plan'] = plan()
    print('Checking vLLM server imports and arguments before downloading weights...', flush=True)
    with (session / 'server-import-check.log').open('w') as stream:
        subprocess.run([sys.executable, '-m', 'vllm.entrypoints.openai.api_server', '--help'],
                       stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', 8001)) == 0:
            raise ValueError('Port 8001 is occupied; no existing server will be reused or stopped')
    command = [sys.executable, '-u', '-m', 'ops.rq1_vm_checkpoint', 'serve-assessor']
    write_json(session / 'launcher.json', {'utc': now(), 'command': command}, exclusive=True)
    process = None
    primary_failed = False
    try:
        print('Downloading/loading the pinned assessor. Startup is limited to 30 minutes.', flush=True)
        with (session / 'server.log').open('w') as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                       cwd=root, start_new_session=True)
            summary['owned_process_group'] = process.pid
            wait_for_server(process, session / 'models.json')
            summary['model_load_tested'] = True
            print('Assessor is ready. Running the 12 frozen stateless requests once...', flush=True)
            execute(calibration / 'public/requests.jsonl', root / WORK / 'assessor.vm.json',
                    calibration / 'responses.jsonl')
            summary['responses_complete'] = True
            import_responses(calibration / 'public/requests.jsonl', calibration / 'responses.jsonl',
                             calibration / 'assessments.initial.jsonl')
            summary['assessments_imported'] = True
    except BaseException as exc:  # Retain the acquisition error while cleaning up.
        primary_failed = True
        summary['acquisition_error'] = {'error_type': type(exc).__name__, 'error': str(exc)}
        raise
    finally:
        if process is not None:
            try:
                summary['owned_server_stopped'] = stop_owned_server(process)
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask a primary error
                summary['owned_server_stopped'] = False
                summary['cleanup_error'] = {'error_type': type(exc).__name__, 'error': str(exc)}
            if not summary['owned_server_stopped']:
                summary['cleanup_warning'] = 'Could not confirm that owned live workers stopped; stop the VM in the console'
                if not primary_failed:
                    raise RuntimeError(summary['cleanup_warning'])


def interrupted(signum, frame):
    raise InterruptedError(f'Session interrupted by signal {signum}')


def main():
    raise SystemExit('Historical v1/v2 assessor route. Current v3 uses ops.rq1_api_calibration for grading and ops.rq1_q_handoff for Q. No model or paid request was started.')


def historical_main():
    from rq1.setup import ROOT
    os.chdir(ROOT)
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    session = ROOT / WORK / 'calibration-sessions' / f'{stamp}-{os.getpid()}'
    session.mkdir(parents=True, exist_ok=False)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)
    summary = {'started_utc': now(), 'model_load_tested': False, 'responses_complete': False,
               'assessments_imported': False, 'calibration_accepted': False,
               'meaning': 'Acquisition only. The assistant must audit all labels/source proofs before acceptance.'}
    status = 0
    try:
        with work_lock(ROOT / WORK / 'calibration'):
            acquire(ROOT, session, summary)
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 - export actual failure diagnostics after cleanup
        status = 1
        summary['error_type'] = type(exc).__name__
        summary['error'] = str(exc)
        print(f'RQ1_CALIBRATION_BLOCKED: {type(exc).__name__}: {exc}', flush=True)
        for name in ('server-import-check.log', 'server.log'):
            path = session / name
            if path.exists():
                print(f'Last lines of {name}:', flush=True)
                print('\n'.join(path.read_text(errors='replace').splitlines()[-45:]), flush=True)
    summary['finished_utc'] = now()
    responses = ROOT / WORK / 'calibration/responses.jsonl'
    try:
        summary['saved_responses'] = len(read_jsonl(responses)) if responses.exists() else 0
    except (ValueError, OSError):
        # A disrupted write must still be exported verbatim for diagnosis.
        summary['saved_responses'] = 'unreadable; inspect the preserved raw file'
        status = 1
    write_json(session / 'summary.json', summary, exclusive=True)
    archive = bundle(ROOT, session)
    print(json.dumps({k: v for k, v in summary.items() if k not in {'environment', 'core_contract'}}, indent=2))
    print(f'RETURN_ARCHIVE: {archive}')
    print('NEXT: download the archive/checksum, then STOP the VM in the Nebius console and return the archive. No Q acquisition.')
    raise SystemExit(status)


if __name__ == '__main__':
    main()
