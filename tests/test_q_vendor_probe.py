"""Metadata-discovery apparatus tests; no model or experimental query is executed."""
from __future__ import annotations

import sys

import pytest

from ops import rq1_q_vendor_probe as probe


def distribution(directory, name, version):
    metadata_dir = directory / f'{name}-{version}.dist-info'
    metadata_dir.mkdir(parents=True)
    (metadata_dir / 'METADATA').write_text(
        f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n')


def test_both_bundles_are_required_and_upstream_path_order_is_preserved(tmp_path, monkeypatch):
    primary = tmp_path / 'primary'
    setuptools = tmp_path / 'setuptools-vendor'
    ray = tmp_path / 'ray-thirdparty'
    distribution(primary, 'probe-shared', '10.0')
    distribution(setuptools, 'probe-shared', '2.0')
    distribution(setuptools, 'probe-setuptools-only', '1.0')
    distribution(ray, 'probe-shared', '3.0')
    distribution(ray, 'probe-ray-only', '1.0')
    monkeypatch.setattr(sys, 'path', [str(primary), *sys.path])
    original_path = sys.path[:]
    original_inventory = probe.environment()

    setuptools_only, combined = probe.expose_metadata_paths(setuptools, ray)

    assert 'probe-ray-only' not in setuptools_only['packages']
    assert combined['packages']['probe-ray-only'] == '1.0'
    assert combined['packages']['probe-setuptools-only'] == '1.0'
    # The frozen recorder keeps the last duplicate. Ray's prepended copy must not
    # overwrite the normal or Setuptools copies later in the enumeration.
    assert original_inventory['packages']['probe-shared'] == '10.0'
    assert setuptools_only['packages']['probe-shared'] == '2.0'
    assert combined['packages']['probe-shared'] == '2.0'
    assert combined != setuptools_only
    assert sys.path == original_path
    assert probe.environment() == original_inventory


def test_metadata_paths_are_restored_after_discovery_failure(tmp_path, monkeypatch):
    original_path = sys.path[:]
    count = 0

    def failing_discovery():
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('Synthetic metadata-read failure')
        return {'packages': {}}

    monkeypatch.setattr(probe, 'environment', failing_discovery)
    with pytest.raises(OSError, match='Synthetic metadata-read failure'):
        probe.expose_metadata_paths(tmp_path / 'setuptools', tmp_path / 'ray')
    assert sys.path == original_path
