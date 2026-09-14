"""LLMxCPG-Q and LLMxCPG-D inference, plus the end-to-end pipeline.

Imports are lazy so the rest of the package works without torch/vllm/transformers.
"""

from __future__ import annotations

__all__ = [
    "ClassificationOutput",
    "ClassificationResult",
    "LLMxCPGPipeline",
    "QueryGenerator",
    "VulnerabilityClassifier",
]


def __getattr__(name: str):
    if name == "QueryGenerator":
        from llmxcpg.inference.query_generator import QueryGenerator
        return QueryGenerator
    if name == "VulnerabilityClassifier":
        from llmxcpg.inference.classifier import VulnerabilityClassifier
        return VulnerabilityClassifier
    if name == "ClassificationOutput":
        from llmxcpg.inference.classifier import ClassificationOutput
        return ClassificationOutput
    if name == "LLMxCPGPipeline":
        from llmxcpg.inference.pipeline import LLMxCPGPipeline
        return LLMxCPGPipeline
    if name == "ClassificationResult":
        from llmxcpg.inference.pipeline import ClassificationResult
        return ClassificationResult
    raise AttributeError(f"module 'llmxcpg.inference' has no attribute {name!r}")
