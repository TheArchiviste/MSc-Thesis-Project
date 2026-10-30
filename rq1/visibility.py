"""Deterministic line visibility, independently of assessor grades or proof audits."""
from __future__ import annotations

import csv

from evidence_experiment.locks import now, validate_terminal_records
from evidence_experiment.schema import file_digest, write_json


def compute(cases, work, *, sealed=False):
    from .sealing import require_release, verify_seal
    verify_seal(work)
    if not sealed:
        require_release(work)
    rows = validate_terminal_records(work, 'slice', cases)
    from evidence_experiment.schema import run_specs
    by_id = {c.case_id: c for c in cases}
    facts, relations, sizes = [], [], []
    for spec in run_specs(cases):
        row, case = rows[spec['run_id']], by_id[spec['case_id']]
        selected, rendered = set(row.get('slice_lines', [])), set(row.get('rendered_lines', []))
        shown = row['status'] == 'ok'
        sizes.append({'case_id': case.case_id, 'arm': spec['arm'], 'status': row['status'],
                      'selected_lines': len(selected), 'rendered_lines': len(rendered),
                      'source_lines': len(case.source_for(spec['arm']).splitlines())})
        if spec['arm'] != 'U':
            continue
        present = {}
        for element in case.referent['elements']:
            required = set(element['lines'])
            present[element['id']] = shown and required <= rendered
            facts.append({'case_id': case.case_id, 'element_id': element['id'],
                'essential': element['essential'], 'reference_lines': ';'.join(map(str, element['lines'])),
                'selected_reference_lines': ';'.join(map(str, sorted(required & selected))),
                'context_reference_lines': ';'.join(map(str, sorted(required & (rendered - selected)))),
                'absent_reference_lines': ';'.join(map(str, sorted(required - rendered))),
                'any_reference_line_visible': shown and bool(required & rendered),
                'all_reference_lines_visible': present[element['id']],
                'semantic_support': 'not_assessed' if shown else 'no_usable_excerpt'})
        for relation in case.referent['relations']:
            relations.append({'case_id': case.case_id, 'relation_id': relation['id'],
                'listed_premise_elements_fully_visible': shown and all(present[p] for p in relation['premise_ids']),
                'semantic_support': 'not_assessed' if shown else 'no_usable_excerpt'})
    target = work / 'structural_visibility'
    if target.exists():
        raise FileExistsError('Structural results already exist; preserve the first computation')
    target.mkdir()
    for name, records in (('elements.csv', facts), ('relation_prerequisites.csv', relations), ('sizes.csv', sizes)):
        with (target / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    text = ('# Structural visibility only\n\n'
            'Line intersections and listed relation-prerequisite visibility are deterministic descriptions of the frozen AI-assisted reference. '
            'They do not establish semantic relationship support, independent annotation accuracy or excerpt sufficiency. '
            'Partial reference-line groups are explicitly distinguished from complete groups.\n\n'
            f"Release state at computation: {'SEALED — do not inspect while developing the assessor' if sealed else 'released'}.\n")
    (target / 'README.md').write_text(text)
    receipt = {'utc': now(), 'sealed': sealed, 'slice_seal_sha256': file_digest(work / 'slice.seal.json'),
               'files': {p.name: file_digest(p) for p in sorted(target.iterdir())},
               'semantic_judgments': 0}
    write_json(target / 'receipt.json', receipt, exclusive=True)
    return receipt
