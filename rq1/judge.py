"""One stateless AI request per packet, with immutable raw-response provenance."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from evidence_experiment.locks import now, work_lock
from evidence_experiment.schema import (
    append_jsonl,
    digest,
    file_digest,
    index_jsonl,
    read_jsonl,
    write_json,
)

from .assessment_protocol import (
    ORIGIN,
    contract,
    public_packet,
    request_for,
    utc_stamp,
    validate_identity,
)


def export(packets, destination, *, pass_id='initial', not_before=None):
    rows = [request_for(p, pass_id=pass_id) for p in packets.values()]
    for row in rows:
        row['not_before_utc'] = (not_before or {}).get(row['review_id'])
    if destination.exists():
        if read_jsonl(destination) != rows:
            raise ValueError('Issued requests changed; preserve the original task bundle')
        return rows
    destination.parent.mkdir(parents=True, exist_ok=True)
    for row in rows:
        append_jsonl(destination, row)
    destination.touch(exist_ok=True)
    return rows


def validate_request(req):
    messages = req['messages']
    if len(messages) != 2 or [m['role'] for m in messages] != ['system', 'user']:
        raise ValueError('Each request must have exactly one fixed task and one excerpt-only message')
    packet = json.loads(messages[1]['content'])['task']
    if packet != public_packet(packet['claim'], packet['code']):
        raise ValueError('Only the public excerpt and fixed contract may enter a request')
    expected = request_for(packet, pass_id=req['pass_id'])
    if any(req.get(k) != v for k, v in expected.items()):
        raise ValueError('Request does not reproduce from the public grading task')
    return packet


def execute(request_path, profile_path, output):
    import requests
    cfg = json.loads(profile_path.read_text())
    if (not cfg.get('provider') or cfg['provider'].startswith('SET_') or not cfg.get('model') or
            cfg['model'].startswith('SET_') or cfg['model'].lower().rstrip('/') == 'qcri/llmxcpg-q' or cfg.get('temperature') != 0 or
            not 1 <= cfg.get('max_tokens', 0) <= 8192):
        raise ValueError('Configure the real assessor identity and fixed sampling before execution')
    required = index_jsonl(request_path, 'request_id')
    done = index_jsonl(output, 'request_id')
    if set(done) - required.keys():
        raise ValueError('Foreign responses in this assessor run')
    profile_hash = digest(json.dumps({k: v for k, v in cfg.items() if k != 'api_key_env'}, sort_keys=True))
    if any(r.get('profile_sha256') != profile_hash for r in done.values()):
        raise ValueError('Assessor configuration changed during this response set')
    headers = {'Content-Type': 'application/json'}
    key = os.environ.get(cfg.get('api_key_env', ''), '')
    if key:
        headers['Authorization'] = 'Bearer ' + key
    for rid, request in required.items():
        validate_request(request)
        if rid in done:
            if done[rid].get('finish_reason') not in {None, 'stop'}:
                raise ValueError('An earlier truncated response requires an explicit new protocol decision')
            continue
        if request.get('not_before_utc'):
            utc_stamp(request['not_before_utc'])
        started = time.monotonic()
        body = {'model': cfg['model'], 'temperature': 0., 'max_tokens': cfg['max_tokens'], 'messages': request['messages']}
        try:
            response = requests.post(cfg['chat_completions_url'], headers=headers, json=body,
                                     timeout=cfg.get('timeout_seconds', 180))
            response.raise_for_status()
            raw = response.json()
            content = raw['choices'][0]['message']['content']
            finish = raw['choices'][0].get('finish_reason')
        except Exception as exc:  # noqa: BLE001 - diagnostic without URLs, headers, credentials or response bodies
            append_jsonl(output.with_suffix('.errors.jsonl'), {'request_id': rid, 'utc': now(),
                'error_type': type(exc).__name__, 'elapsed_seconds': time.monotonic() - started,
                'meaning': 'Transport/response-envelope failure; no content-based retry selection.'})
            raise RuntimeError('Assessor transport/envelope failure; diagnostic saved without credentials') from None
        identity = {'provider': cfg['provider'], 'requested_model': cfg['model'],
                    'reported_model': raw.get('model') or 'not_exposed',
                    'revision_note': cfg.get('revision_note') or 'not_exposed',
                    'route': 'stateless_chat_completions',
                    'sampling': {'temperature': 0., 'max_tokens': cfg['max_tokens']}}
        append_jsonl(output, {**{k: request[k] for k in ('request_id', 'review_id', 'request_sha256', 'pass_id')},
            'assessed_utc': now(), 'assessor_identity': identity, 'profile_sha256': profile_hash,
            'content': content, 'finish_reason': finish, 'elapsed_seconds': time.monotonic() - started,
            'response_metadata': {'id': raw.get('id'), 'model': raw.get('model'), 'usage': raw.get('usage')},
            'synthetic': False})
        if finish not in {None, 'stop'}:
            raise RuntimeError('Truncated assessor response saved; no automatic content repair/retry')
    print(f'RQ1_ASSESSOR_RESPONSES_OK: {len(required)} responses; {output}')


def validated_grades(request_path, response_path):
    from evidence_experiment.review import validate_assessment
    requests = index_jsonl(request_path, 'request_id')
    responses = index_jsonl(response_path, 'request_id')
    if responses.keys() != requests.keys():
        raise ValueError('Supply exactly one response for every issued request')
    grades, signatures = [], set()
    for rid, req in requests.items():
        packet = validate_request(req)
        row = responses[rid]
        if (row.get('request_sha256') != req['request_sha256'] or row.get('synthetic') is not False or
                row.get('review_id') != req['review_id'] or row.get('pass_id') != req['pass_id'] or
                row.get('finish_reason') not in {None, 'stop'}):
            raise ValueError('Mismatched, simulated or incomplete assessor response')
        assessed = utc_stamp(row.get('assessed_utc'))
        if req.get('not_before_utc') and assessed < utc_stamp(req['not_before_utc']):
            raise ValueError('Delayed response was produced before its frozen deadline')
        signatures.add(validate_identity(row.get('assessor_identity')))
        parsed = json.loads(row['content'])
        if parsed.get('review_id') != req['review_id']:
            raise ValueError('Assessor answered a different packet')
        grade = {**parsed, 'assessor_id': 'calibrated_ai_assessor', 'assessment_origin': ORIGIN,
                 'assessment_context': 'excerpt_only_stateless', 'assessed_utc': row['assessed_utc'],
                 'assessment_contract_sha256': contract()['contract_sha256'],
                 'assessor_identity': row['assessor_identity'], 'request_id': rid,
                 'request_sha256': req['request_sha256']}
        validate_assessment(grade, packet)
        grades.append(grade)
    if len(signatures) > 1:
        raise ValueError('One frozen assessor identity/settings must grade the complete set')
    if len({g['review_id'] for g in grades}) != len(grades):
        raise ValueError('Grade each unique packet once per pass')
    return grades, signatures


def import_responses(request_path, response_path, destination):
    grades, signatures = validated_grades(request_path, response_path)
    if destination.exists():
        if read_jsonl(destination) != grades:
            raise ValueError('Preserving initial assessments; no overwrite is allowed')
    else:
        for grade in grades:
            append_jsonl(destination, grade)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.touch(exist_ok=True)
    receipt = {'requests_path': os.path.relpath(request_path.resolve(), destination.parent.resolve()),
        'responses_path': os.path.relpath(response_path.resolve(), destination.parent.resolve()),
        'requests_sha256': file_digest(request_path), 'responses_sha256': file_digest(response_path),
        'assessments_sha256': file_digest(destination), 'assessor_signatures': sorted(signatures),
        'meaning': 'Stateless requests with raw responses; no independent human validation.'}
    proof = destination.with_suffix('.provenance.json')
    if proof.exists() and json.loads(proof.read_text()) != receipt:
        raise ValueError('Assessment provenance changed')
    write_json(proof, receipt)
    return grades


def verify_provenance(destination, packets, *, signature=None, pass_id='initial'):
    proof = json.loads(destination.with_suffix('.provenance.json').read_text())
    req = destination.parent / proof['requests_path']
    resp = destination.parent / proof['responses_path']
    if any(file_digest(path) != proof[key] for path, key in (
            (req, 'requests_sha256'), (resp, 'responses_sha256'), (destination, 'assessments_sha256'))):
        raise ValueError('Assessment provenance files changed')
    requests = index_jsonl(req, 'review_id')
    if requests.keys() != packets.keys() or any(
            validate_request(requests[rid]) != packet or requests[rid]['pass_id'] != pass_id
            for rid, packet in packets.items()):
        raise ValueError('Assessments do not cover the issued packets/pass')
    grades, signatures = validated_grades(req, resp)
    if (read_jsonl(destination) != grades or sorted(signatures) != proof['assessor_signatures'] or
            (signature and signatures and signatures != {signature})):
        raise ValueError('Grades or assessor identity changed after calibration')
    return {g['review_id']: g for g in grades}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('run', 'import'))
    p.add_argument('--requests', type=Path, required=True)
    p.add_argument('--responses', type=Path, required=True)
    p.add_argument('--profile', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    with work_lock(a.responses.parent):
        if a.action == 'run':
            if not a.profile:
                p.error('--profile is required')
            execute(a.requests, a.profile, a.responses)
        else:
            if not a.output:
                p.error('--output is required')
            import_responses(a.requests, a.responses, a.output)
            print(f'RQ1_ASSESSOR_IMPORT_OK {a.output}')


if __name__ == '__main__':
    main()
