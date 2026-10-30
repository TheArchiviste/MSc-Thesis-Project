"""Dev-only, source-checked calibration before any paid Q acquisition."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from evidence_experiment.locks import now, require_witnesses, work_lock
from evidence_experiment.review import numbered_view, packet_lines, render_claim
from evidence_experiment.schema import (
    append_jsonl,
    digest,
    file_digest,
    index_jsonl,
    load_cases,
    read_jsonl,
    write_json,
)

from .assessment_protocol import contract, public_packet, utc_stamp
from .judge import export, verify_provenance

SEED = 20261030


def bank():
    from .setup import CORPUS
    packets, key = {}, []
    for case in load_cases(CORPUS / 'development.jsonl'):
        u, f = (case.source_for(a).splitlines() for a in ('U', 'F'))
        if len(u) != len(f):
            raise ValueError('Recheck the equal-coordinate calibration construction')
        different = {i for i, (a, b) in enumerate(zip(u, f, strict=True), 1) if a != b}
        same = [i for i in range(1, len(u) + 1) if i not in different]
        reduced = [i for i, line in enumerate(u, 1) if 'print' not in line and 'free(' not in line]
        views = [('complete_U', 'U', list(range(1, len(u) + 1)), 'adequate'),
                 ('complete_F', 'F', list(range(1, len(f) + 1)), 'inadequate'),
                 ('reduced_sufficient_U', 'U', reduced, 'adequate'),
                 ('indistinguishable_incomplete', 'U', same, 'inadequate')]
        if numbered_view(case.source_for('U'), same) != numbered_view(case.source_for('F'), same):
            raise ValueError('The negative anchor must be identical under U and F')
        for kind, arm, coords, expected in views:
            packet = public_packet(render_claim(case.referent), numbered_view(case.source_for(arm), coords))
            rid = packet['review_id']
            if rid in packets:
                raise ValueError('Calibration anchors must be distinct')
            packets[rid] = packet
            reason = (case.referent['mechanism'] if expected == 'adequate' else
                      case.referent['repair'] if kind == 'complete_F' else
                      f'Lines {sorted(different)} distinguishing U from F are absent. The exact view is compatible with both; the documented entry-path flaw is not justified.')
            key.append({'review_id': rid, 'case_id': case.case_id, 'kind': kind, 'expected': expected,
                        'source_reason': reason, 'removed_discriminating_lines': sorted(different) if kind == 'indistinguishable_incomplete' else [],
                        'source_sha256': {a: digest(case.source_for(a)) for a in ('U', 'F')}})
    order = list(packets)
    random.Random(SEED).shuffle(order)
    return {rid: packets[rid] for rid in order}, key


def prepare(config):
    from .setup import (
        CORPUS,
        ROOT,
        corpus_contract,
        load_config,
        verify_corpus,
        verify_implementation,
    )
    verify_corpus()
    verify_implementation()
    cfg = load_config(config)
    root = (ROOT / cfg['rq1_calibration_file']).parent
    witnessed = root.parent / 'development'
    require_witnesses(witnessed, load_cases(CORPUS / 'development.jsonl'))
    packets, key = bank()
    expected = {'assessment_contract_sha256': contract()['contract_sha256'],
                'corpus_contract': corpus_contract(), 'development_witness_sha256': file_digest(witnessed / 'witness_validation.jsonl'),
                'seed': SEED, 'n': 12, 'adequate': 6, 'inadequate': 6,
                'limit': 'AI-assisted source answer key, not independent human validation; no Q outputs.'}
    manifest = root / 'bank.json'
    if manifest.exists():
        if json.loads(manifest.read_text()) != expected or index_jsonl(root / 'public/packets.jsonl', 'review_id') != packets or read_jsonl(root / 'private/answer_key.jsonl') != key:
            raise ValueError('Calibration bank changed; preserve it and revise the version explicitly')
    else:
        write_json(manifest, expected)
        for p in packets.values():
            append_jsonl(root / 'public/packets.jsonl', p)
        for row in key:
            append_jsonl(root / 'private/answer_key.jsonl', row)
            append_jsonl(root / 'source_audit.template.jsonl', {'review_id': row['review_id'],
                'source_auditor': 'codex_source_auditor', 'audited_utc': None,
                'source_proof_supported': 'unassessed', 'cited_lines': [], 'reason': ''})
        (root / 'public/README.md').write_text(
            '# Excerpt-only calibration\n\nRun one request at a time using `rq1.judge`. Each request has only the public rubric and one excerpt.\n'
            'Do not supply the private answer key, full source, sibling packets, prior responses or diagnostic archive to the grader.\n'
            'Initial responses are immutable. Source support is checked separately after import.\n')
    export(packets, root / 'public/requests.jsonl', pass_id='calibration')
    print(f'RQ1_CALIBRATION_PREPARED: 12 development anchors (6 adequate / 6 inadequate); {root}; grading PENDING')
    return root


def evaluate(root):
    packets, expected_key = bank()
    key = index_jsonl(root / 'private/answer_key.jsonl', 'review_id')
    if key != {r['review_id']: r for r in expected_key} or index_jsonl(root / 'public/packets.jsonl', 'review_id') != packets:
        raise ValueError('Calibration key or public packets changed')
    grades = verify_provenance(root / 'assessments.initial.jsonl', packets, pass_id='calibration')
    audit = index_jsonl(root / 'source_audit.jsonl', 'review_id')
    if audit.keys() != key.keys():
        raise ValueError('Audit the source proof for all 12 calibration judgments')
    rows = []
    for rid, expected in key.items():
        r, grade = audit[rid], grades[rid]
        if (r.get('source_auditor') != 'codex_source_auditor' or
                r.get('source_proof_supported') not in {'yes', 'no', 'uncertain'} or
                not r.get('reason', '').strip() or not isinstance(r.get('cited_lines'), list) or
                not r['cited_lines'] or any(type(n) is not int for n in r['cited_lines']) or
                not set(r['cited_lines']) <= packet_lines(packets[rid]['code'])):
            raise ValueError('Calibration proof audit needs a real decision, visible citations and reasoning')
        if utc_stamp(r.get('audited_utc')) < utc_stamp(grade['assessed_utc']):
            raise ValueError('Inspect the actual response before its source-proof audit')
        rows.append({'review_id': rid, 'kind': expected['kind'], 'expected': expected['expected'],
                     'observed': grade['adequacy'], 'label_correct': grade['adequacy'] == expected['expected'],
                     'proof_supported': r['source_proof_supported']})
    proof = json.loads((root / 'assessments.initial.provenance.json').read_text())
    return {'accepted': all(r['label_correct'] and r['proof_supported'] == 'yes' for r in rows),
            'assessor_signature': proof['assessor_signatures'][0], 'n': len(rows), 'records': rows,
            'meaning': 'All 12 predeclared labels and source-proof audits must pass; calibration is not population accuracy or human validation.'}


def accept(config):
    from .setup import ROOT, corpus_contract, load_config
    cfg = load_config(config)
    path = ROOT / cfg['rq1_calibration_file']
    root = prepare(config)
    result = evaluate(root)
    write_json(root / 'evaluation.json', result)
    if not result['accepted']:
        raise ValueError('Calibration failed; retain responses, diagnose on development only, and predeclare a new assessor/protocol version before retesting')
    receipt = {**result, 'assessment_contract_sha256': contract()['contract_sha256'],
               'corpus_contract': corpus_contract(), 'files': {name: file_digest(root / name) for name in (
                   'bank.json', 'public/packets.jsonl', 'public/requests.jsonl', 'private/answer_key.jsonl',
                   'assessments.initial.jsonl', 'assessments.initial.provenance.json', 'source_audit.jsonl')},
               'accepted_utc': now()}
    if path.exists():
        require_calibration(cfg)
        return json.loads(path.read_text())
    write_json(path, receipt, exclusive=True)
    print(f'RQ1_CALIBRATION_ACCEPTED {path}')
    return receipt


def require_calibration(cfg):
    from .setup import ROOT, corpus_contract
    path = ROOT / cfg['rq1_calibration_file']
    receipt = json.loads(path.read_text())
    if (receipt.get('accepted') is not True or receipt.get('n') != 12 or
            receipt.get('assessment_contract_sha256') != contract()['contract_sha256'] or
            receipt.get('corpus_contract') != corpus_contract()):
        raise ValueError('Current source-checked assessor calibration is required')
    for name, sha in receipt.get('files', {}).items():
        if file_digest(path.parent / name) != sha:
            raise ValueError('Calibration inputs or assessments changed after acceptance')
    required = {'bank.json', 'public/packets.jsonl', 'public/requests.jsonl', 'private/answer_key.jsonl',
                'assessments.initial.jsonl', 'assessments.initial.provenance.json', 'source_audit.jsonl'}
    if set(receipt.get('files', {})) != required:
        raise ValueError('Calibration receipt is incomplete')
    result = evaluate(path.parent)
    if not result['accepted'] or result['assessor_signature'] != receipt['assessor_signature']:
        raise ValueError('Calibration no longer passes')
    return receipt


def main():
    from .setup import DEFAULT_CONFIG, ROOT, load_config
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'accept', 'status'))
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    a = p.parse_args()
    cfg = load_config(a.config)
    with work_lock((ROOT / cfg['rq1_calibration_file']).parent):
        if a.action == 'prepare':
            prepare(a.config)
        elif a.action == 'accept':
            accept(a.config)
        else:
            print(json.dumps(require_calibration(cfg), indent=2))


if __name__ == '__main__':
    main()
