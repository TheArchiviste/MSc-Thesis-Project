"""LLMxCPG: CPG-guided LLM vulnerability detection.

The top-level package keeps imports light so that downstream modules without
GPU stacks installed (calibration, evaluation, data prep) can still be used.
The heavy inference classes load on first attribute access via PEP 562
module-level `__getattr__`.
"""

from __future__ import annotations

from llmxcpg.config import Config, ModelConfig, JoernConfig, DEFAULT_THRESHOLDS

__version__ = "0.1.0"
__all__ = [
    "LLMxCPGPipeline",
    "ClassificationResult",
    "Config",
    "ModelConfig",
    "JoernConfig",
    "DEFAULT_THRESHOLDS",
]


def __getattr__(name: str):
    """Lazy access to inference classes — torch/vllm load only on first use."""
    if name == "LLMxCPGPipeline":
        from llmxcpg.inference.pipeline import LLMxCPGPipeline
        return LLMxCPGPipeline
    if name == "ClassificationResult":
        from llmxcpg.inference.pipeline import ClassificationResult
        return ClassificationResult
    raise AttributeError(f"module 'llmxcpg' has no attribute {name!r}")
