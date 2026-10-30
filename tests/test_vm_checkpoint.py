"""CPU-only VM handoff, private-key exclusion and pinned single-model serving."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from evidence_experiment.schema import write_json
from ops.rq1_vm_checkpoint import (
    MODEL,
    REVISION,
    WORK,
    audit_requests,
    create_archive,
    plan,
    profile,
    selected_files,
    server_command,
    verify_manifest,
)
from rq1.assessment_protocol import public_packet, request_for


def tree(tmp_path):
    for name in ('config.json', 'token-audit.json', 'joern-capability/readiness.json',
                 'development/witness_validation.jsonl', 'main/witness_validation.jsonl',
                 'calibration/public/requests.jsonl', 'calibration/public/packets.jsonl'):
        path = tmp_path / WORK / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}\n')
    write_json(tmp_path / WORK / 'assessor.vm.json', profile())
    write_json(tmp_path / WORK / 'assessor.vm-plan.json', plan())
    write_json(tmp_path / WORK / 'assessor.vm-token-audit.json', {})
    private = tmp_path / WORK / 'calibration/private/answer_key.jsonl'
    private.parent.mkdir(); private.write_text('PRIVATE-KEY-MUST-NOT-TRANSFER')
    (tmp_path / WORK / 'calibration/public/accidental-secret.json').write_text('DO-NOT-PACKAGE')


def test_bundle_manifest_and_checksum_are_portable_and_exclude_private_keys(tmp_path, monkeypatch):
    from rq1 import setup
    tree(tmp_path)
    monkeypatch.setattr(setup, 'corpus_contract', lambda: {'test-fixture': 'only'})
    archive, manifest = create_archive(tmp_path, tmp_path / 'exports', setup.corpus_contract())
    assert verify_manifest(tmp_path) == manifest
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert all(n.startswith('work/rq1-v5/') and '..' not in Path(n).parts for n in names)
        assert not any('private' in n or 'answer_key' in n or 'accidental-secret' in n for n in names)
        assert any(n.endswith('calibration/public/requests.jsonl') for n in names)
    checksum = archive.with_suffix('.tgz.sha256').read_text()
    assert checksum.endswith('  ' + archive.name + '\n') and '/mnt/' not in checksum
    assert not manifest['contains_model_weights'] and not manifest['contains_private_answer_key']


def test_edited_transfer_file_is_rejected(tmp_path, monkeypatch):
    from rq1 import setup
    tree(tmp_path)
    monkeypatch.setattr(setup, 'corpus_contract', lambda: {'test': True})
    create_archive(tmp_path, tmp_path / 'exports', setup.corpus_contract())
    (tmp_path / WORK / 'token-audit.json').write_text('changed')
    with pytest.raises(ValueError, match='Transfer changed'):
        verify_manifest(tmp_path)


def test_symlink_cannot_add_external_secrets(tmp_path):
    tree(tmp_path)
    secret = tmp_path / 'external-secret'; secret.write_text('secret')
    (tmp_path / WORK / 'joern-capability/leak').symlink_to(secret)
    with pytest.raises(ValueError, match='symlinks'):
        selected_files(tmp_path)


def requests_fixture():
    return [request_for(public_packet('Does the excerpt justify a flaw?', f'L1: int n{i};')) for i in range(12)]


def test_actual_public_requests_are_audited_with_output_reserve():
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            assert len(messages) == 2 and kwargs == {'tokenize': True, 'add_generation_prompt': True}
            return [1] * 2000
    result = audit_requests(requests_fixture(), Tokenizer())
    assert len(result['records']) == 12 and all(r['fits'] for r in result['records'])
    assert result['revision'] == REVISION


def test_overlong_calibration_request_is_never_truncated():
    class Tokenizer:
        def apply_chat_template(self, *a, **kw):
            return [1] * 6000
    with pytest.raises(ValueError, match='without truncation'):
        audit_requests(requests_fixture(), Tokenizer())


def test_server_is_private_single_model_and_revision_pinned():
    command = server_command('python')
    assert command[command.index('--model')+1] == MODEL
    assert command[command.index('--revision')+1] == REVISION
    assert command[command.index('--tokenizer-revision')+1] == REVISION
    assert command[command.index('--host')+1] == '127.0.0.1'
    assert command[command.index('--max-num-seqs')+1] == '1'
    assert '--enforce-eager' in command and '--quantization' not in command
    assert 'qcri/llmxcpg-q' not in json.dumps(command).lower()
