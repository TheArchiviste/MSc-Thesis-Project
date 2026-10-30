"""Regression tests for the RQ1 methodology corrections; simulations are test-only."""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from evidence_experiment.schema import append_jsonl, index_jsonl, load_cases, read_jsonl
from rq1 import calibration, judge, setup
from rq1.assessment_protocol import contract, public_packet, request_for
from rq1.conformance import GRAPH_QUERY, INTERPROCEDURAL_SOURCE, parse_graph

from .conftest import calibration_fixture, rating, replace_record, responses


def test_reference_r13_explicit_count_not_source_initialization():
    case = next(c for c in load_cases(setup.CORPUS / 'main.jsonl') if c.case_id == 'R13')
    extent = next(e for e in case.referent['elements'] if e['id'] == 'extent')
    assert extent['lines'] == [9]
    assert 'memcpy(data, source, 100*sizeof(char))' in case.source_for('U').splitlines()[8]
    assert 'source_initialization' not in {e['id'] for e in case.referent['elements']}
    assert case.referent['checked_quantities']['requested_access_bytes'] == 100


def test_correct_argument_binding_and_granular_facts():
    cases = {c.case_id: c for split in ('development', 'main') for c in load_cases(setup.CORPUS / f'{split}.jsonl')}
    binding = lambda cid: next(r for r in cases[cid].referent['relations'] if r['id'] == 'argument_binding')
    assert 'source object' in binding('R05')['explanation']
    assert 'index scalar' in binding('D02')['explanation']
    assert 'destination object' in binding('D01')['explanation']
    ids = {e['id'] for e in cases['D03'].referent['elements']}
    assert {'string_definition', 'source_initialization', 'alias_selection', 'caller_argument', 'callee_parameter'} <= ids


def test_r05_line_hits_can_be_indistinguishable():
    from evidence_experiment.review import numbered_view
    from llmxcpg.slicing.reconstruction import context_lines
    c = next(c for c in load_cases(setup.CORPUS / 'main.jsonl') if c.case_id == 'R05')
    selected = [6, 7, 20]
    assert numbered_view(c.source_for('U'), context_lines(c.source_for('U'), selected)) == numbered_view(c.source_for('F'), context_lines(c.source_for('F'), selected))
    assert c.referent['checked_quantities']['capacity_bytes'] == 50


def test_calibration_bank_balanced_dev_only_and_identical_negatives():
    packets, key = calibration.bank()
    assert len(packets) == len(key) == 12
    assert Counter(r['expected'] for r in key) == {'adequate': 6, 'inadequate': 6}
    assert {r['case_id'] for r in key} == {'D01', 'D02', 'D03'}
    assert Counter(r['kind'] for r in key) == {k: 3 for k in ('complete_U', 'complete_F', 'reduced_sufficient_U', 'indistinguishable_incomplete')}
    for packet in packets.values():
        req = request_for(packet, pass_id='calibration')
        assert len(req['messages']) == 2 and judge.validate_request(req) == packet
        task = json.loads(req['messages'][1]['content'])['task']
        assert set(task) == {'review_id', 'code', 'claim', 'assessment_contract'}
        assert not {'case_id', 'arm', 'source_reason', 'expected', 'witnesses'} & task.keys()


def test_request_rejects_hidden_oracle_even_if_rehashed():
    packet = public_packet('Does this justify a flaw?', 'L1: int a;')
    packet['answer_key'] = 'hidden'
    req = request_for(packet)
    with pytest.raises(ValueError, match='Only the public'):
        judge.validate_request(req)


def test_calibration_is_not_a_ready_flag(cfg, tmp_path):
    path = tmp_path / 'calibration/acceptance.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'accepted': True, 'n': 12, 'assessment_contract_sha256': contract()['contract_sha256'], 'corpus_contract': setup.corpus_contract()}))
    with pytest.raises(ValueError, match='incomplete'):
        calibration.require_calibration(cfg)


def test_complete_calibration_receipt_revalidates_raw_responses(witnessed, cfg):
    receipt = calibration_fixture(witnessed, cfg)
    assert receipt['accepted'] and calibration.require_calibration(cfg)['n'] == 12
    root = witnessed.parent / 'calibration'
    with (root / 'responses.jsonl').open('a') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='provenance files changed'):
        calibration.require_calibration(cfg)


def test_all_rejecting_assessor_fails_calibration_screen(witnessed, cfg):
    from evidence_experiment.schema import write_json
    config = witnessed.parent / 'config.json'; write_json(config, cfg)
    root = calibration.prepare(config)
    packets = index_jsonl(root / 'public/packets.jsonl', 'review_id')
    responses(root / 'public/requests.jsonl', root / 'responses.jsonl', root / 'assessments.initial.jsonl',
              {rid: 'inadequate' for rid in packets})
    for rid, packet in packets.items():
        append_jsonl(root / 'source_audit.jsonl', {'review_id': rid, 'source_auditor': 'codex_source_auditor',
            'audited_utc': datetime.now(UTC).isoformat(), 'source_proof_supported': 'yes',
            'cited_lines': rating(packet)['cited_lines'], 'reason': 'Unit schema fixture.'})
    result = calibration.evaluate(root)
    assert not result['accepted']
    assert sum(r['label_correct'] for r in result['records']) == 6
    with pytest.raises(ValueError, match='Calibration failed'):
        calibration.accept(config)
    assert not (root / 'acceptance.json').exists()


def test_missing_source_proof_blocks_calibration(witnessed, cfg):
    calibration_fixture(witnessed, cfg)
    path = witnessed.parent / 'calibration/source_audit.jsonl'
    row = read_jsonl(path)[0]
    replace_record(path, 'review_id', row['review_id'], source_proof_supported='uncertain')
    with pytest.raises(ValueError, match='changed after acceptance'):
        calibration.require_calibration(cfg)


def test_cpu_acquisition_cannot_skip_calibration(cfg, monkeypatch, tmp_path):
    for name in ('verify_corpus', 'verify_implementation'):
        monkeypatch.setattr(setup, name, dict)
    for name in ('token_audit_valid', 'capability_valid'):
        monkeypatch.setattr(setup, name, lambda cfg: {})
    from evidence_experiment.schema import write_json
    config = tmp_path / 'config.json'; write_json(config, cfg)
    with pytest.raises(FileNotFoundError):
        setup.check_acquisition_ready(setup.CORPUS / 'development.jsonl', config, phase='query')


def test_graph_marker_mapping_and_actual_query_shape():
    assert 'RQ1_GRAPH=' in GRAPH_QUERY and 'fixture_entry' in INTERPROCEDURAL_SOURCE
    source = 'void case_sink(int n){}\nvoid case_entry(){\ncase_sink(data);\n}\n'
    assert parse_graph('RQ1_GRAPH=1,1,1,1|3\n', source)['caller_lines'] == [3]
    for out in ('', 'RQ1_GRAPH=1,1,1,0|3', 'RQ1_GRAPH=1,1,1,1|99', 'RQ1_GRAPH=1,1,1,1|3\nRQ1_GRAPH=1,1,1,1|3'):
        with pytest.raises(ValueError):
            parse_graph(out, source)


def test_future_delayed_request_does_not_contact_service(tmp_path, monkeypatch):
    import requests

    from evidence_experiment.schema import write_json
    packet = public_packet('Does this justify a flaw?', 'L1: int a;')
    req = tmp_path / 'requests.jsonl'
    judge.export({packet['review_id']: packet}, req, pass_id='delayed', not_before={packet['review_id']: (datetime.now(UTC)+timedelta(hours=1)).isoformat()})
    profile = tmp_path / 'profile.json'
    write_json(profile, {'provider': 'test-only', 'model': 'test-model', 'temperature': 0, 'max_tokens': 3000, 'chat_completions_url': 'http://never-contact.invalid'})
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: pytest.fail('Early request contacted service'))
    with pytest.raises(ValueError, match='future'):
        judge.execute(req, profile, tmp_path / 'responses.jsonl')


def test_nonterminal_response_retained_without_retry_or_credentials(tmp_path, monkeypatch):
    import requests

    from evidence_experiment.schema import write_json
    packet = public_packet('Does this justify a flaw?', 'L1: int a;')
    req = tmp_path / 'requests.jsonl'; judge.export({packet['review_id']: packet}, req)
    profile = tmp_path / 'profile.json'
    write_json(profile, {'provider': 'test-only', 'model': 'test-model', 'temperature': 0, 'max_tokens': 10,
                         'chat_completions_url': 'http://mock.invalid', 'api_key_env': 'RQ1_UNIT_KEY'})
    monkeypatch.setenv('RQ1_UNIT_KEY', 'DO-NOT-PERSIST-TEST-SECRET')
    calls = []
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'model': 'test-model', 'choices': [{'message': {'content': '{truncated'}, 'finish_reason': 'length'}]}
    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(requests, 'post', post)
    out = tmp_path / 'responses.jsonl'
    with pytest.raises(RuntimeError, match='Truncated'):
        judge.execute(req, profile, out)
    assert len(calls) == 1 and len(calls[0]['json']['messages']) == 2
    assert read_jsonl(out)[0]['content'] == '{truncated'
    assert 'DO-NOT-PERSIST' not in out.read_text()
    with pytest.raises(ValueError, match='truncated'):
        judge.execute(req, profile, out)
    assert len(calls) == 1
