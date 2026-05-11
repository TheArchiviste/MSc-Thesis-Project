"""Rebuild a code snippet from the line numbers a CPG slice picks out.

A naive `''.join(lines[i] for i in slice_lines)` is wrong because it produces
syntactically broken code: braces are dropped, function headers vanish, etc.
The paper's Figure-2 → Listing-4 example shows the slice keeps function
headers and matching braces.

Strategy:
  1. Take the union of `slice_lines` plus the line numbers of any *enclosing*
     scope (function header, opening brace, return statement at function end).
  2. For runs of consecutive line numbers, emit them as-is. For gaps, emit a
     blank line. (No `// ...` comment, because the prompt to LLMxCPG-D says the
     snippet "might not be complete, but it has all the important context",
     so the model is already trained to tolerate gaps.)

This is intentionally conservative: it errs on the side of including a few
extra lines that anchor structure rather than hand the detector a soup of
disembodied statements.
"""

from __future__ import annotations

import re
from typing import Iterable


# Lightweight regex for "function header" — works for C/C++ and is forgiving
# enough not to over-fire on macros. Matches lines like:
#   `static int foo(struct bar *b, size_t n)`
#   `void process(char *p) {`
_FUNC_HEADER_RE = re.compile(
    r"^\s*(?:static\s+|inline\s+|extern\s+|const\s+)*"
    r"[A-Za-z_][\w\s\*]*\s+\**[A-Za-z_]\w*\s*\([^;]*\)\s*\{?\s*$"
)


def _enclosing_function_lines(source: list[str], pivot: int) -> tuple[int, int] | None:
    """Find the (header_line, close_brace_line) enclosing the 1-indexed `pivot`.

    Returns None if we can't locate one. The detection is brace-counting from
    the candidate header forward; lots of room for false negatives, but
    failures are *safe* (we just don't add anchor lines).
    """
    # Walk upward to find the most recent function header.
    header = None
    for i in range(pivot - 1, -1, -1):
        if i >= len(source):
            continue
        if _FUNC_HEADER_RE.match(source[i]):
            header = i
            break
    if header is None:
        return None

    # Walk forward from header counting braces.
    depth = 0
    started = False
    for j in range(header, len(source)):
        for ch in source[j]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return (header + 1, j + 1)  # convert to 1-indexed
    return None


def reconstruct_code_from_lines(
    source: str,
    slice_lines: Iterable[int],
    *,
    add_function_anchors: bool = True,
) -> str:
    """Rebuild a snippet from a set of 1-indexed line numbers.

    Args:
        source: the original source as a single string.
        slice_lines: 1-indexed line numbers selected by the slice query.
        add_function_anchors: if True, expand each line to include its enclosing
            function header and closing brace. Set to False if the caller
            already passes a complete set of structurally necessary lines.

    Returns:
        A code snippet preserving original line ordering, with single-line
        gaps where intermediate lines are skipped.
    """
    if not source:
        return ""

    lines = source.splitlines()
    selected: set[int] = {n for n in slice_lines if 1 <= n <= len(lines)}
    if not selected:
        return ""

    if add_function_anchors:
        anchors: set[int] = set()
        for n in list(selected):
            box = _enclosing_function_lines(lines, n)
            if box is None:
                continue
            header, close = box
            anchors.add(header)
            anchors.add(close)
        selected |= anchors

    # Emit lines in original order; collapse multi-line gaps to a single blank.
    out: list[str] = []
    last_emitted: int | None = None
    for n in sorted(selected):
        if last_emitted is not None and n - last_emitted > 1:
            out.append("")  # one blank line marks a gap
        out.append(lines[n - 1])
        last_emitted = n

    return "\n".join(out)
