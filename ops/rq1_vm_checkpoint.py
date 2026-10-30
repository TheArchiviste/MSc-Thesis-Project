"""Prepare accepted inputs on CPU, then inspect the existing VM without loading Q."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from evidence_experiment.locks import environment, git_provenance, now, require_witnesses
from evidence_experiment.schema import file_digest, load_cases, read_jsonl, write_json

MODEL = 'Qwen/Qwen2.5-32B-Instruct'
REVISION = '5ede1c97bbab6ce5cda5812749b4c0bdf79b18dd'
WORK = Path('work/rq1-v6')


def plan():
    return {'model': MODEL, 'revision': REVISION, 'dtype': 'bfloat16', 'max_model_len': 8192,
            'max_num_seqs': 1, 'seed': 0, 'gpu_memory_utilization': .85, 'enforce_eager': True,
            'host': '127.0.0.1', 'port': 8001, 'vllm': '0.6.6.post1',
            'maximum_response_tokens': 3072, 'quantization': None,
            'limit': 'Candidate assessor; real load and 12-anchor source-checked calibration are still required.'}


def profile():
    return {'provider': 'Self-hosted vLLM on Nebius H100 VM', 'model': MODEL,
            'revision_note': f'HF {REVISION}; BF16; vLLM 0.6.6.post1; seed=0; context=8192; one sequence; eager mode; no quantization.',
            'chat_completions_url': 'http://127.0.0.1:8001/v1/chat/completions',
            'api_key_env': '', 'temperature': 0., 'max_tokens': 3072, 'timeout_seconds': 180}


def server_command(python):
    return [python, '-m', 'vllm.entrypoints.openai.api_server', '--model', MODEL,
            '--revision', REVISION, '--tokenizer-revision', REVISION,
            '--host', '127.0.0.1', '--port', '8001', '--dtype', 'bfloat16',
            '--max-model-len', '8192', '--max-num-seqs', '1', '--seed', '0',
            '--gpu-memory-utilization', '0.85', '--tensor-parallel-size', '1',
            '--enforce-eager', '--disable-log-requests']


def write_unchanged(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f'Preserving a differing file: {path}')
    else:
        write_json(path, value, exclusive=True)


def audit_requests(rows, tokenizer):
    from rq1.judge import validate_request
    records = []
    for row in rows:
        validate_request(row)
        tokens = tokenizer.apply_chat_template(row['messages'], tokenize=True, add_generation_prompt=True)
        n = len(tokens)
        records.append({'request_id': row['request_id'], 'request_sha256': row['request_sha256'],
                        'prompt_tokens': n, 'maximum_response_tokens': 3072, 'fits': n + 3072 <= 8192})
    if len(records) != 12 or len({r['request_id'] for r in records}) != 12 or not all(r['fits'] for r in records):
        raise ValueError('All 12 complete calibration requests must fit without truncation')
    return {'model': MODEL, 'revision': REVISION, 'max_model_len': 8192, 'records': records,
            'meaning': 'CPU tokenizer only; no model weights, responses or grades.'}


def selected_files(root):
    paths = [WORK / name for name in (
        'config.json', 'token-audit.json', 'joern-capability',
        'development/witness_validation.jsonl', 'main/witness_validation.jsonl',
        'calibration/public/packets.jsonl', 'calibration/public/requests.jsonl', 'assessor.vm.json', 'assessor.vm-plan.json', 'assessor.vm-token-audit.json')]
    files = []
    for rel in paths:
        path = root / rel
        if not path.exists():
            raise FileNotFoundError(path)
        entries = sorted(path.rglob('*')) if path.is_dir() else [path]
        for entry in entries:
            if entry.is_symlink():
                raise ValueError('Do not package symlinks or external storage targets')
            if entry.is_file() and entry.name != '.run.lock':
                files.append(entry.relative_to(root))
    return sorted(set(files))


def create_archive(root, exports, core_contract):
    files = selected_files(root)
    manifest = {'utc': now(), 'source_commit': git_provenance()['commit'], 'core_contract': core_contract,
                'files': {str(p): file_digest(root / p) for p in files},
                'contains_model_weights': False, 'contains_private_answer_key': False,
                'purpose': 'VM technical inspection and later public calibration requests; no Q acquisition authorization.'}
    manifest_path = WORK / 'vm-inputs-manifest.json'
    write_json(root / manifest_path, manifest)
    exports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    fd, name = tempfile.mkstemp(prefix=f'rq1-vm-inputs-{stamp}-', suffix='.tgz', dir=exports)
    os.close(fd)
    archive = Path(name)
    with tarfile.open(archive, 'w:gz') as tar:
        for rel in [*files, manifest_path]:
            tar.add(root / rel, arcname=str(rel), recursive=False)
    archive.with_suffix(archive.suffix + '.sha256').write_text(file_digest(archive) + '  ' + archive.name + '\n')
    return archive, manifest


def verify_manifest(root):
    from rq1.setup import corpus_contract
    manifest = json.loads((root / WORK / 'vm-inputs-manifest.json').read_text())
    if manifest.get('core_contract') != corpus_contract():
        raise ValueError('Transferred inputs and the checked-out scientific core differ')
    expected = {str(p) for p in selected_files(root)}
    if set(manifest.get('files', {})) != expected:
        raise ValueError('The transfer manifest is incomplete or contains foreign files')
    for rel, expected_sha in manifest['files'].items():
        path = Path(rel)
        if path.is_absolute() or '..' in path.parts or file_digest(root / path) != expected_sha:
            raise ValueError(f'Transfer changed or unsafe path: {rel}')
    if (json.loads((root / WORK / 'assessor.vm-plan.json').read_text()) != plan() or
            json.loads((root / WORK / 'assessor.vm.json').read_text()) != profile()):
        raise ValueError('Assessor model/settings differ from the prepared candidate')
    return manifest


def prepare():
    from rq1.setup import (
        CORPUS,
        DEFAULT_CONFIG,
        ROOT,
        capability_valid,
        corpus_contract,
        load_config,
        token_audit_valid,
        verify_corpus,
        verify_implementation,
    )
    verify_corpus()
    verify_implementation()
    cfg = load_config(DEFAULT_CONFIG)
    if git_provenance()['modified_tracked_files']:
        raise ValueError('Prepare the bundle from a clean committed checkout')
    token_audit_valid(cfg)
    cap = capability_valid(cfg)
    if cap['environment'] != environment():
        raise ValueError('Use the accepted laptop CPU Python environment without installing new packages')
    for split in ('development', 'main'):
        require_witnesses(ROOT / WORK / split, load_cases(CORPUS / f'{split}.jsonl'))
    if any((ROOT / WORK / 'calibration' / n).exists() for n in ('responses.jsonl', 'assessments.initial.jsonl', 'acceptance.json')):
        raise ValueError('Preserve existing assessor acquisition; inspect before changing its backend')
    exports = Path('/mnt/d/Dissertation-RQ1/exports')
    if not exports.is_dir():
        raise ValueError('Run in the existing D-backed Ubuntu environment')
    os.environ['HF_HOME'] = '/mnt/d/Dissertation-RQ1/huggingface'
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, trust_remote_code=False)
    audit = audit_requests(read_jsonl(ROOT / WORK / 'calibration/public/requests.jsonl'), tokenizer)
    write_unchanged(ROOT / WORK / 'assessor.vm.json', profile())
    write_unchanged(ROOT / WORK / 'assessor.vm-plan.json', plan())
    write_unchanged(ROOT / WORK / 'assessor.vm-token-audit.json', audit)
    archive, manifest = create_archive(ROOT, exports, corpus_contract())
    summary = {'CPU_preparation_passed': True, 'candidate_assessor': MODEL, 'revision': REVISION,
               'calibration_prompts_fit': len(audit['records']),
               'maximum_prompt_tokens': max(r['prompt_tokens'] for r in audit['records']),
               'archive': str(archive), 'sha256': file_digest(archive), 'files': len(manifest['files']),
               'archive_MiB': round(archive.stat().st_size / 2**20, 2),
               'weights_downloaded': False, 'VM_started': False,
               'next_step': 'Return this summary; wait before starting the VM.'}
    write_json(archive.with_suffix('.summary.json'), summary)
    print(json.dumps(summary, indent=2))
    print('RQ1_VM_INPUTS_PREPARED — keep the VM stopped and return the summary output.')


def inspect_vm():
    from rq1.setup import DEFAULT_CONFIG, ROOT, doctor, load_config, verify_implementation
    verify_implementation()
    manifest = verify_manifest(ROOT)
    provenance = git_provenance()
    if provenance['modified_tracked_files']:
        raise ValueError('Use a clean committed checkout')
    load_config(DEFAULT_CONFIG)
    work = ROOT / WORK / 'vm-preflight'
    technical = doctor('gpu', DEFAULT_CONFIG, work)
    import importlib.metadata
    versions = {p: importlib.metadata.version(p) for p in ('vllm', 'torch', 'transformers')}
    stack = (versions['vllm'] == '0.6.6.post1' and versions['torch'].split('+')[0] == '2.5.1'
             and versions['transformers'] == '4.47.1' and sys.version_info[:2] == (3, 11))
    cache = Path(os.environ.get('HF_HOME', Path.home() / 'rq1-storage/huggingface'))
    cache.mkdir(parents=True, exist_ok=True)
    free_gib = shutil.disk_usage(cache).free / 2**30
    result = {'utc': now(), 'technical_ready': technical and stack, 'versions': versions,
              'python': sys.version, 'environment': environment(), 'core_contract': manifest['core_contract'],
              'cache_path': str(cache), 'free_GiB': round(free_gib, 1),
              'weights_estimate_each_GiB': 61.1,
              'storage_note': 'Two BF16 checkpoints need about 122 GiB of weights plus download/runtime headroom; inspect available disk before downloading.',
              'model_load_tested': False, 'calibration_accepted': False, 'provenance': provenance}
    write_json(work / 'vm-preflight.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in {'environment', 'core_contract'}}, indent=2))
    if not result['technical_ready']:
        raise SystemExit('VM technical inspection is blocked; no model was loaded')
    print('RQ1_VM_TECHNICAL_INSPECTION_OK — pause before model download/load.')


def serve_assessor():
    from rq1.setup import ROOT, corpus_contract
    verify_manifest(ROOT)
    if git_provenance()['modified_tracked_files']:
        raise ValueError('Serve the assessor from a clean committed checkout')
    receipt = json.loads((ROOT / WORK / 'vm-preflight/vm-preflight.json').read_text())
    if (not receipt.get('technical_ready') or receipt['environment'] != environment() or
            receipt['core_contract'] != corpus_contract()):
        raise ValueError('Current VM technical inspection and unchanged packages are required')
    import torch
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] / 2**30 < 70:
        raise ValueError('Need the H100 available with at least 70 GiB free; unload other model processes first')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', 8001)) == 0:
            raise ValueError('Port 8001 is already occupied; inspect the existing service')
    command = server_command(sys.executable)
    write_json(ROOT / WORK / 'assessor-server-command.json', {'utc': now(), 'command': command, 'plan': plan(), 'environment': environment()})
    # Runs in the foreground; Ctrl-C stops this owned server. No public port is opened.
    subprocess.run(command, check=True)


def main():
    raise SystemExit('Historical v1/v2 assessor route. Current v3 uses ops.rq1_api_calibration for grading and ops.rq1_q_handoff for Q. No model or paid request was started.')


def historical_main():
    from rq1.setup import ROOT
    os.chdir(ROOT)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'inspect', 'serve-assessor'))
    args = p.parse_args()
    {'prepare': prepare, 'inspect': inspect_vm, 'serve-assessor': serve_assessor}[args.action]()


if __name__ == '__main__':
    main()
