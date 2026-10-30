"""V3 request fidelity, bounded provider behaviour and independent acquisition seals."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import pytest

from evidence_experiment import locks
from evidence_experiment.review import numbered_view, packet_lines
from evidence_experiment.schema import load_cases, read_jsonl, write_json
from llmxcpg.slicing.reconstruction import context_lines
from rq1 import calibration, judge, providers, setup
from rq1.assessment_protocol import RUBRIC, decode_schema, response_schema
from rq1.sealing import require_release, verify_seal

from .conftest import rating


def profile():
    return json.loads((setup.CORPUS / 'assessor.example.json').read_text())


def one_request(tmp_path):
    packets, _ = calibration.bank()
    packet = next(iter(packets.values()))
    path = tmp_path / 'requests.jsonl'
    judge.export({packet['review_id']: packet}, path, pass_id='calibration')
    return packet, path, read_jsonl(path)[0]


def content(packet):
    row = rating(packet)
    return json.dumps({k: row[k] for k in response_schema(packet['review_id'])['required']})


def test_export_preserves_proof_before_verdict_order_and_hashes_it(tmp_path):
    packet, path, req = one_request(tmp_path)
    assert list(req['decode_schema']['properties'])[-1] == 'adequacy'
    assert judge.validate_request(req) == packet
    assert packet['code'] in req['messages'][1]['content']
    assert '\\nL' not in req['messages'][1]['content']
    assert sum(m['content'].count(RUBRIC) for m in req['messages']) == 1
    assert 'response_schema' not in req['messages'][1]['content']
    reordered = deepcopy(req)
    reordered['decode_schema'] = json.loads(json.dumps(req['decode_schema'], sort_keys=True))
    with pytest.raises(ValueError, match='schema order'):
        judge.validate_request(reordered)
    assert path.read_text().index('"premises"') < path.read_text().index('"adequacy"')


def test_portable_grammar_keeps_fields_but_leaves_conditions_to_strict_validation():
    schema = decode_schema('id')
    wire = json.dumps(schema)
    assert not any(f'"{key}"' in wire for key in ('allOf', 'if', 'then', 'uniqueItems', 'const'))
    assert schema['required'] == response_schema('id')['required']
    assert schema['additionalProperties'] is False
    assert schema['properties']['review_id']['enum'] == ['id']


def test_realistic_positives_and_explicit_post_render_stress_controls():
    packets, key = calibration.bank()
    assert Counter(r['cohort'] for r in key) == {'development': 12, 'assessor_holdout': 8}
    cases = {c.case_id: c for split in ('development', 'assessor_holdout')
             for c in load_cases(setup.CORPUS / f'{split}.jsonl')}
    main_blocks = {c.cluster_id for c in load_cases(setup.CORPUS / 'main.jsonl')}
    assert not main_blocks & {c.cluster_id for c in cases.values()}
    for row in key:
        c = cases[row['case_id']]
        if row['kind'] == 'reduced_sufficient_U':
            selected = sorted({n for e in c.referent['elements'] if e['essential'] for n in e['lines']})
            assert packets[row['review_id']]['code'] == numbered_view(c.source_for('U'), context_lines(c.source_for('U'), selected))
            assert len(packet_lines(packets[row['review_id']]['code'])) < len(c.source_for('U').splitlines())
        if row['kind'] == 'indistinguishable_incomplete':
            coords = sorted(packet_lines(packets[row['review_id']]['code']))
            assert numbered_view(c.source_for('U'), coords) == numbered_view(c.source_for('F'), coords)
            assert 'stress_control' in row['construction']
    c = cases['D02']
    assert next(e for e in c.referent['elements'] if e['id'] == 'input_acquisition')['lines'] == [34]
    assert 13 in context_lines(c.source_for('U'), [15])
    reduced = next(r for r in key if r['case_id'] == 'D02' and r['kind'] == 'reduced_sufficient_U')
    assert {2, 30, 33, 34} <= packet_lines(packets[reduced['review_id']]['code'])
    loop = cases['R17']
    assert next(e for e in loop.referent['elements'] if e['id'] == 'extent')['lines'] == [10]
    assert next(e for e in loop.referent['elements'] if e['id'] == 'loop_index_type')['lines'] == [6]


def test_responses_wire_has_no_conversation_tools_or_temperature(tmp_path):
    _, _, req = one_request(tmp_path)
    url, body = providers.wire_request(req, profile())
    assert url == 'https://api.openai.com/v1/responses'
    assert body['input'] == req['messages'] and body['store'] is False
    assert body['reasoning'] == {'effort': 'high'}
    assert body['max_output_tokens'] == 25000
    assert not {'tools', 'previous_response_id', 'conversation', 'temperature', 'max_tokens'} & body.keys()
    assert list(body['text']['format']['schema']['properties'])[-1] == 'adequacy'


def test_vllm_wire_supplies_guided_json(tmp_path):
    _, _, req = one_request(tmp_path)
    p = {'provider': 'test', 'model': 'test-model', 'temperature': 0., 'max_tokens': 3072,
         'chat_completions_url': 'http://127.0.0.1:8001/v1/chat/completions'}
    _, body = providers.wire_request(req, p)
    assert body['guided_json'] == req['decode_schema']


def test_real_wire_adapter_records_usage_and_never_saves_key(tmp_path, monkeypatch):
    packet, reqs, req = one_request(tmp_path)
    p = tmp_path / 'profile.json'
    write_json(p, profile())
    monkeypatch.setenv('OPENAI_API_KEY', 'private-test-key')
    calls = []
    envelope = {'id': 'unit-only', 'model': profile()['model'], 'status': 'completed',
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': content(packet)}]}],
        'usage': {'input_tokens': 50, 'output_tokens': 100, 'output_tokens_details': {'reasoning_tokens': 40}}}
    def post(url, **kwargs):
        calls.append((url, kwargs))
        assert kwargs['headers']['Authorization'] == 'Bearer private-test-key'
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: envelope)
    monkeypatch.setattr('requests.post', post)
    dest = tmp_path / 'responses.jsonl'
    judge.execute(reqs, p, dest)
    judge.import_responses(reqs, dest, tmp_path / 'grades.jsonl')
    row = read_jsonl(dest)[0]
    assert len(calls) == 1 and row['request_sha256'] == req['request_sha256']
    assert row['assessor_identity']['route'] == 'stateless_responses'
    assert row['response_metadata']['raw'] == envelope
    assert 'private-test-key' not in dest.read_text()


@pytest.mark.parametrize('envelope', [
    {'status': 'incomplete', 'output': [], 'incomplete_details': {'reason': 'max_output_tokens'}},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'test'}]}]},
])
def test_refusal_or_truncation_is_saved_without_retry(tmp_path, monkeypatch, envelope):
    _, reqs, _ = one_request(tmp_path)
    p = tmp_path / 'profile.json'; write_json(p, profile())
    monkeypatch.setenv('OPENAI_API_KEY', 'private-test-key')
    calls = []
    def post(*a, **kw):
        calls.append(1)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: envelope)
    monkeypatch.setattr('requests.post', post)
    out = tmp_path / 'responses.jsonl'
    with pytest.raises(RuntimeError, match='no automatic'):
        judge.execute(reqs, p, out)
    assert len(calls) == 1 and read_jsonl(out)[0]['finish_reason'] in {'refusal', 'incomplete'}
    with pytest.raises(ValueError):
        judge.import_responses(reqs, out, tmp_path / 'grades.jsonl')
    assert not (tmp_path / 'grades.jsonl').exists()


def test_missing_key_and_legacy_reasoning_parameters_fail_before_inference(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ValueError, match='not set'):
        providers.headers(profile())
    for extra in ({'temperature': 0.}, {'max_tokens': 3072}, {'max_output_tokens': 3072}):
        with pytest.raises(ValueError):
            providers.validate_profile({**profile(), **extra})


def test_calibration_receipt_is_not_an_acquisition_dependency(completed, cases, cfg):
    first = locks.acquisition_fingerprint(setup.CORPUS / 'development.jsonl', cfg, cases, 1, completed)
    acceptance = completed.parent / 'calibration/acceptance.json'
    acceptance.write_text(acceptance.read_text() + '\n')
    second = locks.acquisition_fingerprint(setup.CORPUS / 'development.jsonl', cfg, cases, 1, completed)
    assert first == second
    verify_seal(completed)
    with pytest.raises(ValueError, match='release'):
        require_release(completed)


def test_judging_change_preserves_acquisition_but_invalidates_release(completed, monkeypatch):
    old = setup.corpus_contract()
    actual = setup.assessment_code_contract()
    monkeypatch.setattr(setup, 'assessment_code_contract', lambda: {k:'changed' for k in actual})
    assert setup.corpus_contract() == old
    verify_seal(completed)
    with pytest.raises(ValueError, match='release'):
        require_release(completed)


def test_seal_detects_content_edits(completed):
    with (completed / 'queries.jsonl').open('a') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='Sealed acquisition changed'):
        verify_seal(completed)


def test_visibility_can_run_sealed_without_a_grade(completed):
    from rq1.visibility import compute
    (completed / 'assessment_lock.json').unlink()
    receipt = compute(load_cases(setup.CORPUS / 'development.jsonl'), completed, sealed=True)
    assert receipt['semantic_judgments'] == 0 and receipt['sealed']
    text = (completed / 'structural_visibility/relation_prerequisites.csv').read_text()
    assert 'not_assessed' in text and 'supported' not in text
    with pytest.raises(FileNotFoundError):
        compute(load_cases(setup.CORPUS / 'development.jsonl'), completed)


def test_unreleased_packets_are_blocked(completed, cases):
    from evidence_experiment.review import build_queue
    (completed / 'assessment_lock.json').unlink()
    with pytest.raises(FileNotFoundError):
        build_queue(cases, completed)


def test_native_and_python_logs_do_not_escape(tmp_path):
    log = tmp_path / 'sealed.log'
    code = ('import os\nfrom pathlib import Path\nfrom rq1.sealing import private_log\n'
            f'with private_log(Path({str(log)!r})):\n'
            ' print("private-example")\n os.write(2,b"private-native\\n")\nprint("safe-status")\n')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert result.stdout == 'safe-status\n' and result.stderr == ''
    assert 'private-example' in log.read_text() and 'private-native' in log.read_text()


def test_sealed_collection_requires_its_own_freeze_and_vm_receipt(tmp_path, cfg, monkeypatch):
    for name in ('verify_corpus', 'verify_implementation'):
        monkeypatch.setattr(setup, name, dict)
    monkeypatch.setattr(setup, 'token_audit_valid', lambda cfg: {})
    monkeypatch.setattr(setup, 'capability_valid', lambda cfg: {'environment': setup.environment()})
    monkeypatch.setattr(setup, 'git_provenance', lambda: {'commit': 'unit-only', 'modified_tracked_files': ''})
    called = []
    monkeypatch.setattr(setup, 'require_acquisition_freeze', lambda cfg: called.append('acquisition-freeze'))
    def forbidden(cfg):
        raise AssertionError('Sealed collection must not read calibration')
    monkeypatch.setattr(calibration, 'require_calibration', forbidden)
    config = tmp_path / 'config.json'; write_json(config, cfg)
    with pytest.raises(FileNotFoundError):
        setup.check_acquisition_ready(setup.CORPUS / 'development.jsonl', config, phase='query', sealed=True)
    write_json(tmp_path / 'q-vm-inspection.json', {'technical_ready': True,
        'environment': setup.environment(), 'core_contract': setup.corpus_contract()})
    setup.check_acquisition_ready(setup.CORPUS / 'development.jsonl', config, phase='query', sealed=True)
    assert called == ['acquisition-freeze', 'acquisition-freeze']
    with pytest.raises(AssertionError, match='must not read calibration'):
        setup.check_acquisition_ready(setup.CORPUS / 'development.jsonl', config, phase='query')


def test_q_disk_check_needs_every_pinned_weight_shard(tmp_path, cfg):
    snapshot = tmp_path / 'hub/models--QCRI--LLMxCPG-Q/snapshots' / cfg['query_revision']
    snapshot.mkdir(parents=True)
    write_json(snapshot / 'model.safetensors.index.json', {'weight_map': {'x':'one', 'y':'two'}})
    (snapshot / 'one').write_bytes(b'unit-only')
    assert not setup.q_weights_cached(tmp_path, cfg)
    (snapshot / 'two').write_bytes(b'unit-only')
    assert setup.q_weights_cached(tmp_path, cfg)


def test_verdict_first_or_missing_field_cannot_be_repaired(tmp_path):
    from .conftest import responses
    packet, reqs, _ = one_request(tmp_path)
    raw, grades = tmp_path / 'raw.jsonl', tmp_path / 'grades.jsonl'
    responses(reqs, raw, grades)
    rows = read_jsonl(raw)
    parsed = json.loads(rows[0]['content'])
    parsed = {'adequacy': parsed['adequacy'], **{k:v for k,v in parsed.items() if k != 'adequacy'}}
    rows[0]['content'] = json.dumps(parsed)
    raw.write_text(json.dumps(rows[0]) + '\n')
    with pytest.raises(ValueError, match='before the final verdict'):
        judge.validated_grades(reqs, raw)
    parsed.pop('limitations')
    rows[0]['content'] = json.dumps(parsed)
    raw.write_text(json.dumps(rows[0]) + '\n')
    with pytest.raises(ValueError, match='required response fields'):
        judge.validated_grades(reqs, raw)
    assert packet['review_id'] == rows[0]['review_id']


def test_api_inspection_has_no_network_or_key_requirement(witnessed, cfg, monkeypatch):
    from ops.rq1_api_calibration import inspect
    def forbidden(*args, **kwargs):
        raise AssertionError('No inference or model listing during offline inspection')
    monkeypatch.setattr('requests.get', forbidden)
    monkeypatch.setattr('requests.post', forbidden)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    config = witnessed.parent / 'config.json'; write_json(config, cfg)
    _, result = inspect(config)
    assert result['inference_requests'] == 0 and not result['api_access_checked']
    assert result['requests'] == 20 and result['planning_upper_estimate_usd'] < 30
    assert not result['api_key_present']


def test_read_only_access_does_not_generate_or_save_credentials(witnessed, cfg, monkeypatch):
    from ops.rq1_api_calibration import inspect
    monkeypatch.setenv('OPENAI_API_KEY', 'private-access-key')
    calls = []
    def get(url, **kw):
        calls.append(url)
        assert kw['headers']['Authorization'] == 'Bearer private-access-key'
        return SimpleNamespace(status_code=200, json=lambda: {'id': profile()['model']})
    monkeypatch.setattr('requests.get', get)
    monkeypatch.setattr('requests.post', lambda *a, **kw: pytest.fail('Access must not generate'))
    config = witnessed.parent / 'config.json'; write_json(config, cfg)
    root, result = inspect(config, check_access=True)
    assert result['model_listed'] and result['inference_requests'] == 0 and len(calls) == 1
    assert 'private-access-key' not in (root / 'api-inspection.json').read_text()


def test_failed_api_attempt_exports_raw_evidence_but_not_extra_files(witnessed, cfg, monkeypatch):
    import zipfile

    from ops import rq1_api_calibration as session
    config = witnessed.parent / 'config.json'; write_json(config, cfg)
    root, _ = session.inspect(config)
    write_json(root / 'api-access.json', {'model_listed': True, 'inference_requests': 0,
        'profile_sha256': locks.file_digest(root / 'assessor.json')})
    (root / '.env').write_text('extra-local-secret')
    monkeypatch.setenv('OPENAI_API_KEY', 'private-test-key')
    monkeypatch.setattr(session, 'git_provenance', lambda: {'commit': 'unit-only', 'modified_tracked_files': ''})
    calls = []
    def post(*a, **kw):
        calls.append(1)
        return SimpleNamespace(raise_for_status=lambda: None,
            json=lambda: {'status': 'incomplete', 'output': []})
    monkeypatch.setattr('requests.post', post)
    exports = witnessed.parent / 'exports'
    assert not session.run(config, exports)
    assert len(calls) == 1
    archive = next(exports.glob('*.zip'))
    with zipfile.ZipFile(archive) as zipped:
        assert 'calibration/responses.jsonl' in zipped.namelist()
        assert 'calibration/export-manifest.json' in zipped.namelist()
        assert not any('.env' in name for name in zipped.namelist())
        assert not any(secret.encode() in zipped.read(name) for name in zipped.namelist()
                       for secret in ('private-test-key', 'extra-local-secret'))
    with pytest.raises(ValueError, match='prior acquisition'):
        session.run(config, exports)
    assert len(calls) == 1
