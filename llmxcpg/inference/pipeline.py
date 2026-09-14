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
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from llmxcpg.config import DEFAULT_THRESHOLDS, Config
from llmxcpg.inference.query_generator import QueryGenerationOutput, QueryGenerator
from llmxcpg.joern.client import JoernClient
from llmxcpg.slicing.extractor import Slice, SliceExtractor, SliceFailure

if TYPE_CHECKING:
    from llmxcpg.inference.classifier import ClassificationOutput, VulnerabilityClassifier


logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Everything the pipeline knows about a single input."""
    source_code: str
    is_vulnerable: bool | None
    probability_vulnerable: float | None = None
    probability_safe: float | None = None
    threshold: float | None = None
    # Stage outputs
    query_output: QueryGenerationOutput | None = None
    slice: Slice | None = None
    classification: ClassificationOutput | None = None
    # Failure tracking
    failure_stage: str | None = None  # "query_parse" | "slice" | None
    failure_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.is_vulnerable is not None


class LLMxCPGPipeline:
    """The full LLMxCPG inference pipeline."""

    def __init__(
        self,
        query_generator: QueryGenerator,
        classifier: VulnerabilityClassifier | None,
        joern: JoernClient,
        threshold: float = 0.5,
        classifier_factory: Callable[[], VulnerabilityClassifier] | None = None,
        release_local_query_model_before_detection: bool = False,
    ) -> None:
        self.q = query_generator
        self._classifier = classifier
        self._classifier_factory = classifier_factory
        self.joern = joern
        self.slicer = SliceExtractor(joern)
        self.threshold = threshold
        self.release_local_query_model_before_detection = (
            release_local_query_model_before_detection
        )

    @classmethod
    def from_config(
        cls,
        config: Config,
        dataset_threshold_key: str | None = None,
    ) -> LLMxCPGPipeline:
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
            local_input_dir=config.joern.local_input_dir,
            server_input_dir=config.joern.server_input_dir,
        )
        q = QueryGenerator.from_config(config.models)

        def load_classifier() -> VulnerabilityClassifier:
            from llmxcpg.inference.classifier import VulnerabilityClassifier

            return VulnerabilityClassifier.from_config(config.models)

        return cls(
            query_generator=q,
            classifier=None,
            classifier_factory=load_classifier,
            joern=joern,
            threshold=thr,
            release_local_query_model_before_detection=(
                config.models.release_local_query_model_before_detection
            ),
        )

    def _get_classifier(self) -> VulnerabilityClassifier:
        if self._classifier is None:
            if self.release_local_query_model_before_detection and self.q.uses_local_gpu:
                logger.info("Releasing local query model before loading detector.")
                self.q.close()
            if self._classifier_factory is None:
                raise RuntimeError("No detector or detector factory was configured.")
            self._classifier = self._classifier_factory()
        return self._classifier

    @property
    def d(self) -> VulnerabilityClassifier:
        """Backward-compatible access to the lazily loaded detector."""
        return self._get_classifier()

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
        finally:
            try:
                self.joern.reset()
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask the result
                logger.warning("Joern cleanup failed: %s", exc)

        result.slice = slc

        # Stage 3: classification on the slice
        cls_out = self._get_classifier().classify(slc.code, threshold=thr)
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
        if not source_codes:
            return []
        thr = threshold if threshold is not None else self.threshold

        # Stage 1: batch query generation.
        q_outs = self.q.generate_batch(source_codes)
        if len(q_outs) != len(source_codes):
            raise RuntimeError(
                f"Query engine returned {len(q_outs)} outputs for {len(source_codes)} inputs."
            )

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
            finally:
                try:
                    self.joern.reset()
                except Exception as exc:  # noqa: BLE001 - cleanup must not mask the result
                    logger.warning("Joern cleanup failed: %s", exc)
            results.append(r)

        # Stage 3: batch the classifier over all successful slices.
        if slices_for_d:
            indices, codes = zip(*slices_for_d)
            cls_outs = self._get_classifier().classify_batch(list(codes), threshold=thr)
            if len(cls_outs) != len(codes):
                raise RuntimeError(
                    f"Detector returned {len(cls_outs)} outputs for {len(codes)} slices."
                )
            for idx, cls_out in zip(indices, cls_outs):
                results[idx].classification = cls_out
                results[idx].is_vulnerable = cls_out.is_vulnerable
                results[idx].probability_vulnerable = cls_out.probability_vulnerable
                results[idx].probability_safe = cls_out.probability_safe

        return results
