"""Prepare/check one v3 API calibration; execution is an explicit paid checkpoint."""
from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from evidence_experiment.locks import git_provenance, now, work_lock
from evidence_experiment.schema import file_digest, read_jsonl, write_json
from rq1.calibration import prepare
from rq1.judge import execute, import_responses, validate_request
from rq1.providers import headers, validate_profile, wire_request
from rq1.setup import CORPUS, DEFAULT_CONFIG, ROOT, load_config


def inspect(config, *, check_access=False):
    cfg = load_config(config)
    root = prepare(config)
    profile = json.loads((CORPUS / 'assessor.example.json').read_text())
    validate_profile(profile)
    requests = read_jsonl(root / 'public/requests.jsonl')
    if len(requests) != 20:
        raise ValueError('Use the exact 20 predeclared v3 anchors')
    for request in requests:
        validate_request(request)
    profile_path = root / 'assessor.json'
    if profile_path.exists() and json.loads(profile_path.read_text()) != profile:
        raise ValueError('Preserve the old assessor profile; do not replace it')
    write_json(profile_path, profile)
    # Conservative planning bound at the documented Standard rates (2026-10-30).
    # It is not a provider-enforced billing cap and does not include tax/FX.
    wire_bytes = sum(len(json.dumps(wire_request(r, profile)[1]).encode()) for r in requests)
    cost = ((wire_bytes + len(requests) * 4096) * 12.5 +
            len(requests) * profile['max_output_tokens'] * 50) / 1_000_000
    result = {'utc': now(), 'model': profile['model'], 'reasoning_effort': profile['reasoning_effort'],
        'requests': len(requests), 'development': 12, 'fresh_heldout': 8,
        'max_output_tokens_per_request_including_reasoning': profile['max_output_tokens'],
        'planning_upper_estimate_usd': round(cost, 2),
        'pricing_basis': '2026-10-30 Standard: $10/M input ($12.50/M cache-write rate used conservatively), $50/M output including reasoning; no tools. Input estimate uses wire bytes plus 4096 tokens/request. Not an enforceable billing cap; verify current rates/account funding before run.',
        'pricing_source': 'https://developers.openai.com/api/docs/models/gpt-6-astra',
        'api_key_present': bool(os.environ.get('OPENAI_API_KEY')),
        'inference_requests': 0, 'api_access_checked': False,
        'prior_attempt_present': any((root / n).exists() for n in
            ('acquisition-started.json', 'responses.jsonl', 'responses.errors.jsonl')),
        'acquisition_freeze_present': (ROOT / cfg['rq1_acquisition_freeze_file']).exists()}
    if check_access:
        import requests as http
        try:
            response = http.get('https://api.openai.com/v1/models/' + profile['model'],
                                headers=headers(profile), timeout=30)
            result['api_access_checked'] = True
            result['access_http_status'] = response.status_code
            result['model_listed'] = response.status_code == 200 and response.json().get('id') == profile['model']
        except Exception as exc:  # noqa: BLE001 - never expose credential-bearing transport errors
            result['access_error_type'] = type(exc).__name__
        result['billing_and_generation_access'] = 'not established by a read-only model lookup'
    write_json(root / 'api-inspection.json', result)
    return root, result


def run(config, exports):
    root, inspected = inspect(config)
    if inspected['prior_attempt_present']:
        raise ValueError('A prior acquisition exists. Preserve it; no automatic retry or second candidate')
    profile = json.loads((root / 'assessor.json').read_text())
    headers(profile)  # Validate presence without printing or persisting credentials.
    provenance = git_provenance()
    if not provenance['commit'] or provenance['modified_tracked_files']:
        raise ValueError('Use a clean, committed checkout for real assessment')
    if inspected['planning_upper_estimate_usd'] > 30:
        raise ValueError('Planning estimate exceeds the declared $30 calibration ceiling; pause before any request')
    access = json.loads((root / 'api-access.json').read_text())
    if (access.get('model_listed') is not True or access.get('inference_requests') != 0 or
            access.get('profile_sha256') != file_digest(root / 'assessor.json')):
        raise ValueError('Return and accept the read-only access checkpoint before paid calibration')
    write_json(root / 'acquisition-started.json', {'utc': now(), 'provenance': provenance,
        'requests_sha256': file_digest(root / 'public/requests.jsonl'),
        'profile_sha256': file_digest(root / 'assessor.json'), 'one_predeclared_attempt': True}, exclusive=True)
    status, error, stage = 'blocked', None, 'acquisition'
    try:
        execute(root / 'public/requests.jsonl', root / 'assessor.json', root / 'responses.jsonl')
        stage = 'strict_import'
        import_responses(root / 'public/requests.jsonl', root / 'responses.jsonl', root / 'assessments.initial.jsonl')
        status = 'acquired_and_imported_pending_source_audit'
    except Exception as exc:  # noqa: BLE001 - original records remain immutable, no error bodies/keys exported
        error = type(exc).__name__
    try:
        saved = read_jsonl(root / 'responses.jsonl')
        count = len(saved)
    except (ValueError, OSError):
        saved, count = [], 'unreadable; preserved verbatim'
    usages = [r.get('response_metadata', {}).get('usage') for r in saved]
    usages = [u for u in usages if isinstance(u, dict)]
    usage = {'input_tokens': sum(u.get('input_tokens', 0) or 0 for u in usages),
             'output_tokens_including_reasoning': sum(u.get('output_tokens', 0) or 0 for u in usages),
             'responses_with_usage': len(usages),
             'limit': 'Only returned usage is known; a transport failure may incur additional unreported usage.'}
    summary = {'utc': now(), 'status': status, 'error_type': error, 'stage': stage,
               'saved_responses': count, 'reported_usage': usage,
               'calibration_accepted': False, 'next': 'Return the archive for the separate source-proof audit. No automatic retries.'}
    write_json(root / 'session-summary.json', summary)
    exports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    archive = exports / f'rq1-assessor-v3-{stamp}.zip'
    names = ('bank.json', 'assessor.json', 'api-inspection.json', 'api-access.json', 'acquisition-started.json',
             'session-summary.json', 'responses.jsonl', 'responses.errors.jsonl', 'assessments.initial.jsonl',
             'assessments.initial.provenance.json', 'source_audit.template.jsonl',
             'public/README.md', 'public/packets.jsonl', 'public/requests.jsonl', 'private/answer_key.jsonl')
    files = [root / name for name in names if (root / name).is_file()]
    if any(p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) for p in files):
        raise ValueError('Export actual calibration artifacts, never symlink targets')
    manifest = root / 'export-manifest.json'
    write_json(manifest, {'files': {str(p.relative_to(root)): file_digest(p) for p in files}}, exclusive=True)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in [*files, manifest]:
            zipped.write(path, arcname=str(Path('calibration') / path.relative_to(root)))
    archive.with_suffix('.zip.sha256').write_text(file_digest(archive) + '  ' + archive.name + '\n')
    print(json.dumps(summary, indent=2))
    print(f'RETURN_ARCHIVE: {archive}')
    return status != 'blocked'


def main():
    os.chdir(ROOT)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('inspect', 'access', 'run'))
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    p.add_argument('--exports', type=Path, default=Path('/mnt/d/Dissertation-RQ1/exports'))
    a = p.parse_args()
    cfg = load_config(a.config)
    with work_lock((ROOT / cfg['rq1_calibration_file']).parent):
        if a.action == 'run':
            if not run(a.config, a.exports):
                raise SystemExit(1)
        else:
            root, result = inspect(a.config, check_access=a.action == 'access')
            if a.action == 'access':
                result['profile_sha256'] = file_digest(root / 'assessor.json')
                # A returned access receipt is still only technical access, never calibration.
                write_json(root / 'api-access.json', result)
            print(json.dumps(result, indent=2))
            if a.action == 'access' and not result.get('model_listed'):
                raise SystemExit(1)


if __name__ == '__main__':
    main()
