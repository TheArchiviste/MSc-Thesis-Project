"""Training data preparation: bootstrap CPGQL queries, ESBMC mapping, dataset loaders.

Lazy imports — `bootstrap` pulls in cpgqls-client and openai, neither of which
the lighter modules need.
"""

from __future__ import annotations

from llmxcpg.data.esbmc_cwe_mapping import esbmc_error_to_cwe, ESBMC_TO_CWE

__all__ = [
    "bootstrap_query_dataset",
    "BootstrapResult",
    "DeepSeekQueryProposer",
    "esbmc_error_to_cwe",
    "ESBMC_TO_CWE",
]


def __getattr__(name: str):
    if name in {"bootstrap_query_dataset", "BootstrapResult", "DeepSeekQueryProposer"}:
        from llmxcpg.data import bootstrap
        return getattr(bootstrap, name)
    raise AttributeError(f"module 'llmxcpg.data' has no attribute {name!r}")
