"""Readable RQ1 evidence, separating sufficiency, retrieval and descriptive visibility."""
from __future__ import annotations

import csv

from .schema import index_jsonl


def write_report(cases, work, report, initial, matches, corrections):
    by_case = {c.case_id: c for c in cases}
    slices = index_jsonl(work / 'slices.jsonl', 'run_id')
    records, visibility, relations, transitions = [], [], [], []
    for out in report['run_evidence']:
        case, slc = by_case[out['case_id']], slices[out['run_id']]
        selected, rendered = set(slc.get('slice_lines', [])), set(slc.get('rendered_lines', []))
        rid = out['review_id']
        grade = initial.get(rid, {})
        match = matches.get(case.case_id, {}) if out['arm'] == 'U' else {}
        missing = []
        if out['arm'] == 'U':
            for e in case.referent['elements']:
                location = ('selected' if selected.intersection(e['lines']) else
                            'context_only' if rendered.intersection(e['lines']) else 'absent') if rid else 'no_usable_excerpt'
                if location in {'absent', 'no_usable_excerpt'}:
                    missing.append(e['id'])
                visibility.append({'case_id': case.case_id, 'block': case.cluster_id, 'element_id': e['id'],
                    'role': e['role'], 'essential': e['essential'], 'source_lines': ';'.join(map(str, e['lines'])),
                    'visibility': location, 'meaning': e['meaning']})
            checks = {r['relation_id']: r for r in match.get('relation_checks', [])}
            for r in case.referent['relations']:
                audit = checks.get(r['id'], {})
                relations.append({'case_id': case.case_id, 'relation_id': r['id'],
                    'required_relationship': r['explanation'], 'support': audit.get('support', 'no_usable_excerpt'),
                    'cited_lines': ';'.join(map(str, audit.get('cited_lines', []))),
                    'reason': audit.get('explanation', '')})
        records.append({**out, 'block': case.cluster_id, 'upstream_cwe': case.cwe,
            'overflowing_object': case.referent['observed_storage_kind'],
            'selected_lines': len(selected), 'rendered_lines': len(rendered),
            'source_lines': len(case.source_for(out['arm']).splitlines()),
            'facts_with_no_rendered_line': ';'.join(missing),
            'initial_assessment_reason': grade.get('explanation', ''), 'match_reason': match.get('reason', '')})
    for rid, row in initial.items():
        corrected = corrections.get(rid)
        transitions.append({'review_id': rid, 'initial': row['adequacy'],
            'secondary_corrected': corrected['adequacy'] if corrected else 'not_supplied',
            'revision_reason': corrected.get('revision_reason', '') if corrected else '',
            'affects_primary': False})
    _csv(work / 'rq1_cases.csv', records)
    _csv(work / 'rq1_element_visibility.csv', visibility)
    _csv(work / 'rq1_relationship_support.csv', relations)
    _csv(work / 'rq1_grade_changes.csv', transitions)
    q, f = report['rq1'], report['initial_fixed_control_check']
    n, r, a = q['n'], q['retrieved_U'], q['adequacy']['adequate']
    lower, upper = q['identification_bounds']
    lines = ['# RQ1 evidence adequacy', '', f"Status: **{report['completion']}**; {report['consistency']['status']}.",
        f"Assessment: {report['assessment_mode']}.", report['assessment_limit'], '',
        'The primary outcome uses one U run per case and its first excerpt-only grade, confirmed against source correspondence and visible relationship support. Later reference-informed corrections never promote this outcome.', '',
        f'Enrolled cases/blocks: **{n}/{q["blocks"]}**. Usable U excerpts: **{r}/{n}**.',
        f'Adequate retrieval yield: **{a}/{n} ({a/n:.1%})**.',
        f'Adequacy conditional on retrieval: **{a}/{r} ({a/r:.1%})**.' if r else 'Adequacy conditional on retrieval: **not estimable**.',
        f'Unresolved acquisition/mapping: **{q["uncertain_acquisition"]}**; unresolved assessment: **{q["uncertain_assessment"]}**.',
        f'Overall identification bounds: **{lower:.1%}–{upper:.1%}**. These are unresolved-case bounds, not confidence intervals.',
        f'One/two changed main case judgments move the yield by {q["one_case_percentage_points"]:.2f}/{q["two_case_percentage_points"]:.2f} percentage points.', '',
        'A missing excerpt is an acquisition outcome, not a rejected grader packet. See the two separate columns below.', '',
        '| Case | Acquisition | First excerpt grade | Confirmed primary | Correspondence |', '|---|---|---|---|---|']
    for row in records:
        if row['arm'] == 'U':
            lines.append(f"| {row['case_id']} | {row['status']} | {row['initial_excerpt_assessment']} | {row['adequacy']} | {row['mechanism_match']} |")
    lines += ['', f"Fixed controls: {f['planned_F']} planned; {f['shown_F']} shown ({f['unique_shown_F_packets']} unique packets).",
        (f"Initial false adequacy: **{f['initial_false_adequate']}/{f['shown_F']}**." if f['shown_F'] else
         'Initial false adequacy: **not estimable; no F excerpts shown**.'),
        'F controls are excluded from the primary U denominator. Complete F calibration anchors are a separate development instrument check.', '',
        '- `rq1_cases.csv`: all U/F acquisition outcomes, first grades, source correspondence and explanations.',
        '- `rq1_element_visibility.csv`: selected, added as context, absent, or no usable excerpt for each source fact.',
        '- `rq1_relationship_support.csv`: source-audited support for each required relationship.',
        '- `rq1_grade_changes.csv`: initial-to-secondary corrections and reasons; no primary promotion.', '',
        'Line hits describe visibility. They are not semantic recall or proof that a relationship is established.',
        'Results apply to this small, curated Juliet sample and the frozen Q/Joern configuration. Delayed checks measure within-assessor consistency only.']
    (work / 'rq1_report.md').write_text('\n'.join(lines) + '\n')


def _csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
