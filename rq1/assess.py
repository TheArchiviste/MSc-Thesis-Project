"""Issue stateless grading tasks and record delayed within-assessor consistency."""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import timedelta
from pathlib import Path

from evidence_experiment.review import packet_index
from evidence_experiment.schema import (
    append_jsonl,
    file_digest,
    index_jsonl,
    load_cases,
    read_jsonl,
    run_specs,
    write_json,
)

from .assessment_protocol import response_template, utc_stamp
from .judge import export, verify_provenance
from .setup import CORPUS, ROOT
from .source_audit import template

SEED = 20261027


def prepare(split, work):
    cases = load_cases(CORPUS / f'{split}.jsonl')
    packets, joins = packet_index(cases, work)
    issued = read_jsonl(work / 'blind_review_packets.jsonl')
    if {r['review_id']: r for r in issued} != packets or len(issued) != len(packets):
        raise ValueError('Issue the exact RQ1 packets first')
    paths = [work / name for name in ('assessment_order.jsonl', 'assessments.template.jsonl',
                                      'adjudications.template.jsonl', 'assessment_order_metadata.json')]
    if any(p.exists() for p in paths):
        raise FileExistsError('Assessment forms already exist; preserving the issued order')
    case_sets = {rid: set() for rid in packets}
    for spec in run_specs(cases):
        if spec['run_id'] in joins:
            case_sets[joins[spec['run_id']]].add(spec['case_id'])
    remaining = sorted(packets)
    random.Random(SEED).shuffle(remaining)
    ordered, previous, violations = {}, set(), 0
    while remaining:
        i = next((i for i, rid in enumerate(remaining) if not case_sets[rid] & previous), 0)
        rid = remaining.pop(i)
        violations += bool(case_sets[rid] & previous)
        ordered[rid], previous = packets[rid], case_sets[rid]
        append_jsonl(paths[0], packets[rid])
        append_jsonl(paths[1], response_template(packets[rid]))
    by_case = {c.case_id: c for c in cases}
    for cid, rid in sorted({(s['case_id'], joins[s['run_id']]) for s in run_specs(cases)
                           if s['arm'] == 'U' and s['run_id'] in joins}):
        append_jsonl(paths[2], template(by_case[cid], packets[rid]))
    for path in paths[:3]:
        path.touch(exist_ok=True)
    write_json(paths[3], {'seed': SEED, 'packets': len(ordered), 'adjacent_case_violations': violations,
                         'blinding_limit': 'One stateless request per unique packet; labels concealed, code and sibling recognition remain possible. Source audits separately use references.'})
    export(ordered, work / 'assessment_requests.initial.jsonl')
    print(f'Prepared {len(ordered)} unassessed stateless requests; adjacent-case collisions: {violations}.')


def _initial(work, first):
    from evidence_experiment.analysis import calibration_for_work
    packets = index_jsonl(work / 'assessment_order.jsonl', 'review_id')
    if packets != index_jsonl(work / 'blind_review_packets.jsonl', 'review_id'):
        raise ValueError('Assessment order differs from issued packet contents')
    calibrated = calibration_for_work(work)
    return packets, verify_provenance(first, packets, signature=calibrated['assessor_signature'])


def reassessment_plan(work, first):
    packets, ratings = _initial(work, first)
    chosen = sorted(random.Random(SEED).sample(sorted(packets), math.ceil(.25 * len(packets))))
    plan = {'seed': SEED, 'packets_sha256': file_digest(work / 'assessment_order.jsonl'), 'fraction': .25,
            'first_assessments_sha256': file_digest(first),
            'subset': [{'review_id': rid, 'not_before_utc': (utc_stamp(ratings[rid]['assessed_utc']) + timedelta(hours=48)).isoformat()} for rid in chosen],
            'meaning': 'Within-assessor consistency, not independent validation; primary grades stay unchanged.'}
    path = work / 'reassessment_plan.json'
    if path.exists():
        raise FileExistsError('Delayed subset already selected; preserving it')
    write_json(path, plan)
    subset = {rid: packets[rid] for rid in chosen}
    for packet in subset.values():
        append_jsonl(work / 'reassessment_packets.jsonl', packet)
    (work / 'reassessment_packets.jsonl').touch(exist_ok=True)
    export(subset, work / 'assessment_requests.second.jsonl', pass_id='delayed',
           not_before={r['review_id']: r['not_before_utc'] for r in plan['subset']})
    print(f'Selected {len(chosen)}/{len(packets)} packets; honour every not-before timestamp.')


def consistency(work, first, second):
    from rq1.assessment_protocol import validate_identity
    plan = json.loads((work / 'reassessment_plan.json').read_text())
    if file_digest(first) != plan['first_assessments_sha256']:
        raise ValueError('Initial ratings changed; retain corrections separately')
    packets, initial = _initial(work, first)
    chosen = sorted(random.Random(SEED).sample(sorted(packets), math.ceil(.25 * len(packets))))
    if ([r['review_id'] for r in plan['subset']] != chosen or plan.get('packets_sha256') != file_digest(work / 'assessment_order.jsonl')):
        raise ValueError('The frozen delayed subset or order changed')
    subset = {rid: packets[rid] for rid in chosen}
    signature = validate_identity(next(iter(initial.values()))['assessor_identity']) if initial else None
    later = verify_provenance(second, subset, signature=signature, pass_id='delayed')
    deadlines = {r['review_id']: r['not_before_utc'] for r in plan['subset']}
    requests = index_jsonl(work / 'assessment_requests.second.jsonl', 'review_id')
    if requests.keys() != subset.keys() or any(requests[rid].get('not_before_utc') != deadlines[rid] for rid in chosen):
        raise ValueError('The delayed request deadlines changed')
    rows = []
    for rid in chosen:
        old, new = initial[rid], later[rid]
        hours = (utc_stamp(new['assessed_utc']) - utc_stamp(old['assessed_utc'])).total_seconds() / 3600
        rows.append({'review_id': rid, 'initial': old['adequacy'], 'second': new['adequacy'],
                     'delay_hours': hours, 'met_48_hours': hours >= 48})
    result = {'status': 'complete' if all(r['met_48_hours'] for r in rows) else 'delay_below_48_hours',
              'first_sha256': file_digest(first), 'second_sha256': file_digest(second),
              'plan_sha256': file_digest(work / 'reassessment_plan.json'), 'n': len(rows),
              'agreement': sum(r['initial'] == r['second'] for r in rows) / len(rows) if rows else None,
              'all_met_48_hours': all(r['met_48_hours'] for r in rows), 'records': rows,
              'limit': 'Within-assessor consistency only; no independent validation.'}
    write_json(work / 'consistency.json', result)
    print(work / 'consistency.json')
    return result


def main():
    from evidence_experiment.locks import work_lock
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'reassessment-plan', 'consistency'))
    p.add_argument('--split', choices=('development', 'main'), default='development')
    p.add_argument('--work', type=Path)
    p.add_argument('--first', type=Path)
    p.add_argument('--second', type=Path)
    a = p.parse_args()
    work = a.work or ROOT / 'work/rq1-v5' / a.split
    with work_lock(work):
        if a.action == 'prepare':
            prepare(a.split, work)
        elif a.action == 'reassessment-plan':
            reassessment_plan(work, a.first or work / 'assessments.initial.jsonl')
        else:
            consistency(work, a.first or work / 'assessments.initial.jsonl', a.second or work / 'assessments.second.jsonl')


if __name__ == '__main__':
    main()
