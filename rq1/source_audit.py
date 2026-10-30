"""Reference-informed support checks cannot promote the first excerpt-only grade."""
from __future__ import annotations

from evidence_experiment.review import packet_lines

from .assessment_protocol import ASSUMPTIONS, utc_stamp

SUPPORT = {'supported', 'alternative_supported', 'missing', 'contradicted', 'uncertain'}


def template(case, packet):
    return {'case_id': case.case_id, 'review_id': packet['review_id'],
            'source_auditor': 'codex_source_auditor', 'audited_utc': None,
            'match': 'unassessed', 'reason': '',
            'relation_checks': [{'relation_id': r['id'], 'support': 'unassessed',
                'cited_lines': [], 'assumption_ids': [], 'explanation': ''}
                for r in case.referent['relations']]}


def validate(row, case, packet):
    if (row.get('case_id') != case.case_id or row.get('review_id') != packet['review_id'] or
            row.get('source_auditor') != 'codex_source_auditor' or
            row.get('match') not in {'yes', 'no', 'uncertain'} or not row.get('reason', '').strip()):
        raise ValueError('Source correspondence needs an explicit decision, identity and reason')
    utc_stamp(row.get('audited_utc'))
    checks = row.get('relation_checks', [])
    expected = {r['id'] for r in case.referent['relations']}
    if {r.get('relation_id') for r in checks} != expected or len(checks) != len(expected):
        raise ValueError('Check every required source relationship exactly once')
    visible = packet_lines(packet['code'])
    for r in checks:
        if (r.get('support') not in SUPPORT or not r.get('explanation', '').strip() or
                not isinstance(r.get('cited_lines'), list) or
                any(type(n) is not int for n in r['cited_lines']) or
                not set(r['cited_lines']) <= visible or
                not isinstance(r.get('assumption_ids'), list) or
                not set(r['assumption_ids']) <= ASSUMPTIONS.keys()):
            raise ValueError('A relationship check needs visible citations, allowed assumptions and reasoning')
        if r['support'] in {'supported', 'alternative_supported'} and not r['cited_lines']:
            raise ValueError('Supported relationships need visible proof; source familiarity is not proof')
    if any(r['support'] in {'missing', 'contradicted'} for r in checks):
        return 'inadequate'
    if any(r['support'] == 'uncertain' for r in checks):
        return 'uncertain'
    return 'adequate'


def confirm(initial, row, case, packet):
    support = validate(row, case, packet)
    if utc_stamp(row['audited_utc']) < utc_stamp(initial['assessed_utc']):
        raise ValueError('Source support audit must follow the actual initial response')
    if row['match'] == 'no' or support == 'inadequate':
        return 'inadequate', support
    if initial['adequacy'] == 'inadequate':
        return 'inadequate', support
    if initial['adequacy'] == 'uncertain' or row['match'] == 'uncertain' or support == 'uncertain':
        return 'uncertain', support
    return 'adequate', support
