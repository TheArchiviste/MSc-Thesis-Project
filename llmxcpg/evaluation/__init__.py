"""Evaluation: classification metrics, per-CWE breakdowns, and query-quality audit."""

from llmxcpg.evaluation.audit import (
    QueryAudit,
    audit_queries,
    fleiss_kappa,
    summarise_audit,
)
from llmxcpg.evaluation.metrics import (
    Metrics,
    classification_metrics,
    metrics_by_cwe,
    reduction_ratio_stats,
)

__all__ = [
    "Metrics",
    "QueryAudit",
    "audit_queries",
    "classification_metrics",
    "fleiss_kappa",
    "metrics_by_cwe",
    "reduction_ratio_stats",
    "summarise_audit",
]
