"""Stage-specific seals and release gates; hashes detect changes, not human access."""
from __future__ import annotations

import contextlib
import json
import os
import sys

from evidence_experiment.locks import check_stage_receipts, now, validate_terminal_records
from evidence_experiment.schema import file_digest, write_json


@contextlib.contextmanager
def private_log(path):
    """Capture Python and native model/worker stdout/stderr until release."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(fd) for fd in (1, 2)]
    try:
        with path.open('ab', buffering=0) as log:
            for fd in (1, 2):
                os.dup2(log.fileno(), fd)
            try:
                yield
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
    finally:
        for fd, backup in zip((1, 2), saved, strict=True):
            os.dup2(backup, fd)
            os.close(backup)


def _files(work, phase):
    names = ['queries.jsonl', 'query_sessions.jsonl', 'witness_validation.jsonl',
             'runtime.query.requirements.txt']
    optional = ['query.sealed.log', 'query_load_errors.jsonl', 'query_runtime_errors.jsonl']
    if phase == 'slice':
        names += ['slices.jsonl', 'runtime.slice.requirements.txt', 'experiment_lock.json',
                  'stage_receipts.json', 'query.seal.json']
        optional += ['slice.sealed.log', 'slice_attempts.jsonl']
    paths = [work / name for name in names]
    paths += [work / name for name in optional if (work / name).exists()]
    if phase == 'slice':
        paths += [p for p in (work / 'workers').rglob('*') if p.is_file()]
    if any(not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(work.resolve()) for p in paths):
        raise ValueError('Seal needs actual contained stage files, never symlink targets')
    return {str(p.relative_to(work)): file_digest(p) for p in sorted(set(paths))}


def seal(work, phase, cases):
    if phase not in {'query', 'slice'}:
        raise ValueError('Seal query or slice acquisition')
    check_stage_receipts(work)
    validate_terminal_records(work, phase, cases)
    if phase == 'slice':
        verify_seal(work, 'query')
    lock = json.loads((work / 'experiment_lock.json').read_text())
    body = {'phase': phase, 'input_fingerprint': lock['fingerprint'], 'files': _files(work, phase),
            'stage_environment': lock['stage_environments'][phase],
            'meaning': 'Immutable hash inventory. Outputs remain unopened by protocol; this is not cryptographic access control.'}
    path = work / f'{phase}.seal.json'
    if path.exists():
        old = verify_seal(work, phase)
        if any(old.get(k) != v for k, v in body.items()):
            raise ValueError('Prior acquisition seal differs')
        return old
    receipt = {**body, 'sealed_utc': now()}
    write_json(path, receipt, exclusive=True)
    return receipt


def verify_seal(work, phase='slice'):
    from .setup import corpus_contract
    receipt = json.loads((work / f'{phase}.seal.json').read_text())
    lock = json.loads((work / 'experiment_lock.json').read_text())
    if (receipt.get('phase') != phase or receipt.get('input_fingerprint') != lock['fingerprint'] or
            lock.get('acquisition_contract') != corpus_contract() or
            receipt.get('stage_environment') != lock['stage_environments'].get(phase) or
            receipt.get('files') != _files(work, phase)):
        raise ValueError('Sealed acquisition changed; preserve it and investigate')
    return receipt


def release(work, cfg, *, main=False):
    from .calibration import require_calibration
    from .setup import ROOT, assessment_code_contract
    verified = verify_seal(work)
    calibrated = require_calibration(cfg)
    if main:
        frozen = json.loads((ROOT / cfg['rq1_freeze_file']).read_text())
        if (frozen.get('assessor_signature') != calibrated['assessor_signature'] or
                frozen.get('assessment_code_contract') != assessment_code_contract()):
            raise ValueError('Freeze development assessments before releasing main outputs')
        verify_development_snapshot(frozen, (ROOT / cfg['rq1_calibration_file']).parent.parent)
    body = {'input_fingerprint': verified['input_fingerprint'],
            'slice_seal_sha256': file_digest(work / 'slice.seal.json'),
            'calibration_file': cfg['rq1_calibration_file'],
            'calibration_sha256': file_digest(ROOT / cfg['rq1_calibration_file']),
            'assessor_signature': calibrated['assessor_signature'],
            'assessment_code_contract': assessment_code_contract()}
    if main:
        body['assessment_freeze_file'] = cfg['rq1_freeze_file']
        body['assessment_freeze_sha256'] = file_digest(ROOT / cfg['rq1_freeze_file'])
    path = work / 'assessment_lock.json'
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in body.items()):
            raise ValueError('Assessment release changed; preserve the initial release')
        return old
    receipt = {**body, 'released_utc': now()}
    write_json(path, receipt, exclusive=True)
    return receipt


def require_release(work):
    from .calibration import require_calibration
    from .setup import ROOT, assessment_code_contract
    acquisition = verify_seal(work)
    receipt = json.loads((work / 'assessment_lock.json').read_text())
    if (receipt.get('slice_seal_sha256') != file_digest(work / 'slice.seal.json') or
            receipt.get('input_fingerprint') != acquisition['input_fingerprint'] or
            receipt.get('assessment_code_contract') != assessment_code_contract() or
            receipt.get('calibration_sha256') != file_digest(ROOT / receipt['calibration_file'])):
        raise ValueError('Assessment release no longer matches sealed acquisition and judging instrument')
    calibrated = require_calibration({'rq1_calibration_file': receipt['calibration_file']})
    if receipt.get('assessor_signature') != calibrated['assessor_signature']:
        raise ValueError('Assessment release assessor differs from accepted calibration')
    if receipt.get('assessment_freeze_file'):
        freeze = ROOT / receipt['assessment_freeze_file']
        if file_digest(freeze) != receipt['assessment_freeze_sha256']:
            raise ValueError('Main assessment freeze changed after release')
        verify_development_snapshot(json.loads(freeze.read_text()),
                                    (ROOT / receipt['calibration_file']).parent.parent)
    return receipt


def verify_development_snapshot(frozen, root):
    files = frozen.get('development_assessment_files', {})
    required = {f'development/{name}' for name in ('assessments.initial.jsonl',
        'assessments.initial.provenance.json', 'adjudications.jsonl', 'blind_review_packets.jsonl',
        'assessment_lock.json')}
    if not required <= files.keys() or len(files) < 7:
        raise ValueError('Development assessment snapshot is incomplete')
    for name, sha in files.items():
        path = root / name
        if (path.is_symlink() or not path.resolve().is_relative_to((root / 'development').resolve()) or
                file_digest(path) != sha):
            raise ValueError('Development first assessments or source audit changed after freeze')
