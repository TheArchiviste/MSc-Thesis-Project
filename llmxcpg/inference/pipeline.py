"""End-to-end pipeline.

`LLMxCPGPipeline` composes:
    QueryGenerator  →  Joern + SliceExtractor  →  VulnerabilityClassifier

It returns a `ClassificationResult` rich enough to debug each stage
independently — query, slice, probabilities — because the literature review's
strongest critique is that two-stage pipelines obscure where errors come from.
We don't want that.

Failure modes are explicit in the result:
    - `query_parse_failed`: Q produced unparseable output.
    - `slice_failed`: Joern rejected the queries or returned empty results.
In either case, `is_vulnerable` is left `None` and the caller can decide
whether to fall back to whole-file classification or simply abstain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from llmxcpg.config import Config, DEFAULT_THRESHOLDS
from llmxcpg.joern.client import JoernClient
from llmxcpg.slicing.extractor import Slice, SliceExtractor, SliceFailure
from llmxcpg.inference.query_generator import QueryGenerator, QueryGenerationOutput
from llmxcpg.inference.classifier import VulnerabilityClassifier, ClassificationOutput


logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Everything the pipeline knows about a single input."""
    source_code: str
    is_vulnerable: Optional[bool]
    probability_vulnerable: Optional[float] = None
    probability_safe: Optional[float] = None
    threshold: Optional[float] = None
    # Stage outputs
    query_output: Optional[QueryGenerationOutput] = None
    slice: Optional[Slice] = None
    classification: Optional[ClassificationOutput] = None
    # Failure tracking
    failure_stage: Optional[str] = None  # "query_parse" | "slice" | None
    failure_reason: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.is_vulnerable is not None


class LLMxCPGPipeline:
    """The full LLMxCPG inference pipeline."""

    def __init__(
        self,
        query_generator: QueryGenerator,
        classifier: VulnerabilityClassifier,
        joern: JoernClient,
        threshold: float = 0.5,
    ) -> None:
        self.q = query_generator
        self.d = classifier
        self.joern = joern
        self.slicer = SliceExtractor(joern)
        self.threshold = threshold

    @classmethod
    def from_config(
        cls,
        config: Config,
        dataset_threshold_key: str | None = None,
    ) -> "LLMxCPGPipeline":
        """Build a pipeline from a `Config`. Picks the per-dataset threshold if asked."""
        thr = (
            DEFAULT_THRESHOLDS.get(dataset_threshold_key, config.threshold)
            if dataset_threshold_key
            else config.threshold
        )
        joern = JoernClient(
            host=config.joern.host,
            port=config.joern.port,
            auth_user=config.joern.auth_user,
            auth_pass=config.joern.auth_pass,
        )
        q = QueryGenerator.from_config(config.models)
        d = VulnerabilityClassifier.from_config(config.models)
        return cls(query_generator=q, classifier=d, joern=joern, threshold=thr)

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def detect(
        self,
        source_code: str,
        threshold: float | None = None,
        project_name: str = "snippet",
    ) -> ClassificationResult:
        """Run the full pipeline on one code sample."""
        thr = threshold if threshold is not None else self.threshold
        result = ClassificationResult(
            source_code=source_code,
            is_vulnerable=None,
            threshold=thr,
        )

        # Stage 1: query generation
        q_out = self.q.generate(source_code)
        result.query_output = q_out
        if not q_out.parsed_ok:
            result.failure_stage = "query_parse"
            result.failure_reason = q_out.error
            logger.warning("Query parse failure: %s", q_out.error)
            return result

        # Stage 2: slice construction
        try:
            slc = self.slicer.extract(
                source_code, q_out.queries, project_name=project_name,
            )
        except SliceFailure as e:
            result.failure_stage = "slice"
            result.failure_reason = str(e)
            logger.warning("Slice failure: %s", e)
            return result

        result.slice = slc

        # Stage 3: classification on the slice
        cls_out = self.d.classify(slc.code, threshold=thr)
        result.classification = cls_out
        result.is_vulnerable = cls_out.is_vulnerable
        result.probability_vulnerable = cls_out.probability_vulnerable
        result.probability_safe = cls_out.probability_safe
        return result

    def detect_batch(
        self,
        source_codes: list[str],
        threshold: float | None = None,
    ) -> list[ClassificationResult]:
        """Process a batch. Query generation is batched in vLLM; slicing is
        sequential because it shares Joern session state."""
        thr = threshold if threshold is not None else self.threshold

        # Stage 1: batch query generation.
        q_outs = self.q.generate_batch(source_codes)

        # Stages 2+3: per-sample (Joern session is per-sample anyway).
        results: list[ClassificationResult] = []
        slices_for_d: list[tuple[int, str]] = []  # (idx, slice_code)

        for i, (src, q_out) in enumerate(zip(source_codes, q_outs)):
            r = ClassificationResult(source_code=src, is_vulnerable=None,
                                     threshold=thr, query_output=q_out)
            if not q_out.parsed_ok:
                r.failure_stage = "query_parse"
                r.failure_reason = q_out.error
                results.append(r)
                continue
            try:
                slc = self.slicer.extract(src, q_out.queries, project_name=f"snip_{i}")
                r.slice = slc
                slices_for_d.append((i, slc.code))
            except SliceFailure as e:
                r.failure_stage = "slice"
                r.failure_reason = str(e)
            results.append(r)

        # Stage 3: batch the classifier over all successful slices.
        if slices_for_d:
            indices, codes = zip(*slices_for_d)
            cls_outs = self.d.classify_batch(list(codes), threshold=thr)
            for idx, cls_out in zip(indices, cls_outs):
                results[idx].classification = cls_out
                results[idx].is_vulnerable = cls_out.is_vulnerable
                results[idx].probability_vulnerable = cls_out.probability_vulnerable
                results[idx].probability_safe = cls_out.probability_safe

        return results
