"""Read-only assessor access checking, immutable profiles and secret-safe errors."""
from __future__ import annotations

import json
from types import SimpleNamespace

from ops.rq1_assessor_preflight import MODEL, PROFILE, preflight


def test_preflight_only_lists_models_and_never_saves_key(tmp_path):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {'data': [{'id': MODEL}]})
    report = preflight('unit-test-secret', tmp_path / 'profile.json', tmp_path / 'report.json', get=get)
    assert report['complete'] and report['inference_requests'] == 0
    assert report['billing_access'] == 'not_tested_by_model_listing'
    assert len(calls) == 1 and calls[0][0].endswith('/models')
    assert json.loads((tmp_path / 'profile.json').read_text()) == PROFILE
    assert 'unit-test-secret' not in (tmp_path / 'report.json').read_text() + (tmp_path / 'profile.json').read_text()


def test_preflight_auth_failure_is_blocked_without_profile(tmp_path):
    report = preflight('unit-test', tmp_path / 'p.json', tmp_path / 'r.json',
        get=lambda *a, **kw: SimpleNamespace(status_code=401))
    assert not report['complete'] and report['http_status'] == 401
    assert not (tmp_path / 'p.json').exists()


def test_missing_selected_model_does_not_choose_a_fallback(tmp_path):
    report = preflight('unit-test', tmp_path / 'p.json', tmp_path / 'r.json',
        get=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {'data': [{'id': 'other'}]}))
    assert not report['complete'] and not (tmp_path / 'p.json').exists()


def test_profile_cannot_be_silently_replaced(tmp_path):
    (tmp_path / 'p.json').write_text(json.dumps({'model': 'previous'}))
    def no_request(*a, **kw):
        raise AssertionError('Should not contact service after a profile mismatch')
    report = preflight('unit-test', tmp_path / 'p.json', tmp_path / 'r.json', get=no_request)
    assert not report['complete']
    assert json.loads((tmp_path / 'p.json').read_text()) == {'model': 'previous'}


def test_transport_error_text_cannot_leak_key(tmp_path):
    def get(*a, **kw):
        raise RuntimeError('echoed-key-test-secret')
    report = preflight('echoed-key-test-secret', tmp_path / 'p.json', tmp_path / 'r.json', get=get)
    assert not report['complete'] and 'echoed-key' not in (tmp_path / 'r.json').read_text()
