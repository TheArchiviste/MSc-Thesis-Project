"""Joern WebSocket client and CPGQL query helpers.

`client` is lazy because it imports `cpgqls-client`, which isn't needed for
just the query-template helpers.
"""

from __future__ import annotations

from llmxcpg.joern.queries import (
    BACKWARD_SLICE_QUERY_TEMPLATE,
    INTERACTERS_QUERY_TEMPLATE,
    build_backward_slice_query,
    build_interacters_query,
    validate_generated_query,
)

__all__ = [
    "BACKWARD_SLICE_QUERY_TEMPLATE",
    "INTERACTERS_QUERY_TEMPLATE",
    "JoernClient",
    "JoernError",
    "QueryResult",
    "build_backward_slice_query",
    "build_interacters_query",
    "validate_generated_query",
]


def __getattr__(name: str):
    if name in {"JoernClient", "JoernError", "QueryResult"}:
        from llmxcpg.joern import client
        return getattr(client, name)
    raise AttributeError(f"module 'llmxcpg.joern' has no attribute {name!r}")
