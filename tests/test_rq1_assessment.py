"""Honest assessment completeness, denominators and delayed consistency."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from evidence_experiment.analysis import analyze
from evidence_experiment.locks import write_stage_receipt
from evidence_experiment.review import assessments, packet_index, validate_assessment
from evidence_experiment.schema import append_jsonl, read_jsonl, run_specs
from rq1.assess import consistency, reassessment_plan

from .conftest import rating, replace_record


def test_report_separates_u_f_and_provisional_delayed_work(completed, cases):
    report = analyze(cases, completed)
    assert report['scope'] == 'rq1_only' and report['completion'] == 'provisional'
    assert report['rq1']['n'] == 3
    assert sum(report['rq1']['adequacy'].values()) == 3
    assert report['rq1']['adequacy']['adequate'] == 3
    assert report['initial_fixed_control_check']['shown_F'] == 3
    assert report['initial_fixed_control_check']['initial_false_adequate'] == 3
    assert 'provisional' in (completed / 'rq1_report.md').read_text()
    assert len((completed / 'rq1_cases.csv').read_text().splitlines()) == 7
    assert not {'rq2', 'rq3', 'classifier', 'threshold'} & report.keys()


@pytest.mark.parametrize('changes', [
    {'assessor_id': 'pretend_second_human'}, {'assessment_origin': 'independent human'},
    {'assessed_utc': None}, {'assessed_utc': '2020-01-01T00:00:00'},
    {'assessed_utc': '2099-01-01T00:00:00+00:00'}, {'explanation': ''},
    {'cited_lines': [999]}, {'relationships': []}, {'limitations': None},
    {'adequacy': 'unassessed'},
])
def test_assessment_identity_time_explanation_and_visible_citations(changes):
    packet = {'review_id': 'test', 'code': 'L1: int a;'}
    with pytest.raises(ValueError):
        validate_assessment({**rating(packet), **changes}, packet)


def test_missing_packet_assessment_or_match_cannot_pass(completed, cases):
    path = completed / 'assessments.final.jsonl'
    rows = read_jsonl(path)
    path.unlink()
    for row in rows[:-1]:
        append_jsonl(path, row)
    with pytest.raises(ValueError, match='every shown'):
        analyze(cases, completed)


def test_wrong_reference_match_reduces_sufficient_explanation_to_uncertain(completed, cases):
    replace_record(completed / 'adjudications.jsonl', 'case_id', cases[0].case_id, match='uncertain')
    report = analyze(cases, completed)
    assert report['rq1']['adequacy'] == {'adequate': 2, 'inadequate': 0, 'uncertain': 1}
    assert report['rq1']['identification_bounds'] == [2/3, 1.]


def test_mapping_failure_is_uncertain_and_failed_retrieval_stays_in_n(completed, cases):
    # Rebuild the packet/forms set for two missing U excerpts. All records are unit fixtures.
    specs = [s for s in run_specs(cases) if s['arm'] == 'U']
    for spec, status in zip(specs, ('mapping_error', 'empty_slice'), strict=False):
        replace_record(completed / 'slices.jsonl', 'run_id', spec['run_id'], status=status)
    write_stage_receipt(completed, 'slice', cases)
    packets, joins = packet_index(cases, completed)
    for name in ('blind_review_packets.jsonl', 'assessments.initial.jsonl', 'assessments.final.jsonl', 'adjudications.jsonl'):
        (completed / name).unlink()
        (completed / name).touch()
    for p in packets.values():
        append_jsonl(completed / 'blind_review_packets.jsonl', p)
        append_jsonl(completed / 'assessments.initial.jsonl', rating(p))
        append_jsonl(completed / 'assessments.final.jsonl', rating(p, hours_ago=71))
    for spec in specs:
        if spec['run_id'] in joins:
            append_jsonl(completed / 'adjudications.jsonl', {'case_id': spec['case_id'], 'review_id': joins[spec['run_id']], 'match': 'yes', 'reason': 'Test only.'})
    report = analyze(cases, completed)
    assert report['rq1']['n'] == 3
    assert report['rq1']['adequacy'] == {'adequate': 1, 'inadequate': 1, 'uncertain': 1}


def test_delayed_subset_is_exact_seeded_and_no_initial_overwrite(completed):
    first = completed / 'assessments.initial.jsonl'
    reassessment_plan(completed, first)
    plan = json.loads((completed / 'reassessment_plan.json').read_text())
    assert len(plan['subset']) == 2  # ceil(25% of six packets)
    with pytest.raises(FileExistsError):
        reassessment_plan(completed, first)
    with first.open('a') as f:
        f.write('\n')
    with pytest.raises(ValueError, match='Initial ratings changed'):
        consistency(completed, first, completed / 'no-second.jsonl')


def second_pass(work, delay):
    plan = json.loads((work / 'reassessment_plan.json').read_text())
    initial = {r['review_id']: r for r in read_jsonl(work / 'assessments.initial.jsonl')}
    path = work / 'assessments.second.jsonl'
    for entry in plan['subset']:
        row = dict(initial[entry['review_id']])
        row['assessed_utc'] = (datetime.fromisoformat(row['assessed_utc']) + timedelta(hours=delay)).isoformat()
        append_jsonl(path, row)
    return path


@pytest.mark.parametrize('delay,complete', [(47, False), (48, True)])
def test_completion_requires_real_48_hour_delays(completed, cases, delay, complete):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    later = second_pass(completed, delay)
    result = consistency(completed, completed / 'assessments.initial.jsonl', later)
    assert result['all_met_48_hours'] == complete
    report = analyze(cases, completed)
    assert (report['completion'] == 'complete') == complete


def test_delayed_ratings_need_reasons_and_same_identity(completed):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    later = second_pass(completed, 48)
    rid = read_jsonl(later)[0]['review_id']
    replace_record(later, 'review_id', rid, explanation='')
    with pytest.raises(ValueError, match='Explain'):
        consistency(completed, completed / 'assessments.initial.jsonl', later)


def test_second_pass_cannot_use_foreign_or_missing_ids(completed):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    later = second_pass(completed, 48)
    with later.open('a') as f:
        f.write(json.dumps({'review_id': 'foreign'}) + '\n')
    with pytest.raises(ValueError, match='entire frozen subset'):
        consistency(completed, completed / 'assessments.initial.jsonl', later)


def test_final_assessment_cannot_predate_initial(completed, cases):
    first = read_jsonl(completed / 'assessments.initial.jsonl')[0]
    replace_record(completed / 'assessments.final.jsonl', 'review_id', first['review_id'],
                   assessed_utc=(datetime.now(UTC) - timedelta(hours=80)).isoformat())
    with pytest.raises(ValueError, match='predates'):
        analyze(cases, completed)


def test_duplicate_packet_decisions_rejected(tmp_path):
    packet = {'review_id': 'test', 'code': 'L1: int a;'}
    path = tmp_path / 'ratings.jsonl'
    for _ in range(2):
        append_jsonl(path, rating(packet))
    with pytest.raises(ValueError, match='Duplicate'):
        assessments(path, {'test': packet})
