"""Synthetic protocol fixtures, confined to pytest temporary directories."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from evidence_experiment import locks
from evidence_experiment.schema import (
    append_jsonl,
    digest,
    index_jsonl,
    load_cases,
    read_jsonl,
    run_specs,
    write_json,
)
from rq1.setup import CORPUS


@pytest.fixture
def cases():
    return load_cases(CORPUS / 'development.jsonl')


@pytest.fixture
def cfg(tmp_path):
    result = json.loads((CORPUS / 'config.example.json').read_text())
    result['rq1_calibration_file'] = str(tmp_path / 'calibration/acceptance.json')
    return result


@pytest.fixture
def witnessed(tmp_path, cases):
    tmp_path = tmp_path / 'development'
    for c in cases:
        append_jsonl(tmp_path / 'witness_validation.jsonl', {
            'case_id': c.case_id, 'checks': {'compile': 'pass', 'trigger': 'pass', 'fixed': 'pass',
                                          'benign_behavior': 'pass'},
            'witness_plan_sha256': c.referent['witness_plan_sha256'],
            'source_sha256': {a: digest(s) for a, s in c.sources.items()}})
    return tmp_path


IDENTITY = {'provider': 'unit-test-fixture', 'requested_model': 'synthetic-test-model',
            'reported_model': 'synthetic-test-model', 'revision_note': 'test-only',
            'route': 'stateless_chat_completions', 'sampling': {'temperature': 0., 'max_tokens': 3072}}


def rating(packet, decision='adequate', *, hours_ago=72):
    from evidence_experiment.review import packet_lines
    from rq1.assessment_protocol import ORIGIN, contract
    cited = sorted(packet_lines(packet['code']))[:1]
    return {'review_id': packet['review_id'], 'assessor_id': 'calibrated_ai_assessor',
            'assessment_origin': ORIGIN, 'assessment_context': 'excerpt_only_stateless',
            'assessment_contract_sha256': contract()['contract_sha256'], 'assessor_identity': IDENTITY,
            'assessed_utc': (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
            'adequacy': decision, 'cited_lines': cited,
            'premises': [{'category': c, 'statement': 'Unit fixture, not semantic evidence.',
                          'cited_lines': cited, 'assumption_ids': []}
                         for c in ('capacity', 'extent', 'binding', 'violation')],
            'relationships': ['Synthetic test explanation; no study judgement.'],
            'assumptions_used': [], 'missing_context': [], 'limitations': ['Test fixture only.'],
            'explanation': 'Synthetic test record, never experimental evidence.'}


def responses(request_path, response_path, output, decisions=None, *, hours_ago=72, identity=None):
    from rq1.judge import import_responses, validate_request
    for req in read_jsonl(request_path):
        packet = validate_request(req)
        grade = rating(packet, (decisions or {}).get(packet['review_id'], 'adequate'), hours_ago=hours_ago)
        append_jsonl(response_path, {**{k: req[k] for k in ('request_id', 'review_id', 'request_sha256', 'pass_id')},
            'assessed_utc': grade['assessed_utc'], 'assessor_identity': identity or IDENTITY,
            'content': json.dumps(grade), 'finish_reason': 'stop', 'synthetic': False,
            'test_fixture_only': True})
    response_path.touch(exist_ok=True)
    import_responses(request_path, response_path, output)
    return output


def calibration_fixture(work, cfg):
    from rq1.calibration import accept, prepare
    config = work.parent / 'config.json'
    write_json(config, cfg)
    root = prepare(config)
    key = read_jsonl(root / 'private/answer_key.jsonl')
    responses(root / 'public/requests.jsonl', root / 'responses.jsonl', root / 'assessments.initial.jsonl',
              {r['review_id']: r['expected'] for r in key})
    packets = index_jsonl(root / 'public/packets.jsonl', 'review_id')
    for r in key:
        append_jsonl(root / 'source_audit.jsonl', {'review_id': r['review_id'],
            'source_auditor': 'codex_source_auditor',
            'audited_utc': (datetime.now(UTC) - timedelta(hours=71)).isoformat(),
            'source_proof_supported': 'yes', 'cited_lines': rating(packets[r['review_id']])['cited_lines'],
            'reason': 'Schema-only unit fixture; not a real calibration judgment.'})
    return accept(config)


def issue_test_grades(work, cases):
    from evidence_experiment.review import build_queue, packet_index
    from rq1.assess import prepare
    from rq1.source_audit import template
    build_queue(cases, work)
    prepare('development', work)
    responses(work / 'assessment_requests.initial.jsonl', work / 'responses.initial.jsonl',
              work / 'assessments.initial.jsonl')
    packets, joins = packet_index(cases, work)
    for case in cases:
        spec = next(s for s in run_specs([case]) if s['arm'] == 'U')
        if spec['run_id'] not in joins:
            continue
        p = packets[joins[spec['run_id']]]
        row = template(case, p)
        row.update(match='yes', reason='Unit test only.', audited_utc=datetime.now(UTC).isoformat())
        for r in row['relation_checks']:
            r.update(support='supported', cited_lines=rating(p)['cited_lines'], explanation='Unit test schema fixture.')
        append_jsonl(work / 'adjudications.jsonl', row)
    (work / 'adjudications.jsonl').touch(exist_ok=True)


@pytest.fixture
def completed(witnessed, cases, cfg):
    """Schema-valid mocked acquisition; never called outside unit tests."""
    work = witnessed
    calibration_fixture(work, cfg)
    locks.lock_inputs(work, CORPUS / 'development.jsonl', cfg, cases, phase='query')
    locks.lock_inputs(work, CORPUS / 'development.jsonl', cfg, cases, phase='slice')
    append_jsonl(work / 'query_sessions.jsonl', {'session_id': 'unit-test-only', 'synthetic': False,
        'model_load_seconds': .1, 'effective_dtype': 'torch.bfloat16', 'effective_seed': 0,
        'effective_max_context': cfg['query_max_context'], 'query_model': cfg['query_model'],
        'query_revision': cfg['query_revision'], 'runtime': locks.environment(),
        'generation_allowance': 2048, 'temperature': 0., 'top_p': 1.})
    from llmxcpg.slicing.reconstruction import reconstruct_code_from_lines
    by_case = {c.case_id: c for c in cases}
    for spec in run_specs(cases):
        source = by_case[spec['case_id']].source_for(spec['arm'])
        coords = list(range(1, len(source.splitlines()) + 1))
        append_jsonl(work / 'queries.jsonl', {'run_id': spec['run_id'], 'status': 'ok',
            'synthetic': False, 'query_engine': 'vllm', 'session_id': 'unit-test-only',
            'prompt_tokens': 100, 'queries': ['val execution_path = sink.reachableByFlows(source).l']})
        append_jsonl(work / 'slices.jsonl', {'run_id': spec['run_id'], 'status': 'ok',
            'slice_lines': coords, 'rendered_lines': coords,
            'slice_code': reconstruct_code_from_lines(source, coords)})
    for stage in ('query', 'slice'):
        locks.write_stage_receipt(work, stage, cases)
    issue_test_grades(work, cases)
    return work


def replace_record(path: Path, key, value, **changes):
    from evidence_experiment.schema import read_jsonl
    rows = read_jsonl(path)
    for row in rows:
        if row[key] == value:
            row.update(changes)
    path.unlink()
    for row in rows:
        append_jsonl(path, row)


def rewrite_json(path, **changes):
    data = json.loads(path.read_text())
    data.update(changes)
    write_json(path, data)
