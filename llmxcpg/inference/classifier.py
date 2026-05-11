"""LLMxCPG-D: vulnerability classifier with a reduced LM head.

This is the most surgical part of the paper (§4.2). Instead of running open-ended
generation and parsing the first word, we:

  1. Take the trained LM at hand and grab the rows of its `lm_head.weight`
     matrix that correspond to the tokens "VULNERABLE" and "SAFE".
  2. Replace the LM head with a 2-output classification head built from those
     rows alone.
  3. At inference, do a single forward pass to the last hidden state, project
     through the reduced head, softmax over the two classes, and threshold.

This avoids the cost of full-vocabulary decoding and ensures the model can
*only* output one of the two labels we care about — a much stronger guarantee
than prompt-engineering "respond with one word".

Subtleties:
  - Tokenisers split words differently. "VULNERABLE" might be a single token
    in some tokenisers and multiple in others. We require it to be a *single*
    token and fail loudly otherwise — multi-token labels would need a
    different reduction (e.g., scoring full sequences). Practically this is
    fine for Qwen-family tokenisers, which keep ALL-CAPS tokens as units.
  - The hidden state we project from is the last position of the prompt — the
    position the model would generate the answer from.
  - We disable KV cache during this single-step forward; it would help on
    long generation but not here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer, PreTrainedTokenizerBase

from llmxcpg.config import ModelConfig
from llmxcpg.prompts import render_detection_prompt


logger = logging.getLogger(__name__)


@dataclass
class ClassificationOutput:
    """A single classification with its calibrated probability."""
    is_vulnerable: bool
    probability_vulnerable: float
    probability_safe: float
    threshold_used: float
    raw_logits: tuple[float, float]  # (vuln_logit, safe_logit)


class VulnerabilityClassifier:
    """Run LLMxCPG-D as a binary classifier over reduced logits.

    Loading is deliberately not lazy: a 32B model takes minutes to load and
    you don't want that latency surfacing on the first prediction.
    """

    def __init__(
        self,
        model_path: str,
        vulnerable_token: str = "VULNERABLE",
        safe_token: str = "SAFE",
        dtype: str = "bfloat16",
        device: str = "auto",
        max_context: int = 8_192,
    ) -> None:
        self.model_path = model_path
        self.vuln_label = vulnerable_token
        self.safe_label = safe_token
        self.max_context = max_context

        torch_dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16,
                       "float32": torch.float32}[dtype]

        logger.info("Loading detector model: %s", model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch_dtype,
            device_map=device,
            trust_remote_code=True,
        )
        self.model.eval()

        # Build the reduced LM head once.
        self.vuln_token_id, self.safe_token_id = self._resolve_token_ids()

    @classmethod
    def from_config(cls, cfg: ModelConfig, **kwargs) -> "VulnerabilityClassifier":
        return cls(
            model_path=cfg.detector_model_path,
            vulnerable_token=cfg.vulnerable_token,
            safe_token=cfg.safe_token,
            dtype=cfg.detector_dtype,
            max_context=cfg.detector_max_context,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    # Token resolution
    # ------------------------------------------------------------------ #
    def _resolve_token_ids(self) -> tuple[int, int]:
        """Resolve the single-token IDs for the two label words.

        We try a few encoding variants (with/without leading space) because
        BPE tokenisers behave differently in either case.
        """
        candidates_vuln = [self.vuln_label, " " + self.vuln_label]
        candidates_safe = [self.safe_label, " " + self.safe_label]

        vid = self._first_single_token(candidates_vuln)
        sid = self._first_single_token(candidates_safe)
        if vid is None or sid is None:
            raise ValueError(
                f"Could not encode {self.vuln_label!r}/{self.safe_label!r} as single "
                f"tokens in {self.tokenizer.__class__.__name__}. Check the prompt's "
                "label words match what the model was fine-tuned on."
            )
        logger.info("Reduced head: %s -> %d, %s -> %d",
                    self.vuln_label, vid, self.safe_label, sid)
        return vid, sid

    def _first_single_token(self, candidates: Sequence[str]) -> int | None:
        for s in candidates:
            ids = self.tokenizer.encode(s, add_special_tokens=False)
            if len(ids) == 1:
                return ids[0]
        return None

    # ------------------------------------------------------------------ #
    # Classification
    # ------------------------------------------------------------------ #
    @torch.inference_mode()
    def classify(
        self,
        code_slice: str,
        threshold: float,
    ) -> ClassificationOutput:
        """Classify a single slice. Threshold should come from calibration."""
        prompt = render_detection_prompt(code_slice)
        return self._classify_prompt(prompt, threshold)

    @torch.inference_mode()
    def classify_batch(
        self,
        code_slices: Sequence[str],
        threshold: float,
        batch_size: int = 4,
    ) -> list[ClassificationOutput]:
        """Naive batched classification.

        We pad to the longest in the batch; the LM head reduction makes this
        cheap relative to autoregressive generation.
        """
        outputs: list[ClassificationOutput] = []
        prompts = [render_detection_prompt(s) for s in code_slices]
        for i in range(0, len(prompts), batch_size):
            chunk = prompts[i : i + batch_size]
            outputs.extend(self._classify_chunk(chunk, threshold))
        return outputs

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _classify_prompt(self, prompt: str, threshold: float) -> ClassificationOutput:
        ids = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_context,
        ).to(self.model.device)
        # We want logits at the *last* position — that's where the model would
        # emit its first generated token.
        out = self.model(**ids, use_cache=False)
        last_logits = out.logits[0, -1, :]  # (vocab,)
        return self._reduce_and_decide(last_logits, threshold)

    def _classify_chunk(
        self, prompts: list[str], threshold: float,
    ) -> list[ClassificationOutput]:
        # Pad on the left so the "last position" is always meaningful.
        original_side = self.tokenizer.padding_side
        self.tokenizer.padding_side = "left"
        try:
            enc = self.tokenizer(
                prompts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.max_context,
            ).to(self.model.device)
            out = self.model(**enc, use_cache=False)
            # Last position per row in the *padded* batch.
            last_logits = out.logits[:, -1, :]
            results = []
            for row in last_logits:
                results.append(self._reduce_and_decide(row, threshold))
            return results
        finally:
            self.tokenizer.padding_side = original_side

    def _reduce_and_decide(
        self, full_logits: torch.Tensor, threshold: float,
    ) -> ClassificationOutput:
        # Pick the two rows we care about and softmax over just them.
        vuln_logit = full_logits[self.vuln_token_id].item()
        safe_logit = full_logits[self.safe_token_id].item()
        probs = F.softmax(
            torch.tensor([vuln_logit, safe_logit], dtype=torch.float32), dim=-1,
        )
        p_vuln, p_safe = probs[0].item(), probs[1].item()
        return ClassificationOutput(
            is_vulnerable=p_vuln > threshold,
            probability_vulnerable=p_vuln,
            probability_safe=p_safe,
            threshold_used=threshold,
            raw_logits=(vuln_logit, safe_logit),
        )
