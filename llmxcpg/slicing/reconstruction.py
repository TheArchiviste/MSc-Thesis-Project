"""Line-preserving enclosing-block reconstruction for the reviewed Juliet C subset.

Function bodies, enclosing control headers and their braces remain visible.
Comments and quoted braces are ignored when finding block boundaries. This is
an explicit RQ1 adaptation, not a claim of a complete C/C++ parser.
"""
from __future__ import annotations

import re


def _masked_lines(source):
    result, block_comment, quote, escape = [], False, None, False
    for line in source.splitlines():
        chars, i = [], 0
        while i < len(line):
            c = line[i]
            if block_comment:
                if line[i:i + 2] == "*/":
                    chars.extend("  ")
                    i += 2
                    block_comment = False
                else:
                    chars.append(" ")
                    i += 1
            elif quote:
                chars.append(" ")
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == quote:
                    quote = None
                i += 1
            elif line[i:i + 2] == "//":
                chars.extend(" " * (len(line) - i))
                break
            elif line[i:i + 2] == "/*":
                chars.extend("  ")
                i += 2
                block_comment = True
            elif c in "\"'":
                chars.append(" ")
                quote = c
                i += 1
            else:
                chars.append(c)
                i += 1
        result.append("".join(chars))
    return result


def context_lines(source: str, selected) -> list[int]:
    lines = source.splitlines()
    requested = list(selected)
    if not requested or any(type(n) is not int or not 1 <= n <= len(lines) for n in requested):
        raise ValueError("Invalid or empty source-line coordinates")
    masked = _masked_lines(source)
    stack, blocks = [], []
    for i, line in enumerate(masked):
        for column, c in enumerate(line):
            if c == "{":
                header = i
                if not line[:column].strip():
                    header = i - 1
                    while header >= 0 and not masked[header].strip():
                        header -= 1
                header = max(0, header)
                balance = masked[header].count(")") - masked[header].count("(")
                while balance > 0 and header > 0:
                    header -= 1
                    balance += masked[header].count(")") - masked[header].count("(")
                if re.match(r"\s*}?\s*else\b", masked[header]):
                    # Look back through the preceding closing brace to its if header.
                    prior = next((block for block in reversed(blocks) if block[2] <= i + 1), None)
                    if prior:
                        # Include its control header and brace, not its omitted body.
                        stack.append((header + 1, i + 1, prior[:2]))
                    else:
                        stack.append((header + 1, i + 1, None))
                else:
                    stack.append((header + 1, i + 1, None))
            elif c == "}":
                if not stack:
                    raise ValueError("Unbalanced source braces")
                header, opening, preceding = stack.pop()
                blocks.append((header, opening, i + 1, preceding))
    if stack:
        raise ValueError("Unbalanced source braces")
    rendered = set(requested)
    for pivot in requested:
        for header, opening, closing, preceding in blocks:
            if opening <= pivot <= closing:
                rendered.update(range(header, opening + 1))
                rendered.add(closing)
                if preceding:
                    previous_header, previous_opening = preceding
                    rendered.update(range(previous_header, previous_opening + 1))
                    # Keep the previous branch's closing brace so else has its visible condition.
                    previous_block = next(b for b in blocks if b[:2] == preceding)
                    rendered.add(previous_block[2])
        # The corpus also contains single-line allocation checks. Retain
        # a preceding braceless control header when the selected statement is its body.
        previous = pivot - 2
        if (previous >= 0 and re.match(r"\s*(if|for|while)\s*\(", masked[previous]) and
                "{" not in masked[previous] and masked[previous].rstrip().endswith(")")):
            rendered.add(previous + 1)
    return sorted(rendered)


def reconstruct_code_from_lines(source, slice_lines, *, add_function_anchors=True):
    # The historical keyword remains solely for callers of the extractor.
    # Production RQ1 reconstruction always enables enclosing-block context.
    selected = context_lines(source, slice_lines) if add_function_anchors else sorted(set(slice_lines))
    lines, out, last = source.splitlines(), [], None
    for n in selected:
        if type(n) is not int or not 1 <= n <= len(lines):
            raise ValueError("Invalid source-line coordinates")
        if last is not None and n > last + 1:
            out.append("")
        out.append(lines[n - 1])
        last = n
    return "\n".join(out)
