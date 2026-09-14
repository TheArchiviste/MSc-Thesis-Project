"""LLMxCPG-D: vulnerability classifier with a reduced LM head.

This is the most surgical part of the paper (§4.2). Instead of running open-ended
generation and parsing the first word, we:

  1. Take the trained LM at hand and grab the rows of its `lm_head.weight`
     matrix that correspond to the tokens "No" and "Yes".
  2. Replace the LM head with a 2-output classification head built from those
     rows alone.
  3. At inference, do a single forward pass to the last hidden state, project
     through the reduced head, softmax over the two classes, and threshold.

This avoids the cost of full-vocabulary decoding and ensures the model can
*only* output one of the two labels we care about — a much stronger guarantee
than prompt-engineering "respond with one word".

Subtleties:
  - Tokenisers split words differently. Each label must be a single token
    in some tokenisers and multiple in others. We require it to be a *single*
    token and fail loudly otherwise — multi-token labels would need a
    different reduction (e.g., scoring full sequences). Practically this is
    fine for the released Qwen-family detector and its Yes/No labels.
  - The hidden state we project from is the last position of the prompt — the
    position the model would generate the answer from.
  - We disable KV cache during this single-step forward; it would help on
    long generation but not here.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

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
        vulnerable_token: str = "Yes",
        safe_token: str = "No",
        dtype: str = "bfloat16",
        device: str = "auto",
        max_context: int = 16_384,
        revision: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.vuln_label = vulnerable_token
        self.safe_label = safe_token
        self.max_context = max_context

        try:
            torch_dtype = {
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }[dtype]
        except KeyError as exc:
            raise ValueError("dtype must be float16, bfloat16, or float32.") from exc

        logger.info("Loading detector model: %s", model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, revision=revision, trust_remote_code=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch_dtype,
            device_map=device,
            trust_remote_code=True,
            revision=revision,
        )
        self.model.eval()

        # Replace the full-vocabulary projection once. The class order matches
        # the original implementation: [safe/No, vulnerable/Yes].
        self.vuln_token_id, self.safe_token_id = self._resolve_token_ids()
        self._install_reduced_head()

    @classmethod
    def from_config(cls, cfg: ModelConfig, **kwargs) -> VulnerabilityClassifier:
        return cls(
            model_path=cfg.detector_model_path,
            vulnerable_token=cfg.vulnerable_token,
            safe_token=cfg.safe_token,
            dtype=cfg.detector_dtype,
            max_context=cfg.detector_max_context,
            revision=cfg.detector_model_revision,
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

    def _install_reduced_head(self) -> None:
        """Replace the model output projection with the two label rows."""
        original = self.model.get_output_embeddings()
        if original is None or not hasattr(original, "weight"):
            raise TypeError("Detector model does not expose a writable output embedding.")

        weight = original.weight
        if weight.device.type == "meta":
            raise RuntimeError("Cannot reduce an output head that is still on the meta device.")

        has_bias = getattr(original, "bias", None) is not None
        reduced = torch.nn.Linear(
            weight.shape[1],
            2,
            bias=has_bias,
            device=weight.device,
            dtype=weight.dtype,
        )
        with torch.no_grad():
            reduced.weight.copy_(weight[[self.safe_token_id, self.vuln_token_id]])
            if has_bias:
                reduced.bias.copy_(original.bias[[self.safe_token_id, self.vuln_token_id]])
        reduced.requires_grad_(False)
        self.model.set_output_embeddings(reduced)
        logger.info("Installed reduced detector head with shape %s", tuple(reduced.weight.shape))

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
            add_special_tokens=False,
        ).to(self.model.device)
        # We want logits at the *last* position — that's where the model would
        # emit its first generated token.
        out = self.model(**ids, use_cache=False)
        last_logits = out.logits[0, -1, :]  # (safe, vulnerable)
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
                add_special_tokens=False,
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
        self, class_logits: torch.Tensor, threshold: float,
    ) -> ClassificationOutput:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1.")
        if class_logits.shape[-1] != 2:
            raise RuntimeError(
                f"Expected the reduced detector head to emit 2 logits, got {class_logits.shape[-1]}."
            )
        safe_logit, vuln_logit = class_logits.float().unbind(-1)
        probs = F.softmax(class_logits.float(), dim=-1)
        p_safe, p_vuln = probs[0].item(), probs[1].item()
        return ClassificationOutput(
            is_vulnerable=p_vuln >= threshold,
            probability_vulnerable=p_vuln,
            probability_safe=p_safe,
            threshold_used=threshold,
            raw_logits=(vuln_logit.item(), safe_logit.item()),
        )
