"""Small, explicit wire adapters; no SDK retries, tools or conversation state."""
from __future__ import annotations

import os
import re


def api_kind(profile):
    return profile.get('api', 'vllm_chat_completions')


def validate_profile(profile):
    kind = api_kind(profile)
    if not profile.get('provider') or not profile.get('model') or any(
            str(profile[k]).startswith('SET_') for k in ('provider', 'model')):
        raise ValueError('Configure the real assessor identity')
    if profile['model'].lower().rstrip('/') == 'qcri/llmxcpg-q':
        raise ValueError('The evaluated Q cannot grade its own evidence')
    if kind == 'openai_responses':
        if (profile.get('responses_url') != 'https://api.openai.com/v1/responses' or
                profile.get('reasoning_effort') not in {'low', 'medium', 'high', 'xhigh', 'max'} or
                type(profile.get('max_output_tokens')) is not int or
                not 25000 <= profile['max_output_tokens'] <= 128000 or
                'temperature' in profile or 'max_tokens' in profile):
            raise ValueError('Responses reasoning needs the official endpoint, fixed effort and a sufficient output allowance; omit temperature')
        if profile.get('api_key_env') != 'OPENAI_API_KEY':
            raise ValueError('Use the private OPENAI_API_KEY environment variable')
    elif kind == 'vllm_chat_completions':
        if (profile.get('temperature') != 0 or type(profile.get('max_tokens')) is not int or
                not 1 <= profile['max_tokens'] <= 8192):
            raise ValueError('Freeze the vLLM assessor sampling settings')
    else:
        raise ValueError('Unsupported assessor API; declare a new adapter before use')
    return kind


def wire_request(request, profile):
    kind = validate_profile(profile)
    common = {'model': profile['model']}
    if kind == 'openai_responses':
        return profile['responses_url'], {**common, 'input': request['messages'], 'store': False,
            'service_tier': 'default',
            'reasoning': {'effort': profile['reasoning_effort']},
            'max_output_tokens': profile['max_output_tokens'],
            'text': {'format': {'type': 'json_schema', 'name': 'rq1_assessment',
                                'strict': True, 'schema': request['decode_schema']}}}
    return profile['chat_completions_url'], {**common, 'messages': request['messages'],
        'temperature': 0., 'max_tokens': profile['max_tokens'],
        'guided_json': request['decode_schema']}


def headers(profile):
    key_name = profile.get('api_key_env', '')
    if key_name and not re.fullmatch(r'[A-Z][A-Z0-9_]*', key_name):
        raise ValueError('Invalid credential environment-variable name')
    key = os.environ.get(key_name, '')
    if api_kind(profile) == 'openai_responses' and not key:
        raise ValueError('OPENAI_API_KEY is not set; no paid request was sent')
    result = {'Content-Type': 'application/json'}
    if key:
        result['Authorization'] = 'Bearer ' + key
    return result


def unpack(raw, profile):
    if api_kind(profile) == 'openai_responses':
        blocks = [block for item in raw.get('output', []) if item.get('type') == 'message'
                  for block in item.get('content', [])]
        text = ''.join(block['text'] for block in blocks if block.get('type') == 'output_text')
        refused = any(block.get('type') == 'refusal' for block in blocks)
        finish = 'refusal' if refused else 'stop' if raw.get('status') == 'completed' and text else 'incomplete'
        return text, finish
    return raw['choices'][0]['message']['content'], raw['choices'][0].get('finish_reason')


def identity(profile, raw):
    responses = api_kind(profile) == 'openai_responses'
    sampling = ({'reasoning_effort': profile['reasoning_effort'],
                 'max_output_tokens': profile['max_output_tokens'], 'structured_outputs': True,
                 'service_tier': 'default'}
                if responses else {'temperature': 0., 'max_tokens': profile['max_tokens'],
                                      'guided_json': True})
    return {'provider': profile['provider'], 'requested_model': profile['model'],
            'reported_model': raw.get('model') or 'not_exposed',
            'revision_note': profile.get('revision_note') or 'not_exposed',
            'route': 'stateless_responses' if responses else 'stateless_chat_completions',
            'sampling': sampling}
