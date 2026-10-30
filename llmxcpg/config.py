"""Settings for pretrained Q generation only; no training or verdict model."""
from dataclasses import dataclass


@dataclass
class ModelConfig:
    query_model_path: str = "QCRI/LLMxCPG-Q"
    query_model_revision: str = "1f48ab60420d90277207394f1254d27d3375b07e"
    query_max_context: int = 8192
    query_temperature: float = 0.0
    query_gpu_memory_utilization: float = 0.85
    query_tensor_parallel_size: int = 1
