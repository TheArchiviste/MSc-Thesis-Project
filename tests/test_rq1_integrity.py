"""Regression checks for source identity and real-stage provenance."""
from __future__ import annotations

import json

import pytest

from evidence_experiment import locks
from evidence_experiment.schema import append_jsonl, load_cases, run_specs, write_json
from rq1.setup import CORPUS, load_config, token_audit_valid, verify_corpus, verify_implementation

from .conftest import replace_record


def test_corpus_sources_maps_abi_and_disjoint_blocks():
    assert verify_corpus() == {'development': 3, 'main': 12}
    dev, main = (load_cases(CORPUS / f'{s}.jsonl') for s in ('development', 'main'))
    assert not {c.cluster_id for c in dev} & {c.cluster_id for c in main}
    assert len({c.cluster_id for c in main}) == 12
    assert all('case_entry' in c.sources['U'] and 'CWE' not in c.sources['U'] for c in dev + main)


def test_implementation_contract():
    assert verify_implementation()['implementation_id'] == 'rq1-v3'


def test_config_legacy_or_changed_design_rejected(tmp_path, cfg):
    path = tmp_path / 'cfg.json'
    write_json(path, cfg)
    assert load_config(path) == cfg
    for changes in ({'detector_model': 'unused'}, {'pipeline_commit': 'legacy'}, {'query_temperature': .2}, {'joern_digest': 'placeholder'}):
        write_json(path, {**cfg, **changes})
        with pytest.raises(ValueError):
            load_config(path)


def test_no_repeats_or_extra_arms(tmp_path, cases):
    with pytest.raises(ValueError, match='one primary'):
        run_specs(cases, 3)
    path = tmp_path / 'm.jsonl'
    row = json.loads((CORPUS / 'development.jsonl').read_text().splitlines()[0])
    row['sources']['TM'] = 'anything.c'
    append_jsonl(path, row)
    with pytest.raises(ValueError, match='exactly U and F'):
        load_cases(path)


@pytest.mark.parametrize('name', ['queries.jsonl', 'slices.jsonl', 'query_sessions.jsonl', 'stage_receipts.json', 'analysis.json'])
def test_orphan_outputs_cannot_get_new_lock(witnessed, cases, cfg, name):
    (witnessed / name).write_text('{}\n')
    with pytest.raises(ValueError, match='Orphan'):
        locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases)


def test_full_environment_and_stage_separation(witnessed, cases, cfg, monkeypatch):
    base = {'python': '3.11.18', 'packages': {'jinja2': '3.1.6'}}
    monkeypatch.setattr(locks, 'environment', lambda: base)
    locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases)
    monkeypatch.setattr(locks, 'environment', lambda: {**base, 'python': '3.11.19'})
    with pytest.raises(ValueError, match='environment changed'):
        locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases)
    locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases, phase='slice')
    monkeypatch.setattr(locks, 'environment', lambda: {**base, 'packages': {'jinja2': '3.1.7'}})
    with pytest.raises(ValueError):
        locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases)


def test_source_policy_and_witness_lock(witnessed, cases, cfg):
    locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases)
    with pytest.raises(ValueError, match='changed'):
        locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', {**cfg, 'query_max_context': 4096}, cases)
    replace_record(witnessed / 'witness_validation.jsonl', 'case_id', cases[0].case_id, checks={})
    with pytest.raises(ValueError, match='Witness'):
        locks.lock_inputs(witnessed, CORPUS / 'development.jsonl', cfg, cases)


def test_concurrent_run_rejected(tmp_path):
    with locks.work_lock(tmp_path), pytest.raises(ValueError, match='Another process'), locks.work_lock(tmp_path):
        pass


def test_stage_receipt_detects_edits(completed):
    locks.check_stage_receipts(completed)
    with (completed / 'queries.jsonl').open('a') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='Completed output changed'):
        locks.check_stage_receipts(completed)


@pytest.mark.parametrize('change', [{'synthetic': True}, {'effective_dtype': 'unknown'}, {'query_revision': 'changed'}, {'runtime': {}}, {'effective_seed': 42}])
def test_real_q_provenance_required(completed, cases, change):
    replace_record(completed / 'query_sessions.jsonl', 'session_id', 'unit-test-only', **change)
    with pytest.raises(ValueError, match='provenance'):
        locks.validate_terminal_records(completed, 'query', cases)


def test_unknown_status_and_incomplete_ids_rejected(completed, cases):
    rid = run_specs(cases)[0]['run_id']
    replace_record(completed / 'slices.jsonl', 'run_id', rid, status='invented')
    with pytest.raises(ValueError, match='Unknown'):
        locks.validate_terminal_records(completed, 'slice', cases)
    (completed / 'queries.jsonl').unlink()
    with pytest.raises(ValueError, match='Incomplete'):
        locks.validate_terminal_records(completed, 'query', cases)


def test_stale_token_audit_is_rejected(tmp_path, cfg, monkeypatch):
    from rq1 import setup
    cfg['rq1_token_audit_file'] = str(tmp_path / 'audit.json')
    write_json(tmp_path / 'audit.json', {'corpus_contract': {}, 'policy': locks.policy(cfg)})
    monkeypatch.setattr(setup, 'corpus_contract', lambda: {'expected': 'current'})
    with pytest.raises(ValueError, match='stale'):
        token_audit_valid(cfg)
