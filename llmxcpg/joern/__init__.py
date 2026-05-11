"""Joern WebSocket client and CPGQL query helpers.

`client` is lazy because it imports `cpgqls-client`, which isn't needed for
just the query-template helpers.
"""

from __future__ import annotations

from llmxcpg.joern.queries import (
    INTERACTERS_QUERY_TEMPLATE,
    BACKWARD_SLICE_QUERY_TEMPLATE,
    build_interacters_query,
    build_backward_slice_query,
)

__all__ = [
    "JoernClient",
    "JoernError",
    "QueryResult",
    "INTERACTERS_QUERY_TEMPLATE",
    "BACKWARD_SLICE_QUERY_TEMPLATE",
    "build_interacters_query",
    "build_backward_slice_query",
]


def __getattr__(name: str):
    if name in {"JoernClient", "JoernError", "QueryResult"}:
        from llmxcpg.joern import client
        return getattr(client, name)
    raise AttributeError(f"module 'llmxcpg.joern' has no attribute {name!r}")
