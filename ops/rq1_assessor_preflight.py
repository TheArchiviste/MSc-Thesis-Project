"""Check Nebius assessor access without sending prompts or generating tokens."""
from __future__ import annotations

import getpass
import json
import shutil
import sys
from pathlib import Path

import requests

from evidence_experiment.locks import now
from evidence_experiment.schema import write_json

MODEL = 'Qwen/Qwen3-235B-A22B-Instruct-2507'
MODELS_URL = 'https://api.tokenfactory.nebius.com/v1/models'
PROFILE = {
    'provider': 'Nebius Token Factory',
    'model': MODEL,
    'revision_note': 'Dated model ID Instruct-2507; provider serving build revision not_exposed.',
    'chat_completions_url': 'https://api.tokenfactory.nebius.com/v1/chat/completions',
    'api_key_env': 'RQ1_ASSESSOR_API_KEY',
    'temperature': 0.0,
    'max_tokens': 3072,
    'timeout_seconds': 180,
}


def preflight(api_key, profile_path, report_path, *, get=None):
    """No chat completion, private answer key, source bank or credential is written."""
    report = {'utc': now(), 'requested_model': MODEL, 'endpoint': MODELS_URL,
              'complete': False, 'inference_requests': 0, 'grading_status': 'not_started',
              'billing_access': 'not_tested_by_model_listing', 'key_saved': False}
    try:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('A nonempty API key is required')
        if profile_path.exists() and json.loads(profile_path.read_text()) != PROFILE:
            raise ValueError('Existing assessor profile differs; preserve it for inspection')
        response = (get or requests.get)(MODELS_URL,
            headers={'Authorization': 'Bearer ' + api_key.strip()}, timeout=45, allow_redirects=False)
        report['http_status'] = response.status_code
        if response.status_code != 200:
            report['status'] = 'blocked_http_status'
            return report
        data = response.json().get('data')
        if not isinstance(data, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in data):
            raise ValueError('Unexpected model-list schema')
        ids = sorted({r['id'] for r in data})
        report['available_model_ids'] = ids
        report['selected_model_listed'] = MODEL in ids
        if MODEL not in ids:
            report['status'] = 'blocked_selected_model_not_listed'
            return report
        if not profile_path.exists():
            write_json(profile_path, PROFILE, exclusive=True)
        report.update(complete=True, status='model_access_preflight_passed')
        return report
    except Exception as exc:  # noqa: BLE001 - never expose credentials through HTTP exception text
        report.update(status='blocked_preflight_error', error_type=type(exc).__name__)
        return report
    finally:
        write_json(report_path, report)


def main():
    raise SystemExit('Historical v1/v2 assessor route. Current v3 uses ops.rq1_api_calibration for grading and ops.rq1_q_handoff for Q. No model or paid request was started.')


def historical_main():
    from rq1.setup import (
        DEFAULT_CONFIG,
        ROOT,
        capability_valid,
        load_config,
        token_audit_valid,
        verify_implementation,
    )
    cfg = load_config(DEFAULT_CONFIG)
    verify_implementation()
    token_audit_valid(cfg)
    capability_valid(cfg)
    exports = Path('/mnt/d/Dissertation-RQ1/exports')
    if not exports.is_dir():
        raise SystemExit('Use the D-backed Ubuntu terminal with its existing exports folder')
    work = ROOT / 'work/rq1-v6/assessor-preflight'
    profile_path = ROOT / 'work/rq1-v6/assessor.json'
    key = getpass.getpass('Nebius Token Factory API key (hidden; not saved): ')
    report = preflight(key, profile_path, work / 'preflight.json')
    key = None
    if profile_path.exists():
        shutil.copyfile(profile_path, work / 'assessor.json')
    archive = shutil.make_archive(str(exports / ('assessor-preflight-' + now().replace(':', '').split('.')[0])), 'zip', work)
    print(json.dumps({k: v for k, v in report.items() if k != 'available_model_ids'}, indent=2))
    print('Return this ZIP:', archive)
    print('Pause here. No calibration prompts or inference requests were sent.')
    if not report['complete']:
        sys.exit(1)


if __name__ == '__main__':
    main()
