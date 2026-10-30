"""Source-only Juliet grouping and line-preserving C extraction for RQ1."""
from __future__ import annotations

import re

FILE_NAME = re.compile('^(CWE\\d+)_[^/]*?__(.+?)_(\\d{2})([a-e]?)\\.(c|cpp)$')


TYPES = ('wchar_t', 'char', 'unsigned_int', 'int64_t', 'int', 'long', 'short', 'struct', 'class', 'twoIntsStruct')


SOURCES = ('fgets', 'fscanf', 'rand', 'large', 'connect_socket', 'listen_socket', 'max', 'min', 'negative', 'zero', 'ten')


ALLOCATION_STYLES = ('alloca', 'declare')


COPY_SINKS = ('memcpy', 'memmove', 'ncpy', 'cpy')


def parse(path: str) -> dict | None:
    match = FILE_NAME.match(path.strip().rsplit('/', 1)[-1])
    if not match:
        return None
    cwe, functional, flow, part, ext = match.groups()
    return {'cwe': cwe, 'functional_variant': functional, 'flow_variant': int(flow), 'multi_file_part': part or None, 'ext': ext}


def _strip(tokens: str, words: tuple[str, ...]) -> str:
    return re.sub(f"(^|_)({'|'.join(map(re.escape, words))})(?=_|$)", '\\1', tokens)


def template_of(cwe: str, functional_variant: str, *, merge_copy_sinks: bool=True) -> str:
    """Collapse source, type and allocation variants into one template id."""
    t = _strip(functional_variant, TYPES)
    t = _strip(t, SOURCES)
    t = _strip(t, ALLOCATION_STYLES)
    if merge_copy_sinks:
        t = re.sub(f"(^|_)({'|'.join(COPY_SINKS)})(?=_|$)", '\\1copy', t)
    t = re.sub('_+', '_', t).strip('_')
    return '-'.join([cwe, *[part for part in t.split('_') if part]])


def template_cluster(upstream_path: str, *, merge_copy_sinks: bool=True) -> str:
    """Cluster id for a Juliet test-case path, e.g. 'CWE121-CWE129'."""
    parsed = parse(upstream_path)
    if parsed is None:
        raise ValueError(f'Not a Juliet test-case file name: {upstream_path}')
    return template_of(parsed['cwe'], parsed['functional_variant'], merge_copy_sinks=merge_copy_sinks)


def _strip_comment(line: str, in_block: bool) -> tuple[str, bool]:
    """Remove comments in the reviewed C subset, retaining source line identity."""
    out = []
    i = 0
    quoted = None
    while i < len(line):
        if in_block:
            end = line.find('*/', i)
            if end == -1:
                return (''.join(out), True)
            i = end + 2
            in_block = False
        elif quoted:
            out.append(line[i])
            if line[i] == '\\' and i + 1 < len(line):
                i += 1
                out.append(line[i])
            elif line[i] == quoted:
                quoted = None
            i += 1
        elif line.startswith('/*', i):
            in_block = True
            i += 2
        elif line.startswith('//', i):
            break
        else:
            if line[i] in ("'", '"'):
                quoted = line[i]
            out.append(line[i])
            i += 1
    return (''.join(out), in_block)


def _function(lines: list[str], name: str) -> list[tuple[str, int]]:
    start = next((i for i, line in enumerate(lines) if re.match('^(?:static\\s+)?void\\s+' + re.escape(name) + '\\s*\\(', line)), None)
    if start is None:
        raise ValueError(f'Missing reviewed function {name}')
    depth = 0
    opened = False
    result = []
    for i in range(start, len(lines)):
        line = lines[i]
        result.append((line, i + 1))
        depth += line.count('{') - line.count('}')
        opened |= '{' in line
        if opened and depth == 0:
            return result
    raise ValueError(f'Unclosed reviewed function {name}')
