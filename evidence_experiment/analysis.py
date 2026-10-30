"""RQ1 first-pass sufficiency, source support and explicit acquisition denominators."""
from __future__ import annotations

import json
from collections import Counter

from .locks import check_stage_receipts, now, validate_terminal_records
from .review import index_jsonl, packet_index, validate_assessment
from .schema import file_digest, run_specs, write_json


def consistency_status(work, packets):
    if not packets:
        return {'complete': True, 'status': 'not_applicable_no_shown_packets', 'n': 0}
    required = [work / n for n in ('reassessment_plan.json', 'assessments.second.jsonl', 'consistency.json')]
    if not all(p.is_file() for p in required):
        return {'complete': False, 'status': 'pending_25_percent_delayed_reassessment'}
    from rq1.assess import consistency
    result = consistency(work, work / 'assessments.initial.jsonl', work / 'assessments.second.jsonl')
    return {'complete': result['all_met_48_hours'] is True,
            'status': 'complete' if result['all_met_48_hours'] else 'delay_below_48_hours', **result}


def calibration_for_work(work):
    from rq1.calibration import require_calibration
    lock = json.loads((work / 'experiment_lock.json').read_text())
    return require_calibration({'rq1_calibration_file': lock['calibration_file']})


def corrections(work, packets, initial):
    """Optional secondary corrections; never replace the primary labels."""
    from rq1.assessment_protocol import utc_stamp
    path = work / 'assessments.final.jsonl'
    rows = index_jsonl(path, 'review_id')
    if set(rows) - packets.keys():
        raise ValueError('Foreign corrected packets')
    for rid, row in rows.items():
        validate_assessment(row, packets[rid], expected_context='reference_informed')
        if (utc_stamp(row['assessed_utc']) < utc_stamp(initial[rid]['assessed_utc']) or
                not row.get('revision_reason', '').strip() or not row['cited_lines']):
            raise ValueError('Corrections need a later real timestamp, visible proof and a revision reason')
    return rows


def analyze(cases, work):
    from rq1.judge import verify_provenance
    from rq1.source_audit import confirm

    from .runner import INFRA_STATUSES
    check_stage_receipts(work)
    receipts = json.loads((work / 'stage_receipts.json').read_text())
    if not {'query', 'slice'} <= receipts.keys():
        raise ValueError('Acquire and receipt both real stages before analysis')
    for phase in ('query', 'slice'):
        validate_terminal_records(work, phase, cases)
    calibrated = calibration_for_work(work)
    packets, joins = packet_index(cases, work)
    if index_jsonl(work / 'blind_review_packets.jsonl', 'review_id') != packets:
        raise ValueError('Issue the exact current packets before assessment')
    initial = verify_provenance(work / 'assessments.initial.jsonl', packets, signature=calibrated['assessor_signature'])
    final = corrections(work, packets, initial)
    specs = run_specs(cases)
    expected = {s['case_id']: joins[s['run_id']] for s in specs if s['arm'] == 'U' and s['run_id'] in joins}
    path = work / 'adjudications.jsonl'
    if not path.is_file():
        raise FileNotFoundError(path)
    matches = index_jsonl(path, 'case_id')
    if matches.keys() != expected.keys():
        raise ValueError('Match each shown U packet to its source-only reference exactly once')
    slices = index_jsonl(work / 'slices.jsonl', 'run_id')
    by_case = {c.case_id: c for c in cases}
    records = []
    for spec in specs:
        row, case = slices[spec['run_id']], by_case[spec['case_id']]
        rid = joins.get(spec['run_id'])
        support, match, uncertainty = 'not_applicable', 'not_applicable', None
        if row['status'] != 'ok':
            uncertainty = 'acquisition' if row['status'] in INFRA_STATUSES | {'mapping_error'} else None
            verdict = 'uncertain' if uncertainty else 'inadequate'
            assessment = 'not_shown'
        else:
            assessment = initial[rid]['adequacy']
            verdict = assessment
            if spec['arm'] == 'U':
                audit = matches[spec['case_id']]
                verdict, support = confirm(initial[rid], audit, case, packets[rid])
                match = audit['match']
            if verdict == 'uncertain':
                uncertainty = 'assessment'
        elements = case.referent['elements']
        overlap = sum(bool(set(e['lines']) & set(row.get('rendered_lines', []))) for e in elements) / len(elements)
        records.append({**spec, 'status': row['status'], 'adequacy': verdict,
                        'initial_excerpt_assessment': assessment, 'source_support': support,
                        'mechanism_match': match, 'uncertainty_kind': uncertainty,
                        'no_usable_excerpt_reason': row['status'] if not rid else None,
                        'review_id': rid, 'role_line_hit_fraction': overlap if spec['arm'] == 'U' else None})
    primary = [r for r in records if r['arm'] == 'U']
    shown = [r for r in primary if r['review_id']]
    counts = {k: sum(r['adequacy'] == k for r in primary) for k in ('adequate', 'inadequate', 'uncertain')}
    n, retrieved, a = len(cases), len(shown), counts['adequate']
    ku = sum(r['uncertainty_kind'] == 'acquisition' for r in primary)
    ks = sum(r['uncertainty_kind'] == 'assessment' for r in primary)
    fixed = [r for r in records if r['arm'] == 'F' and r['review_id']]
    false_adequate = sum(initial[r['review_id']]['adequacy'] == 'adequate' for r in fixed)
    consistency = consistency_status(work, packets)
    report = {'scope': 'rq1_only', 'utc': now(), 'primary_rule': 'repeat_0_first_excerpt_only_confirmed_by_source_support',
              'repeats': 1, 'assessment_mode': 'Calibrated stateless AI assessor plus reference-informed AI source audit',
              'assessment_limit': 'Source references and support audits are AI-assisted. Stateless request provenance limits grader access to hidden context; sibling recognition and model pretraining remain limitations. No independent human validation or inter-rater reliability is claimed.',
              'completion': 'complete' if consistency['complete'] else 'provisional',
              'consistency': consistency, 'run_evidence': records,
              'rq1': {'n': n, 'blocks': len({c.cluster_id for c in cases}), 'retrieved_U': retrieved,
                      'adequacy': counts, 'adequate_retrieval_yield': a / n,
                      'adequacy_given_retrieval': a / retrieved if retrieved else None,
                      'identification_bounds': [a / n, (a + ku + ks) / n],
                      'conditional_identification_bounds': [a / retrieved, (a + ks) / retrieved] if retrieved else None,
                      'uncertain_acquisition': ku, 'uncertain_assessment': ks,
                      'initial_shown_grade_counts': dict(Counter(r['initial_excerpt_assessment'] for r in shown)),
                      'mechanism_correspondence_counts': dict(Counter(r['mechanism_match'] for r in shown)),
                      'status_counts': dict(Counter(r['status'] for r in primary)),
                      'one_case_percentage_points': 100 / n, 'two_case_percentage_points': 200 / n},
              'initial_fixed_control_check': {'planned_F': n, 'shown_F': len(fixed),
                  'unique_shown_F_packets': len({r['review_id'] for r in fixed}),
                  'initial_false_adequate': false_adequate,
                  'initial_false_adequacy_rate': false_adequate / len(fixed) if fixed else None},
              'secondary_corrections': {'n': len(final), 'affects_primary': False},
              'assessor_calibration_signature': calibrated['assessor_signature'],
              'analysis_provenance': {name: file_digest(work / name) for name in (
                  'assessments.initial.jsonl', 'assessments.initial.provenance.json', 'adjudications.jsonl',
                  'blind_review_packets.jsonl', 'stage_receipts.json', 'experiment_lock.json')}}
    if (work / 'assessments.final.jsonl').exists():
        report['analysis_provenance']['assessments.final.jsonl'] = file_digest(work / 'assessments.final.jsonl')
    write_json(work / 'analysis.json', report)
    from .rq1_report import write_report
    write_report(cases, work, report, initial, matches, final)
    return report
