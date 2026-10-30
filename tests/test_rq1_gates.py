"""Public entry points, pre-main freeze and unforgeable-by-accident gate behavior."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from evidence_experiment.schema import file_digest, write_json
from rq1 import setup


@pytest.mark.parametrize('command', ['detect', 'all', 'calibrate', 'train', 'transform'])
def test_old_non_rq1_commands_are_not_available(command):
    p = subprocess.run([sys.executable, '-m', 'evidence_experiment', command], capture_output=True, text=True, check=False)
    assert p.returncode == 2 and 'invalid choice' in p.stderr


def isolate_gate(monkeypatch, tmp_path, cfg):
    monkeypatch.setattr(setup, 'verify_corpus', lambda: {'development': 3, 'main': 12})
    monkeypatch.setattr(setup, 'verify_implementation', dict)
    monkeypatch.setattr(setup, 'token_audit_valid', lambda cfg: {})
    monkeypatch.setattr(setup, 'capability_valid', lambda cfg: {'environment': setup.environment()})
    monkeypatch.setattr(setup, 'git_provenance', lambda: {'commit': 'unit-test', 'modified_tracked_files': ''})
    from rq1 import calibration
    monkeypatch.setattr(calibration, 'require_calibration', lambda cfg: {'assessor_signature': 'test'})
    write_json(tmp_path / 'calibration/acceptance.json', {'gate_fixture_only': True})
    cfg['rq1_freeze_file'] = str(tmp_path / 'freeze.json')
    path = tmp_path / 'config.json'
    write_json(path, cfg)
    return path


def test_main_is_blocked_without_freeze(tmp_path, cfg, monkeypatch):
    config = isolate_gate(monkeypatch, tmp_path, cfg)
    with pytest.raises(FileNotFoundError):
        setup.check_acquisition_ready(setup.CORPUS / 'main.jsonl', config, phase='query')


def test_main_locks_contract_policy_and_stage_environment(tmp_path, cfg, monkeypatch):
    config = isolate_gate(monkeypatch, tmp_path, cfg)
    frozen = {'corpus_contract': setup.corpus_contract(), 'policy': setup.policy(cfg),
              'stage_environments': {'query': setup.environment()},
              'calibration_sha256': file_digest(tmp_path / 'calibration/acceptance.json'), 'assessor_signature': 'test'}
    write_json(tmp_path / 'freeze.json', frozen)
    setup.check_acquisition_ready(setup.CORPUS / 'main.jsonl', config, phase='query')
    with pytest.raises(ValueError, match='environment'):
        setup.check_acquisition_ready(setup.CORPUS / 'main.jsonl', config, phase='slice')
    write_json(tmp_path / 'freeze.json', {**frozen, 'corpus_contract': {}})
    with pytest.raises(ValueError, match='changed'):
        setup.check_acquisition_ready(setup.CORPUS / 'main.jsonl', config)


def test_dirty_source_blocks_real_acquisition(tmp_path, cfg, monkeypatch):
    config = isolate_gate(monkeypatch, tmp_path, cfg)
    monkeypatch.setattr(setup, 'git_provenance', lambda: {'commit': 'unit-test', 'modified_tracked_files': 'M file.py'})
    with pytest.raises(ValueError, match='clean, committed'):
        setup.check_acquisition_ready(setup.CORPUS / 'development.jsonl', config)


def test_capability_cannot_be_just_a_smoke_ready_flag(tmp_path, cfg):
    cfg['joern_capability_file'] = str(tmp_path / 'receipt.json')
    write_json(tmp_path / 'receipt.json', {'ready': True, 'synthetic': False,
        'corpus_contract': setup.corpus_contract(), 'policy': setup.policy(cfg)})
    with pytest.raises(ValueError, match='complete successful'):
        setup.capability_valid(cfg)


def test_implementation_drift_rejected(tmp_path, monkeypatch):
    (tmp_path / 'rq1').mkdir()
    source = tmp_path / 'module.py'
    source.write_text('before')
    write_json(tmp_path / 'rq1/pipeline_contract.json', {'implementation_id': 'rq1-v5',
                                                       'files': {'module.py': file_digest(source)}})
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    monkeypatch.setattr(setup, 'CORPUS', tmp_path / 'rq1')
    setup.verify_implementation()
    source.write_text('after')
    with pytest.raises(ValueError, match='drift'):
        setup.verify_implementation()


def test_freeze_recomputes_all_assessments_and_is_exclusive(completed, cfg, monkeypatch):
    cfg['rq1_freeze_file'] = str(completed / 'frozen.json')
    cfg['rq1_token_audit_file'] = str(completed / 'audit.json')
    cfg['joern_capability_file'] = str(completed / 'capability.json')
    write_json(completed / 'audit.json', {'unit_test_fixture': True})
    write_json(completed / 'capability.json', {'unit_test_fixture': True})
    path = completed / 'config.json'
    write_json(path, cfg)
    monkeypatch.setattr(setup, 'check_acquisition_ready', lambda *a, **kw: cfg)
    setup.freeze(path, completed)
    frozen = json.loads((completed / 'frozen.json').read_text())
    assert frozen['primary_rule'] == 'repeat_0'
    assert {'query', 'slice'} == frozen['stage_environments'].keys()
    assert frozen['development_summary']['real_inference_complete']
    with pytest.raises(FileExistsError):
        setup.freeze(path, completed)


def test_partial_acquisition_is_pending_not_inadequate(tmp_path):
    status = setup.status('development', tmp_path)
    assert status['queries_recorded'] == 0 and status['slices_recorded'] == 0
    assert not status['real_inference_complete']
    assert 'inadequate' not in status


def test_changed_cpu_environment_requires_fresh_selector_conformance(tmp_path, cfg, monkeypatch):
    config = isolate_gate(monkeypatch, tmp_path, cfg)
    monkeypatch.setattr(setup, 'capability_valid', lambda cfg: {'environment': {'python': 'different'}})
    with pytest.raises(ValueError, match='CPU environment'):
        setup.check_acquisition_ready(setup.CORPUS / 'development.jsonl', config, phase='slice')
