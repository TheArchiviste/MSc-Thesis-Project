"""LoRA configuration builder.

LLaMA-Factory is the reference path (configs/llamafactory/*.yaml), but if you
prefer a vanilla `peft + transformers` script, this builds the same LoRA config
the paper uses: rank=8, alpha=4, lr=1e-4 — exactly per §4.2.
"""

from __future__ import annotations

from llmxcpg.config import TrainingConfig


def build_lora_config(cfg: TrainingConfig):
    """Return a `peft.LoraConfig` matching the paper's hyperparameters."""
    from peft import LoraConfig, TaskType

    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=cfg.lora_rank,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=list(cfg.target_modules),
        bias="none",
    )
