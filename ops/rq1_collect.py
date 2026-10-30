"""Run one sealed Q/Joern stage, report safe progress and export an unopened bundle."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from evidence_experiment.schema import file_digest, read_jsonl, write_json
from rq1.setup import DEFAULT_CONFIG, ROOT, load_config


def collect(phase, split, exports):
    cfg = load_config(DEFAULT_CONFIG)
    work = (ROOT / cfg['rq1_calibration_file']).parent.parent / split
    expected = 6 if split == 'development' else 24
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    work.mkdir(parents=True, exist_ok=True)
    log = work / f'collection-{phase}-{stamp}.log'
    command = [sys.executable, '-u', '-m', 'evidence_experiment', phase, '--split', split, '--sealed']
    name = 'queries.jsonl' if phase == 'query' else 'slices.jsonl'
    with log.open('x') as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        while True:
            try:
                code = process.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                try:
                    count = len(read_jsonl(work / name))
                except (ValueError, OSError):
                    count = 'write in progress'
                print(f'RQ1 sealed {split} {phase}: {count}/{expected} records; process running; content stays in private logs', flush=True)
    seal = work / f'{phase}.seal.json'
    summary = {'split': split, 'phase': phase, 'exit_code': code, 'expected_records': expected,
               'acquisition_sealed': code == 0 and seal.is_file(),
               'seal_sha256': file_digest(seal) if seal.is_file() else None,
               'instruction': 'Return only this summary while assessment is pending. Transfer the archive programmatically; do not open or upload its contents for assessor development.'}
    exports.mkdir(parents=True, exist_ok=True)
    archive = exports / f'rq1-sealed-{split}-{phase}-{stamp}.tgz'
    # The operator may need the failed raw artifacts for a separately declared diagnosis.
    # Preserve every file without displaying outcomes or filtering successful cases.
    with tarfile.open(archive, 'x:gz') as tar:
        for path in sorted(work.rglob('*')):
            if path.is_file():
                if path.is_symlink():
                    raise ValueError('Do not package symlink targets')
                tar.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    archive.with_suffix('.tgz.sha256').write_text(file_digest(archive) + '  ' + archive.name + '\n')
    summary.update(archive=str(archive), archive_sha256=file_digest(archive))
    write_json(archive.with_suffix('.summary.json'), summary)
    print(json.dumps(summary, indent=2))
    return summary['acquisition_sealed']


def main():
    os.chdir(ROOT)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('query', 'slice'))
    p.add_argument('--split', choices=('development', 'main'), default='development')
    p.add_argument('--exports', type=Path, required=True)
    a = p.parse_args()
    if not collect(a.phase, a.split, a.exports):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
