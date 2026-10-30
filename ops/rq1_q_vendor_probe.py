"""Prove or reject the vendor-path explanation without importing Q or changing its records."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence_experiment.locks import environment
from ops.rq1_q_diagnose import digest, provenance_checks
from rq1.setup import DEFAULT_CONFIG, corpus_contract, load_config, require_acquisition_freeze

PROTOCOL = 'rq1-v7-bundled-metadata-probe-v2'


class ProbeBlocked(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ProbeBlocked(code)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def distribution_manifest(path=None):
    distributions = metadata.distributions() if path is None else metadata.distributions(path=[str(path)])
    rows = []
    for distribution in distributions:
        name = distribution.metadata.get('Name')
        if name:
            rows.append({'name': name.lower().replace('_', '-'), 'version': distribution.version,
                         'metadata_sha256': hashlib.sha256((distribution.read_text('METADATA') or '').encode()).hexdigest()})
    return sorted(rows, key=lambda row: (row['name'], row['version'] or '', row['metadata_sha256']))


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024,
            'invalid_metadata_file')
    return json.loads(path.read_text())


def work_hashes(work):
    result = {}
    for path in sorted(work.rglob('*')):
        require(not path.is_symlink(), 'symlink_in_original_work')
        if path.is_file():
            result[path.relative_to(work).as_posix()] = digest(path)
    return result


def expose_metadata_paths(setuptools_vendor, ray_thirdparty):
    """Reproduce upstream path registration, without importing either library."""
    saved_path = sys.path[:]
    try:
        sys.path.append(str(setuptools_vendor))
        setuptools_only = environment()
        sys.path.insert(0, str(ray_thirdparty))
        combined = environment()
    finally:
        sys.path[:] = saved_path
    return setuptools_only, combined


def probe(work, archive, expected_archive, expected_receipt):
    require(digest(archive) == expected_archive, 'original_archive_checksum_mismatch')
    require_acquisition_freeze(load_config(DEFAULT_CONFIG))
    inspected_path = work.parent / 'q-vm-inspection.json'
    require(digest(inspected_path) == expected_receipt, 'accepted_inspection_receipt_mismatch')
    inspected = read_json(inspected_path)
    lock = read_json(work / 'experiment_lock.json')
    marker = read_json(work / 'q-wrapper-started.json')
    require(marker.get('Q_host_receipt_sha256') == expected_receipt, 'attempt_inspection_binding_mismatch')
    require(inspected.get('technical_ready') is True and
            inspected.get('core_contract') == lock.get('acquisition_contract') == corpus_contract(),
            'acquisition_contract_mismatch')
    require(not (work / 'query.seal.json').exists() and not (work / 'stage_receipts.json').exists(),
            'stage_already_receipted_or_sealed')
    records = {}
    for name in ('queries.jsonl', 'query_sessions.jsonl', 'query_load_errors.jsonl', 'query_runtime_errors.jsonl'):
        path = work / name
        if not path.exists():
            records[name] = []
            continue
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024,
                'invalid_record_file')
        records[name] = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    require(len(records['query_sessions.jsonl']) == 1 and len(records['queries.jsonl']) == 6,
            'unexpected_query_or_session_count')
    require(not records['query_load_errors.jsonl'] and not records['query_runtime_errors.jsonl'],
            'query_errors_present')
    require(provenance_checks(records, lock)['failed_checks'] == ['runtime_matches_stage_lock'],
            'different_provenance_failure')
    before = environment()
    recorded = records['query_sessions.jsonl'][0]['runtime']
    require(before == lock['stage_environments']['query'] == inspected['environment'],
            'current_installed_inventory_differs')
    original_hashes = work_hashes(work)
    physical_before = distribution_manifest()
    vendor = Path(metadata.distribution('setuptools').locate_file('setuptools/_vendor')).resolve()
    ray_root = Path(metadata.distribution('ray').locate_file('ray')).resolve()
    ray_thirdparty = ray_root / 'thirdparty_files'
    require(all(path.is_dir() and str(path) not in sys.path for path in (vendor, ray_thirdparty)),
            'bundled_path_not_separate')
    ray_init = ray_root / '__init__.py'
    require('sys.path.insert(0, thirdparty_files)' in ray_init.read_text() and
            '"thirdparty_files"' in ray_init.read_text(), 'ray_path_registration_unverified')
    vendor_manifest = {'setuptools_vendor': distribution_manifest(vendor),
                       'ray_thirdparty': distribution_manifest(ray_thirdparty)}
    require(all(vendor_manifest.values()), 'bundled_metadata_absent')
    setuptools_only, exposed = expose_metadata_paths(vendor, ray_thirdparty)
    restored = environment()
    physical_after = distribution_manifest()
    unchanged = original_hashes == work_hashes(work)
    require(unchanged and digest(archive) == expected_archive, 'original_files_changed')
    checks = {
        'current_inventory_matches_accepted': True,
        'bundled_paths_exactly_reproduce_recorded_runtime': exposed == recorded,
        'restoring_path_restores_accepted_inventory': restored == before,
        'installed_metadata_unchanged_during_probe': physical_before == physical_after,
        'original_records_and_archive_unchanged': unchanged,
    }
    return {
        'protocol': PROTOCOL,
        'utc': datetime.now(UTC).isoformat(), 'probe_passed': all(checks.values()), 'checks': checks,
        'model_loaded': False, 'generation_repeated': False, 'query_record_count': 6,
        'original_archive_sha256': expected_archive, 'original_file_hashes': original_hashes,
        'accepted_inspection_receipt_sha256': expected_receipt,
        'acquisition_contract_sha256': canonical_digest(corpus_contract()),
        'probe_code_sha256': digest(Path(__file__)),
        'stage_inventory_sha256': canonical_digest(before),
        'recorded_session_inventory_sha256': canonical_digest(recorded),
        'exposed_inventory_sha256': canonical_digest(exposed),
        'installed_metadata_manifest_sha256': canonical_digest(physical_before),
        'vendor_metadata': vendor_manifest,
        'bootstrap_source_sha256': {'setuptools': digest(vendor.parent / '__init__.py'),
                                   'ray': digest(ray_init)},
        'setuptools_only_unexplained_package_names': sorted(
            k for k in set(setuptools_only['packages']) | set(recorded['packages'])
            if setuptools_only['packages'].get(k) != recorded['packages'].get(k)),
        'changed_package_count': sum(before['packages'].get(k) != recorded['packages'].get(k)
                                     for k in set(before['packages']) | set(recorded['packages'])),
        'unexplained_package_names': sorted(k for k in set(exposed['packages']) | set(recorded['packages'])
                                            if exposed['packages'].get(k) != recorded['packages'].get(k)),
        'instruction': 'Retain the proof privately. Original records are unchanged; review before metadata reconciliation.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('archive_sha256')
    parser.add_argument('inspection_receipt_sha256')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    require(all(re.fullmatch(r'[a-f0-9]{64}', value) for value in
                (args.archive_sha256, args.inspection_receipt_sha256)), 'invalid_checksum_argument')
    work = ROOT / 'work/rq1-v7/development'
    try:
        # Read-lock the existing acquisition directory; do not start a collector.
        with (work / '.run.lock').open('rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = probe(work, args.archive, args.archive_sha256, args.inspection_receipt_sha256)
    except ProbeBlocked as exc:
        result = {'protocol': PROTOCOL, 'probe_passed': False,
                  'blocked_check': str(exc), 'model_loaded': False, 'generation_repeated': False}
    except Exception as exc:  # noqa: BLE001 - record only the failure class; private data stays hidden
        result = {'protocol': PROTOCOL, 'probe_passed': False,
                  'blocked_check': 'probe_infrastructure_failure', 'exception_category': type(exc).__name__,
                  'model_loaded': False, 'generation_repeated': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    summary = {key: result[key] for key in ('protocol', 'probe_passed', 'checks', 'blocked_check',
               'model_loaded', 'generation_repeated', 'query_record_count', 'changed_package_count',
               'original_archive_sha256', 'unexplained_package_names') if key in result}
    summary.update(proof_sha256=digest(args.output), proof=str(args.output))
    with args.output.with_suffix('.summary.json').open('x') as stream:
        json.dump(summary, stream, indent=2)
        stream.write('\n')
    print(json.dumps(summary, indent=2))
    if not result['probe_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
