"""Read a preserved Q archive locally; disclose a traceback only before any Q session."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

PREFIX = 'work/rq1-v7/development/'
MAX_RECORD_BYTES = 16 * 1024 * 1024
MAX_TRACEBACK_BYTES = 64 * 1024
COUNTS = ('queries.jsonl', 'query_sessions.jsonl',
          'query_load_errors.jsonl', 'query_runtime_errors.jsonl')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


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
        counts = {}
        for name in COUNTS:
            member = files.get(name)
            if member is None:
                counts[name] = 0
                continue
            if member.size > MAX_RECORD_BYTES:
                raise ValueError('Record file exceeds diagnostic limit; no contents displayed.')
            with tar.extractfile(member) as stream:
                # Validate that each nonempty line is a JSON object, but never export its fields.
                rows = [json.loads(line) for line in stream if line.strip()]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError('Malformed record file; no contents displayed.')
            counts[name] = len(rows)
        before_session = counts['queries.jsonl'] == counts['query_sessions.jsonl'] == 0
        result = {
            'phase': 'query', 'split': 'development', 'archive_sha256': expected,
            'archive_checksum_verified': True, 'record_counts': counts,
            'query_seal_present': 'query.seal.json' in files,
            'diagnostic_scope': 'Infrastructure diagnosis; original archive is read only and retained.',
            'traceback_disclosed': False,
            'generated_content_exported': False,
        }
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
    except (OSError, ValueError, KeyError, tarfile.TarError):
        raise SystemExit('Diagnostic stopped: invalid, changed or unsupported archive. Preserve all files; no contents displayed.') from None
    output = args.archive.with_suffix('.diagnostic.json')
    encoded = json.dumps(result, indent=2) + '\n'
    if output.exists() and output.read_text() != encoded:
        raise SystemExit('An earlier diagnostic differs. Both original files preserved.')
    if not output.exists():
        with output.open('x') as stream:
            stream.write(encoded)
    print(f'RETURN_DIAGNOSTIC: {output}')


if __name__ == '__main__':
    main()
