"""Central configuration. Defaults match the LLMxCPG paper (USENIX Security 2025).

All values that come from the paper are annotated with the section they appear in,
so anyone tweaking them can trace the provenance.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# Per-dataset thresholds γ from §4.2 of the paper (calibrated on 20 validation samples).
# Note the wide spread — see Discussion in the literature review on portability cost.
DEFAULT_THRESHOLDS: Mapping[str, float] = {
    "primevul": 0.594,
    "formai": 0.547,
    "sven": 0.334,
    "reposvul": 0.193,
}


# CWEs the system is designed to handle (paper §4.1, "Studied CWEs").
# Restricted to memory-safety bugs that static CPG analysis can model.
SUPPORTED_CWES: tuple[str, ...] = (
    "CWE-119",  # Buffer Overflow
    "CWE-120",  # Buffer Copy without Checking the Size of Input
    "CWE-121",  # Stack-based Buffer Overflow
    "CWE-122",  # Heap-based Buffer Overflow
    "CWE-125",  # Out-of-bounds Read
    "CWE-190",  # Integer Overflow
    "CWE-415",  # Double Free
    "CWE-416",  # Use After Free
    "CWE-787",  # Out-of-bounds Write
)


@dataclass
class JoernConfig:
    """Connection details for the Joern WebSocket server (joern --server)."""
    host: str = "localhost"
    port: int = 8080
    auth_user: str | None = None
    auth_pass: str | None = None
    # Joern runs in another filesystem when Docker is used. Source is staged
    # in this host directory and addressed through `server_input_dir` inside
    # the container. The compose file mounts these two locations together.
    local_input_dir: Path | None = None
    server_input_dir: str | None = "/analysis/inputs"
    # The Joern docker image to spin up if you use docker compose.
    image: str = "ghcr.io/joernio/joern:v4.0.0"


@dataclass
class ModelConfig:
    """Identifies which weights to load.

    The two-model split is non-negotiable: end-to-end fusion would destroy the
    inspectability that the architecture exists to provide.
    """
    # Query generator (LLMxCPG-Q). Paper fine-tunes Qwen2.5-Coder-32B-Instruct.
    query_model_path: str = "QCRI/LLMxCPG-Q"
    query_model_revision: str | None = None
    query_max_context: int = 32_768  # 32K — paper §5 explains the limit.
    query_temperature: float = 0.0   # Deterministic CPGQL generation.
    query_engine: str = "vllm"       # "vllm", "openai", or "dummy".
    query_base_url: str | None = None
    query_api_key_env: str = "LLMXCPG_QUERY_API_KEY"
    query_gpu_memory_utilization: float = 0.85
    query_tensor_parallel_size: int = 1

    # Detector (LLMxCPG-D). Paper fine-tunes QwQ-32B-Preview.
    detector_model_path: str = "QCRI/LLMxCPG-D"
    detector_model_revision: str | None = None
    detector_max_context: int = 16_384  # Released inference configuration.
    detector_dtype: str = "bfloat16"

    # The released detector is trained and evaluated with Yes/No. Its reduced
    # head is ordered [No, Yes], so the published thresholds apply to class 1.
    vulnerable_token: str = "Yes"
    safe_token: str = "No"

    # A local 32B Q model and 32B D model do not fit in memory together on the
    # paper's single A100. Release Q before lazily loading D. Batch callers
    # should use detect_batch so all Q work finishes before the release.
    release_local_query_model_before_detection: bool = True


@dataclass
class TrainingConfig:
    """LoRA hyperparameters from §4.2 of the paper."""
    lora_rank: int = 8
    lora_alpha: int = 4
    lora_dropout: float = 0.0
    learning_rate: float = 1e-4
    # Targets for LoRA adapters — chosen to cover attn + FFN, standard for Qwen.
    target_modules: tuple[str, ...] = (
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    )
    num_epochs: int = 3
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    warmup_ratio: float = 0.05
    weight_decay: float = 0.0
    save_strategy: str = "epoch"
    bf16: bool = True


@dataclass
class Config:
    """Top-level config grouping everything."""
    joern: JoernConfig = field(default_factory=JoernConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    work_dir: Path = field(default_factory=lambda: Path("./work"))
    # Default classification threshold; override per-dataset via DEFAULT_THRESHOLDS.
    threshold: float = 0.5
    # Cap retries when DeepSeek-v3 fails to produce a valid CPGQL query (§4.2).
    bootstrap_max_retries: int = 3

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        if self.joern.local_input_dir is None:
            self.joern.local_input_dir = self.work_dir / "joern-inputs"
        else:
            self.joern.local_input_dir = Path(self.joern.local_input_dir)
        self.joern.local_input_dir.mkdir(parents=True, exist_ok=True)
