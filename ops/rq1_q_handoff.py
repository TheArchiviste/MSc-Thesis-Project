"""Checksummed CPU-to-Q transfer; no assessor weights, credentials or paid calls."""
from __future__ import annotations

import argparse
import json
import os
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from evidence_experiment.locks import environment, git_provenance
from evidence_experiment.schema import file_digest, write_json
from rq1.setup import (
    DEFAULT_CONFIG,
    ROOT,
    capability_valid,
    corpus_contract,
    doctor,
    load_config,
    require_acquisition_freeze,
    token_audit_valid,
    verify_corpus,
    verify_implementation,
)

WORK = Path('work/rq1-v7')


def files_for_transfer(cfg):
    names = [DEFAULT_CONFIG, Path(cfg['rq1_acquisition_freeze_file']), Path(cfg['rq1_token_audit_file'])]
    names += [WORK / split / 'witness_validation.jsonl' for split in ('development', 'main')]
    cap = (ROOT / cfg['joern_capability_file']).parent
    names += [p.relative_to(ROOT) for p in cap.rglob('*') if p.is_file()]
    files = [ROOT / name for name in sorted(set(names))]
    if any(not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to((ROOT / WORK).resolve()) for p in files):
        raise ValueError('Transfer only actual contained CPU-proof files')
    return files


def validate_inputs():
    verify_implementation()
    verify_corpus()
    cfg = load_config(DEFAULT_CONFIG)
    require_acquisition_freeze(cfg)
    token_audit_valid(cfg)
    capability_valid(cfg)
    source = git_provenance()
    if not source['commit'] or source['modified_tracked_files']:
        raise ValueError('Use clean, committed main for the handoff')
    return cfg


def prepare(exports):
    cfg = validate_inputs()
    if capability_valid(cfg)['environment'] != environment():
        raise ValueError('Prepare the transfer on the accepted laptop CPU environment')
    files = files_for_transfer(cfg)
    receipt = {'core_contract': corpus_contract(), 'files': {str(p.relative_to(ROOT)): file_digest(p) for p in files},
               'contains_credentials': False, 'contains_model_weights': False,
               'assessor_calibration_required_for_sealed_Q': False}
    manifest = ROOT / WORK / 'q-transfer-manifest.json'
    write_json(manifest, receipt)
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    exports.mkdir(parents=True, exist_ok=True)
    archive = exports / f'rq1-q-inputs-{stamp}.tgz'
    with tarfile.open(archive, 'x:gz') as tar:
        for p in [*files, manifest]:
            tar.add(p, arcname=str(p.relative_to(ROOT)), recursive=False)
    archive.with_suffix('.tgz.sha256').write_text(file_digest(archive) + '  ' + archive.name + '\n')
    result = {'archive': str(archive), 'sha256': file_digest(archive), 'files': len(files),
              'next': 'Return this summary; pause before VM transfer. No model weights loaded.'}
    write_json(archive.with_suffix('.summary.json'), result)
    return result


def inspect_vm():
    cfg = validate_inputs()
    receipt = json.loads((ROOT / WORK / 'q-transfer-manifest.json').read_text())
    expected = {str(p.relative_to(ROOT)): file_digest(p) for p in files_for_transfer(cfg)}
    if receipt.get('core_contract') != corpus_contract() or receipt.get('files') != expected:
        raise ValueError('Q transfer manifest or scientific source contract differs')
    if not doctor('gpu', DEFAULT_CONFIG, ROOT / WORK / 'gpu-doctor'):
        raise ValueError('GPU technical inspection failed; no Q weights loaded')
    import torch
    free = torch.cuda.mem_get_info(0)[0] / 2**30
    if free < 70:
        raise ValueError('Require at least 70 GiB free GPU memory before original Q loading')
    result = {'technical_ready': True, 'free_gpu_GiB': round(free, 2),
              'environment': environment(), 'core_contract': corpus_contract(),
              'model_load_tested': False, 'next': 'Return inspection and pause before Q acquisition.'}
    write_json(ROOT / WORK / 'q-vm-inspection.json', result)
    return result


def main():
    os.chdir(ROOT)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'inspect'))
    p.add_argument('--exports', type=Path, default=Path('/mnt/d/Dissertation-RQ1/exports'))
    a = p.parse_args()
    print(json.dumps(prepare(a.exports) if a.action == 'prepare' else inspect_vm(), indent=2))


if __name__ == '__main__':
    main()
