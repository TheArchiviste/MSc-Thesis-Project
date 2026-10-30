import io
import json
import signal
import subprocess
import sys
import tarfile
from contextlib import nullcontext
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops import rq1_vm_calibration as vm
from ops.rq1_vm_checkpoint import MODEL, WORK


def receipt(cache):
    return {'technical_ready': True, 'environment': {'packages': {'vllm': '0.6.6.post1'}},
            'core_contract': {'source': 'fixed'}, 'cache_path': str(cache)}


def test_preflight_accepts_the_actual_recorded_environment_and_cache(tmp_path):
    r = receipt(tmp_path)
    vm.validate_preflight(r, r['environment'], r['core_contract'], tmp_path)


@pytest.mark.parametrize('changed', ('technical_ready', 'environment', 'core_contract', 'cache_path'))
def test_preflight_rejects_changes_before_loading_weights(tmp_path, changed):
    r = receipt(tmp_path)
    actual = {'environment': r['environment'], 'core_contract': r['core_contract'], 'cache_path': tmp_path}
    r[changed] = False if changed == 'technical_ready' else str(tmp_path / 'changed') if changed == 'cache_path' else {}
    with pytest.raises(ValueError, match='Restore the accepted VM'):
        vm.validate_preflight(r, current_environment=actual['environment'],
                              core_contract=actual['core_contract'], cache_path=actual['cache_path'])


def test_startup_does_not_use_an_answer_from_another_model(tmp_path, monkeypatch):
    opener = SimpleNamespace(open=lambda *a, **kw: io.StringIO(json.dumps({'data': [{'id': 'another-model'}]})))
    monkeypatch.setattr(vm.urllib.request, 'build_opener', lambda *a: opener)
    monkeypatch.setattr(vm.time, 'sleep', lambda *a: pytest.fail('Do not retry a model mismatch'))
    with pytest.raises(ValueError, match='pinned assessor'):
        vm.wait_for_server(SimpleNamespace(poll=lambda: None), tmp_path / 'models.json')
    assert not (tmp_path / 'models.json').exists()


def test_startup_gets_model_metadata_without_generating_a_smoke_answer(tmp_path, monkeypatch):
    paths = []
    def get(url, **kw):
        paths.append(url)
        return io.StringIO(json.dumps({'data': [{'id': MODEL}]}))
    monkeypatch.setattr(vm.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=get))
    vm.wait_for_server(SimpleNamespace(poll=lambda: None), tmp_path / 'models.json')
    assert paths == ['http://127.0.0.1:8001/v1/models']
    assert json.loads((tmp_path / 'models.json').read_text())['response']['data'][0]['id'] == MODEL


def test_startup_failure_stops_before_sending_any_requests(tmp_path, monkeypatch):
    opener = SimpleNamespace(open=lambda *a, **kw: pytest.fail('Exited server cannot receive a request'))
    monkeypatch.setattr(vm.urllib.request, 'build_opener', lambda *a: opener)
    with pytest.raises(RuntimeError, match='exited during startup'):
        vm.wait_for_server(SimpleNamespace(poll=lambda: 1), tmp_path / 'models.json')


def test_shutdown_escalates_only_the_owned_process_group(monkeypatch):
    calls = []
    live = [123456]
    def killpg(group, sig):
        calls.append((group, sig))
        if sig == signal.SIGTERM:
            live.clear()
    monkeypatch.setattr(vm.os, 'killpg', killpg)
    monkeypatch.setattr(vm, 'live_group_members', lambda group: live[:])
    clock = count(step=10)
    monkeypatch.setattr(vm.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(vm.time, 'sleep', lambda delay: None)
    process = SimpleNamespace(pid=123456, poll=lambda: 0, wait=lambda **kw: 0)
    assert vm.stop_owned_server(process)
    assert calls == [(123456, signal.SIGINT), (123456, signal.SIGTERM)]


def test_dead_zombie_entries_do_not_count_as_live_workers(tmp_path):
    for pid, state, group in ((101, 'S', 10), (102, 'Z', 10), (103, 'D', 10), (104, 'R', 20)):
        p = tmp_path / str(pid)
        p.mkdir()
        (p / 'stat').write_text(f'{pid} (name with ) parentheses) {state} 1 {group} 10 0 0\n')
    assert vm.live_group_members(10, proc_root=tmp_path) == [101, 103]


def test_mismatched_proc_namespace_cannot_falsely_confirm_shutdown(monkeypatch):
    monkeypatch.setattr(vm, 'proc_namespace_matches', lambda: False)
    with pytest.raises(RuntimeError, match='namespaces differ'):
        vm.live_group_members(123456)


@pytest.mark.skipif(sys.platform != 'linux', reason='The deployment and /proc lifecycle are Linux-specific')
def test_real_owned_launcher_and_child_are_stopped():
    if not vm.proc_namespace_matches():
        pytest.skip('This executor exposes host /proc with different PID mappings; CI and the VM use normal Linux namespaces')
    code = ('import subprocess, sys, time; '
            'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]); '
            'print(child.pid, flush=True); time.sleep(60)')
    p = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        child = int(p.stdout.readline())
        assert {p.pid, child} <= set(vm.live_group_members(p.pid))
        assert vm.stop_owned_server(p)
        assert not vm.live_group_members(p.pid)
    finally:
        try:
            vm.os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait(timeout=10)
        p.stdout.close()


def put(root, path, content):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_export_preserves_raw_failures_and_excludes_keys_and_weights(tmp_path):
    session = tmp_path / WORK / 'calibration-sessions' / 'test-session'
    put(tmp_path, session.relative_to(tmp_path) / 'server.log', 'load failed\n')
    raw = put(tmp_path, WORK / 'calibration/responses.jsonl', '{"raw":true}\n')
    put(tmp_path, WORK / 'calibration/responses.errors.jsonl', '{"error":true}\n')
    put(tmp_path, WORK / 'calibration/public/requests.jsonl', '{"public":true}\n')
    put(tmp_path, WORK / 'calibration/private/answer_key.jsonl', 'PRIVATE')
    put(tmp_path, WORK / 'calibration/public/unexpected.jsonl', 'DO NOT EXPORT')
    put(tmp_path, Path('huggingface/model.safetensors'), 'WEIGHTS')
    archive = vm.bundle(tmp_path, session)
    assert raw.read_text() == '{"raw":true}\n'
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert str(raw.relative_to(tmp_path)) in names
        assert str(WORK / 'calibration/responses.errors.jsonl') in names
        assert not any('private' in name or 'safetensors' in name for name in names)
        assert not any('unexpected' in name for name in names)
        manifest = json.load(tar.extractfile(str(session.relative_to(tmp_path) / 'export-manifest.json')))
        assert manifest['calibration_accepted'] is False
        assert manifest['contains_model_weights'] is False
    assert archive.with_suffix('.tgz.sha256').read_text().endswith('  ' + archive.name + '\n')
    with pytest.raises(FileExistsError):
        vm.bundle(tmp_path, session)


def test_export_rejects_external_symlink_targets(tmp_path):
    session = tmp_path / WORK / 'calibration-sessions' / 'test-session'
    session.mkdir(parents=True)
    secret = put(tmp_path, Path('secret'), 'not an export input')
    (session / 'secret.log').symlink_to(secret)
    with pytest.raises(ValueError, match='symlink'):
        vm.bundle(tmp_path, session)


@pytest.mark.parametrize('name', ('responses.jsonl', 'responses.errors.jsonl', 'assessments.initial.jsonl', 'acceptance.json'))
def test_existing_acquisition_is_never_retried_or_replaced(tmp_path, monkeypatch, name):
    prior = put(tmp_path, WORK / 'calibration' / name, 'preserve this exactly')
    monkeypatch.setattr(vm.subprocess, 'run', lambda *a, **kw: pytest.fail('No server startup after a prior acquisition'))
    with pytest.raises(ValueError, match='Prior calibration acquisition'):
        vm.acquire(tmp_path, tmp_path / 'session', {})
    assert prior.read_text() == 'preserve this exactly'


@pytest.mark.parametrize('failure_stage', ('generation', 'import'))
@pytest.mark.parametrize('cleanup', ('success', 'unconfirmed', 'exception'))
def test_owned_server_is_stopped_and_raw_output_retained_after_failure(tmp_path, monkeypatch, failure_stage, cleanup):
    from rq1 import calibration, judge, setup

    r = receipt(tmp_path / 'cache')
    monkeypatch.setenv('HF_HOME', r['cache_path'])
    monkeypatch.setattr(vm, 'environment', lambda: r['environment'])
    monkeypatch.setattr(vm, 'proc_namespace_matches', lambda: True)
    monkeypatch.setattr(vm, 'verify_manifest', lambda root: {'core_contract': r['core_contract']})
    monkeypatch.setattr(vm, 'git_provenance', lambda: {'commit': 'fixed', 'modified_tracked_files': ''})
    monkeypatch.setattr(setup, 'verify_implementation', lambda: None)
    monkeypatch.setattr(setup, 'corpus_contract', lambda: r['core_contract'])
    put(tmp_path, WORK / 'vm-preflight/vm-preflight.json', json.dumps(r))
    packets = {str(i): {'review_id': str(i)} for i in range(12)}
    requests = [{**p, 'pass_id': 'calibration'} for p in packets.values()]
    monkeypatch.setattr(calibration, 'bank', lambda: (packets, []))
    put(tmp_path, WORK / 'calibration/public/packets.jsonl', ''.join(json.dumps(p) + '\n' for p in packets.values()))
    put(tmp_path, WORK / 'calibration/public/requests.jsonl', ''.join(json.dumps(p) + '\n' for p in requests))
    monkeypatch.setattr(vm.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(vm.socket, 'socket', lambda: nullcontext(SimpleNamespace(connect_ex=lambda *a: 1)))
    started, stopped = [], []
    process = SimpleNamespace(pid=123456)
    def start(*args, **kwargs):
        started.append(kwargs)
        return process
    monkeypatch.setattr(vm.subprocess, 'Popen', start)
    monkeypatch.setattr(vm, 'wait_for_server', lambda *a: None)
    def stop(p):
        stopped.append(p)
        if cleanup == 'exception':
            raise OSError('cleanup failed')
        return cleanup == 'success'
    monkeypatch.setattr(vm, 'stop_owned_server', stop)
    raw = tmp_path / WORK / 'calibration/responses.jsonl'
    def generate(*args):
        raw.write_text('{"content":"actual response retained"}\n')
        if failure_stage == 'generation':
            raise RuntimeError('generation failed')
    def import_grades(*args):
        raise RuntimeError('import failed')
    monkeypatch.setattr(judge, 'execute', generate)
    monkeypatch.setattr(judge, 'import_responses', import_grades)
    session = tmp_path / 'session'
    session.mkdir()
    summary = {}
    with pytest.raises(RuntimeError, match=f'{failure_stage} failed'):
        vm.acquire(tmp_path, session, summary)
    assert started[0]['start_new_session'] is True
    assert stopped == [process]
    assert summary['owned_server_stopped'] == (cleanup == 'success')
    assert summary['acquisition_error']['error'] == f'{failure_stage} failed'
    if cleanup != 'success':
        assert summary['cleanup_warning']
    assert summary.get('responses_complete', False) == (failure_stage == 'import')
    assert raw.read_text() == '{"content":"actual response retained"}\n'
    assert not (tmp_path / WORK / 'calibration/acceptance.json').exists()
