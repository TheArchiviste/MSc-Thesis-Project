"""Read a preserved Q archive locally; disclose a traceback only before any Q session."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

PREFIX = 'work/rq1-v7/development/'
MAX_RECORD_BYTES = 16 * 1024 * 1024
MAX_TRACEBACK_BYTES = 64 * 1024
COUNTS = ('queries.jsonl', 'query_sessions.jsonl',
          'query_load_errors.jsonl', 'query_runtime_errors.jsonl')
VERSION = 2
KNOWN_FAILURES = {
    'Real Q session provenance is missing or synthetic': 'query_session_provenance',
    'Unknown or nonterminal observation status': 'query_terminal_status',
    'Seal needs actual contained stage files, never symlink targets': 'seal_file_inventory',
    'Incomplete stage receipt or different inputs': 'stage_receipt_inputs',
    'Unknown stage receipt': 'stage_receipt_phase',
    'Prior acquisition seal differs': 'prior_seal_conflict',
}
TRACEBACK_FILES = ('evidence_experiment/__main__.py', 'evidence_experiment/locks.py',
                   'evidence_experiment/runner.py', 'evidence_experiment/schema.py',
                   'rq1/sealing.py', 'rq1/setup.py', 'llmxcpg/inference/query_generator.py')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def provenance_checks(records, lock):
    """Aggregate validation predicates; never export query text, errors or case IDs."""
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository))
    from evidence_experiment.schema import load_cases, run_specs

    expected = {r['run_id'] for r in run_specs(load_cases(repository / 'rq1/development.jsonl'))}
    queries = records['queries.jsonl']
    sessions = records['query_sessions.jsonl']
    session_ids = [s.get('session_id') for s in sessions]
    query_ids = [r.get('run_id') for r in queries]
    indexed = {s['session_id']: s for s in sessions if isinstance(s.get('session_id'), str)}
    cfg = lock.get('policy', {})
    checks = {
        'six_query_records': len(queries) == 6,
        'query_ids_match_frozen_development': set(query_ids) == expected,
        'query_ids_unique': len(set(query_ids)) == len(query_ids),
        'session_ids_unique': len(set(session_ids)) == len(session_ids),
        'terminal_statuses_recognized': all(r.get('status') in {'ok', 'query_parse', 'context_overflow'} for r in queries),
    }
    predicates = {
        'record_is_real': lambda r, s: r.get('synthetic') is False,
        'record_engine_vllm': lambda r, s: r.get('query_engine') == 'vllm',
        'session_exists': lambda r, s: bool(s),
        'session_is_real': lambda r, s: s.get('synthetic') is False,
        'model_load_time_recorded': lambda r, s: bool(s.get('model_load_seconds')),
        'effective_dtype_bfloat16': lambda r, s: s.get('effective_dtype') in {'torch.bfloat16', 'bfloat16'},
        'runtime_matches_stage_lock': lambda r, s: s.get('runtime') == lock.get('stage_environments', {}).get('query'),
        'revision_matches_policy': lambda r, s: s.get('query_revision') == cfg.get('query_revision'),
        'model_matches_policy': lambda r, s: s.get('query_model') == cfg.get('query_model'),
        'context_matches_policy': lambda r, s: s.get('effective_max_context') == cfg.get('query_max_context'),
        'effective_seed_zero': lambda r, s: s.get('effective_seed') == 0,
        'temperature_zero': lambda r, s: s.get('temperature') == 0,
        'top_p_one': lambda r, s: s.get('top_p') == 1,
        'generation_allowance_2048': lambda r, s: s.get('generation_allowance') == 2048,
        'positive_prompt_token_count': lambda r, s: type(r.get('prompt_tokens')) is int and r['prompt_tokens'] > 0,
        'queries_list_shape': lambda r, s: isinstance(r.get('queries'), list),
        'nonempty_queries_when_status_ok': lambda r, s: r.get('status') != 'ok' or bool(r.get('queries')),
    }
    for name, predicate in predicates.items():
        checks[name] = bool(queries) and all(predicate(r, indexed.get(r.get('session_id'), {})) for r in queries)
    metadata = []
    for session in sessions:
        row = {}
        dtype = session.get('effective_dtype')
        row['effective_dtype'] = dtype if dtype in {'torch.bfloat16', 'bfloat16', 'torch.float16', 'float16', 'unknown', 'synthetic'} else 'other_or_missing'
        for name in ('effective_seed', 'effective_max_context', 'generation_allowance', 'temperature', 'top_p'):
            value = session.get(name)
            row[name] = value if value is None or type(value) in {int, float} else 'non_numeric_withheld'
        metadata.append(row)
    return {'checks': checks, 'failed_checks': [name for name, ok in checks.items() if not ok],
            'session_settings': metadata}


def diagnose(path, expected):
    if not re.fullmatch(r'[a-f0-9]{64}', expected) or digest(path) != expected:
        raise ValueError('Archive differs from the independently returned checksum; preserve it.')
    with tarfile.open(path, 'r:gz') as tar:
        members = tar.getmembers()
        if len({m.name for m in members}) != len(members):
            raise ValueError('Duplicate archive entries; preserve the archive.')
        for member in members:
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or '..' in name.parts or
                    not member.name.startswith(PREFIX)):
                raise ValueError('Unexpected archive entry; preserve the archive.')
        files = {m.name[len(PREFIX):]: m for m in members}
        counts, records = {}, {}
        for name in COUNTS:
            member = files.get(name)
            if member is None:
                counts[name] = 0
                records[name] = []
                continue
            if member.size > MAX_RECORD_BYTES:
                raise ValueError('Record file exceeds diagnostic limit; no contents displayed.')
            with tar.extractfile(member) as stream:
                # Validate that each nonempty line is a JSON object, but never export its fields.
                rows = [json.loads(line) for line in stream if line.strip()]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError('Malformed record file; no contents displayed.')
            counts[name] = len(rows)
            records[name] = rows
        before_session = counts['queries.jsonl'] == counts['query_sessions.jsonl'] == 0
        result = {
            'diagnostic_version': VERSION,
            'phase': 'query', 'split': 'development', 'archive_sha256': expected,
            'archive_checksum_verified': True, 'record_counts': counts,
            'query_seal_present': 'query.seal.json' in files,
            'diagnostic_scope': 'Infrastructure diagnosis; original archive is read only and retained.',
            'traceback_disclosed': False,
            'generated_content_exported': False,
        }
        required = ('queries.jsonl', 'query_sessions.jsonl', 'witness_validation.jsonl',
                    'runtime.query.requirements.txt', 'experiment_lock.json', 'stage_receipts.json')
        result['required_stage_files_present'] = {name: name in files for name in required}
        if 'experiment_lock.json' in files:
            member = files['experiment_lock.json']
            if member.size > MAX_RECORD_BYTES:
                raise ValueError('Lock exceeds diagnostic limit.')
            with tar.extractfile(member) as stream:
                lock = json.load(stream)
            result['provenance_validation'] = provenance_checks(records, lock)
        logs = ['query.sealed.log'] + sorted(
            name for name in files if re.fullmatch(r'collection-query-[0-9TZ]+\.log', name))
        diagnostics = []
        for name in logs:
            member = files.get(name)
            if member is None:
                continue
            with tar.extractfile(member) as stream:
                stream.seek(max(0, member.size - MAX_TRACEBACK_BYTES))
                tail = stream.read(MAX_TRACEBACK_BYTES).decode('utf-8', errors='replace')
            position = tail.rfind('Traceback (most recent call last):')
            entry = {'log': name, 'traceback_found': position >= 0}
            if position >= 0 and before_session:
                # No Q session exists and no primary output was recorded: generation
                # of the experimental inputs has not begun. Expose only the final
                # Python traceback for this declared infrastructure diagnosis.
                entry['pre_session_traceback'] = tail[position:]
                result['traceback_disclosed'] = True
            elif position >= 0:
                # Once Q has a session, even exception messages may contain output.
                # Return only a built-in exception category, never its message.
                matches = re.findall(
                    r'^(ImportError|ModuleNotFoundError|ValueError|TypeError|RuntimeError|'
                    r'AttributeError|NameError|KeyError|OSError|FileNotFoundError|'
                    r'PermissionError|AssertionError|MemoryError|TimeoutError):', tail[position:], re.M)
                entry['exception_category'] = matches[-1] if matches else 'unclassified'
                entry['known_failure_checks'] = [code for message, code in KNOWN_FAILURES.items()
                    if re.search(r'^ValueError: ' + re.escape(message) + r'\s*$', tail[position:], re.M)]
                frames = []
                for filename, number, function in re.findall(
                        r'^  File "([^"\n]+)", line ([0-9]+), in ([A-Za-z_][A-Za-z_0-9]*|<module>)\s*$',
                        tail[position:], re.M):
                    for known in TRACEBACK_FILES:
                        if filename == known or filename.endswith('/' + known):
                            frames.append({'file': known, 'line': int(number), 'function': function})
                            break
                entry['repository_traceback_frames'] = frames
            diagnostics.append(entry)
        result['diagnostics'] = diagnostics
        result['instruction'] = 'Return this diagnostic JSON only. Keep the VM stopped; do not repeat Q acquisition.'
    if digest(path) != expected:
        raise ValueError('Archive changed during diagnosis; preserve both files.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('expected_sha256')
    args = parser.parse_args()
    try:
        result = diagnose(args.archive, args.expected_sha256)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, tarfile.TarError):
        raise SystemExit('Diagnostic stopped: invalid, changed or unsupported archive. Preserve all files; no contents displayed.') from None
    output = args.archive.with_suffix(f'.diagnostic-v{VERSION}.json')
    encoded = json.dumps(result, indent=2) + '\n'
    if output.exists() and output.read_text() != encoded:
        raise SystemExit('An earlier diagnostic differs. Both original files preserved.')
    if not output.exists():
        with output.open('x') as stream:
            stream.write(encoded)
    print(f'RETURN_DIAGNOSTIC: {output}')


if __name__ == '__main__':
    main()
