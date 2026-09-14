"""Slice construction: query → execution path → interacters → backward slice → code.

`extractor` is lazy because it transitively pulls in the Joern client.
"""

from __future__ import annotations

from llmxcpg.slicing.reconstruction import reconstruct_code_from_lines

__all__ = ["Slice", "SliceExtractor", "SliceFailure", "reconstruct_code_from_lines"]


def __getattr__(name: str):
    if name in {"SliceExtractor", "Slice", "SliceFailure"}:
        from llmxcpg.slicing import extractor
        return getattr(extractor, name)
    raise AttributeError(f"module 'llmxcpg.slicing' has no attribute {name!r}")
