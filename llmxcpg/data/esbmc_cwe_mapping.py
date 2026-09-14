"""ESBMC error message → CWE mapping for FormAI-v2.

FormAI-v2 labels code via ESBMC's bounded model checker; its assertions don't
emit CWE IDs directly. The paper §4.1 explicitly notes the authors built this
mapping manually. Here is a faithful reconstruction based on the ESBMC
manual, the FormAI-v2 paper (Tihanyi et al.), and the four CWEs the LLMxCPG
paper says it covered for FormAI training (CWE-119, CWE-190, CWE-415, CWE-416).

If you need to extend this for additional CWEs, just add entries — the keys
are *substrings* matched case-insensitively against the ESBMC verdict text.
"""

from __future__ import annotations

from collections.abc import Mapping

# Substring → CWE. Order matters: more specific patterns first.
ESBMC_TO_CWE: Mapping[str, str] = {
    # Use after free
    "dereference failure: invalidated dynamic object": "CWE-416",
    "use after free": "CWE-416",
    # Double free
    "double free": "CWE-415",
    "invalid pointer freed": "CWE-415",
    # Integer overflow / arithmetic
    "arithmetic overflow on add": "CWE-190",
    "arithmetic overflow on sub": "CWE-190",
    "arithmetic overflow on mul": "CWE-190",
    "arithmetic overflow on shl": "CWE-190",
    "overflow in implicit conversion": "CWE-190",
    "overflow on": "CWE-190",
    # Buffer / memory bounds (paper rolls these into CWE-119)
    "array bounds violated": "CWE-119",
    "dereference failure: array bounds violated": "CWE-119",
    "dereference failure: object out-of-bounds": "CWE-119",
    "dereference failure: invalid pointer": "CWE-119",
    "buffer overflow": "CWE-119",
    "out-of-bounds": "CWE-119",
}


def esbmc_error_to_cwe(esbmc_text: str) -> str | None:
    """Map an ESBMC verdict to a CWE, or None if no rule fires."""
    if not esbmc_text:
        return None
    needle = esbmc_text.lower()
    for pattern, cwe in ESBMC_TO_CWE.items():
        if pattern in needle:
            return cwe
    return None
