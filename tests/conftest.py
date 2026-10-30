"""Synthetic protocol fixtures, confined to pytest temporary directories."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from evidence_experiment import locks
from evidence_experiment.schema import append_jsonl, digest, load_cases, run_specs, write_json
from rq1.setup import CORPUS


@pytest.fixture
def cases():
    return load_cases(CORPUS / 'development.jsonl')


@pytest.fixture
def cfg():
    return json.loads((CORPUS / 'config.example.json').read_text())


@pytest.fixture
def witnessed(tmp_path, cases):
    for c in cases:
        append_jsonl(tmp_path / 'witness_validation.jsonl', {
            'case_id': c.case_id, 'checks': {'compile': 'pass', 'trigger': 'pass', 'fixed': 'pass',
                                          'benign_behavior': 'pass'},
            'witness_plan_sha256': c.referent['witness_plan_sha256'],
            'source_sha256': {a: digest(s) for a, s in c.sources.items()}})
    return tmp_path


def rating(packet, decision='adequate', *, hours_ago=72):
    from evidence_experiment.review import packet_lines
    return {'review_id': packet['review_id'], 'assessor_id': 'codex_ai_assessor',
            'assessment_origin': 'AI-assisted; no independent human validation',
            'assessed_utc': (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
            'adequacy': decision, 'cited_lines': sorted(packet_lines(packet['code']))[:1],
            'relationships': ['Synthetic test explanation; no study judgement.'],
            'assumptions_used': [], 'missing_context': [], 'limitations': [],
            'explanation': 'Synthetic test record, never experimental evidence.'}


@pytest.fixture
def completed(witnessed, cases, cfg):
    """Schema-valid mocked acquisition; never called outside unit tests."""
    work = witnessed
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
    from evidence_experiment.review import build_queue, packet_index
    from rq1.assess import prepare
    build_queue(cases, work)
    prepare('development', work)
    packets, joins = packet_index(cases, work)
    for p in packets.values():
        append_jsonl(work / 'assessments.initial.jsonl', rating(p))
        append_jsonl(work / 'assessments.final.jsonl', rating(p, hours_ago=71))
    for spec in run_specs(cases):
        if spec['arm'] == 'U':
            append_jsonl(work / 'adjudications.jsonl', {'case_id': spec['case_id'],
                'review_id': joins[spec['run_id']], 'match': 'yes', 'reason': 'Unit test only.'})
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
