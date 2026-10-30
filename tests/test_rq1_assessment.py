"""First-pass integrity, visible support, denominators and delayed consistency."""
from __future__ import annotations

import json

import pytest

from evidence_experiment.analysis import analyze
from evidence_experiment.locks import write_stage_receipt
from evidence_experiment.review import assessments, packet_index, validate_assessment
from evidence_experiment.schema import append_jsonl, read_jsonl, run_specs
from rq1.assess import consistency, reassessment_plan
from rq1.judge import import_responses

from .conftest import IDENTITY, issue_test_grades, rating, replace_record, responses


def test_report_separates_u_f_and_provisional_delayed_work(completed, cases):
    report = analyze(cases, completed)
    assert report['scope'] == 'rq1_only' and report['completion'] == 'provisional'
    assert report['rq1']['n'] == 3 and report['rq1']['retrieved_U'] == 3
    assert report['rq1']['adequacy'] == {'adequate': 3, 'inadequate': 0, 'uncertain': 0}
    assert report['rq1']['adequate_retrieval_yield'] == report['rq1']['adequacy_given_retrieval'] == 1
    assert report['initial_fixed_control_check']['initial_false_adequate'] == 3
    assert 'provisional' in (completed / 'rq1_report.md').read_text()
    assert len((completed / 'rq1_cases.csv').read_text().splitlines()) == 7
    assert (completed / 'rq1_relationship_support.csv').exists()
    assert not {'rq2', 'rq3', 'classifier', 'threshold'} & report.keys()


@pytest.mark.parametrize('changes', [
    {'assessor_id': 'pretend_second_human'}, {'assessment_origin': 'independent human'},
    {'assessed_utc': None}, {'assessed_utc': '2020-01-01T00:00:00'},
    {'assessed_utc': '2099-01-01T00:00:00+00:00'}, {'explanation': ''},
    {'cited_lines': [999]}, {'relationships': []}, {'limitations': None},
    {'adequacy': 'unassessed'}, {'assessment_context': 'reference_informed'},
    {'assessor_identity': {}}, {'premises': []}, {'assumptions_used': ['hidden_source_length']},
])
def test_assessment_identity_time_explanation_and_visible_citations(changes):
    packet = {'review_id': 'test', 'code': 'L1: int a;'}
    with pytest.raises(ValueError):
        validate_assessment({**rating(packet), **changes}, packet)


def test_initial_file_cannot_be_silently_edited(completed, cases):
    first = read_jsonl(completed / 'assessments.initial.jsonl')[0]
    replace_record(completed / 'assessments.initial.jsonl', 'review_id', first['review_id'], adequacy='inadequate')
    with pytest.raises(ValueError, match='provenance files changed'):
        analyze(cases, completed)


def test_missing_match_cannot_pass(completed, cases):
    (completed / 'adjudications.jsonl').write_text('')
    with pytest.raises(ValueError, match='each shown U'):
        analyze(cases, completed)


def test_uncertain_source_match_has_separate_assessment_uncertainty(completed, cases):
    replace_record(completed / 'adjudications.jsonl', 'case_id', cases[0].case_id, match='uncertain')
    q = analyze(cases, completed)['rq1']
    assert q['adequacy'] == {'adequate': 2, 'inadequate': 0, 'uncertain': 1}
    assert q['uncertain_assessment'] == 1 and q['uncertain_acquisition'] == 0
    assert q['identification_bounds'] == [2/3, 1.]


def test_relationship_missing_defeats_line_hits_and_source_match(completed, cases):
    row = read_jsonl(completed / 'adjudications.jsonl')[0]
    row['relation_checks'][0].update(support='missing', cited_lines=[], explanation='Capacity relation is absent.')
    replace_record(completed / 'adjudications.jsonl', 'case_id', row['case_id'], relation_checks=row['relation_checks'])
    report = analyze(cases, completed)
    outcome = next(r for r in report['run_evidence'] if r['case_id'] == row['case_id'] and r['arm'] == 'U')
    assert outcome['role_line_hit_fraction'] == 1 and outcome['adequacy'] == 'inadequate'


def reissue_after_slice_change(work, cases):
    write_stage_receipt(work, 'slice', cases)
    for pattern in ('blind_review_packets.jsonl', 'review_key.jsonl', 'assessment*', 'adjudications*', 'responses.initial.jsonl'):
        for path in work.glob(pattern):
            if path.is_file():
                path.unlink()
    issue_test_grades(work, cases)


def test_mapping_failure_uncertain_and_no_excerpt_not_rejected_grade(completed, cases):
    specs = [s for s in run_specs(cases) if s['arm'] == 'U']
    for spec, status in zip(specs, ('mapping_error', 'empty_slice'), strict=False):
        replace_record(completed / 'slices.jsonl', 'run_id', spec['run_id'], status=status)
    reissue_after_slice_change(completed, cases)
    report = analyze(cases, completed)
    q = report['rq1']
    assert q['n'] == 3 and q['retrieved_U'] == 1
    assert q['adequacy'] == {'adequate': 1, 'inadequate': 1, 'uncertain': 1}
    assert q['adequacy_given_retrieval'] == 1 and q['adequate_retrieval_yield'] == 1/3
    assert q['uncertain_acquisition'] == 1
    assert all(r['initial_excerpt_assessment'] == 'not_shown' for r in report['run_evidence'] if r['status'] != 'ok')


def test_zero_shown_has_no_conditional_or_fixed_rate(completed, cases):
    for spec in run_specs(cases):
        replace_record(completed / 'slices.jsonl', 'run_id', spec['run_id'], status='empty_slice')
    reissue_after_slice_change(completed, cases)
    report = analyze(cases, completed)
    assert report['rq1']['adequacy_given_retrieval'] is None
    assert report['initial_fixed_control_check']['initial_false_adequacy_rate'] is None
    assert report['completion'] == 'complete'


def test_reference_informed_promotion_is_secondary_only(completed, cases):
    packets, joins = packet_index(cases, completed)
    rid = next(joins[s['run_id']] for s in run_specs(cases) if s['arm'] == 'U')
    raw = completed / 'responses.initial.jsonl'
    row = next(r for r in read_jsonl(raw) if r['review_id'] == rid)
    content = json.loads(row['content']); content['adequacy'] = 'inadequate'
    replace_record(raw, 'review_id', rid, content=json.dumps(content))
    (completed / 'assessments.initial.jsonl').unlink()
    (completed / 'assessments.initial.provenance.json').unlink()
    import_responses(completed / 'assessment_requests.initial.jsonl', raw, completed / 'assessments.initial.jsonl')
    later = rating(packets[rid], hours_ago=71)
    later.update(assessment_context='reference_informed', revision_reason='A later source-informed correction; visible proof recorded separately.')
    append_jsonl(completed / 'assessments.final.jsonl', later)
    result = analyze(cases, completed)
    assert result['rq1']['adequacy']['adequate'] == 2
    assert result['secondary_corrections'] == {'n': 1, 'affects_primary': False}
    assert 'inadequate,adequate' in (completed / 'rq1_grade_changes.csv').read_text()


def test_delayed_subset_exact_seeded_and_no_initial_overwrite(completed):
    first = completed / 'assessments.initial.jsonl'
    reassessment_plan(completed, first)
    assert len(json.loads((completed / 'reassessment_plan.json').read_text())['subset']) == 2
    with pytest.raises(FileExistsError):
        reassessment_plan(completed, first)
    with first.open('a') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='Initial ratings changed'):
        consistency(completed, first, completed / 'missing.jsonl')


def second_pass(work, delay, **kwargs):
    return responses(work / 'assessment_requests.second.jsonl', work / 'responses.second.jsonl',
                     work / 'assessments.second.jsonl', hours_ago=72-delay, **kwargs)


def test_early_second_response_cannot_be_imported(completed):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    with pytest.raises(ValueError, match='before its frozen deadline'):
        second_pass(completed, 47)


def test_real_48_hour_delay_allows_completion(completed, cases):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    later = second_pass(completed, 49)
    assert consistency(completed, completed / 'assessments.initial.jsonl', later)['all_met_48_hours']
    assert analyze(cases, completed)['completion'] == 'complete'


def test_delayed_identity_cannot_change(completed):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    later = second_pass(completed, 49, identity={**IDENTITY, 'reported_model': 'changed-model'})
    with pytest.raises(ValueError, match='identity changed'):
        consistency(completed, completed / 'assessments.initial.jsonl', later)


def test_second_pass_cannot_use_foreign_ids(completed):
    reassessment_plan(completed, completed / 'assessments.initial.jsonl')
    later = second_pass(completed, 49)
    append_jsonl(later, {'review_id': 'foreign'})
    with pytest.raises(ValueError, match='provenance files changed'):
        consistency(completed, completed / 'assessments.initial.jsonl', later)


def test_correction_cannot_predate_initial(completed, cases):
    packets, _ = packet_index(cases, completed)
    packet = next(iter(packets.values()))
    row = rating(packet, hours_ago=80)
    row.update(assessment_context='reference_informed', revision_reason='Synthetic test correction.')
    append_jsonl(completed / 'assessments.final.jsonl', row)
    with pytest.raises(ValueError, match='later real timestamp'):
        analyze(cases, completed)


def test_duplicate_packet_decisions_rejected(tmp_path):
    packet = {'review_id': 'test', 'code': 'L1: int a;'}
    path = tmp_path / 'ratings.jsonl'
    for _ in range(2):
        append_jsonl(path, rating(packet))
    with pytest.raises(ValueError, match='Duplicate'):
        assessments(path, {'test': packet})
