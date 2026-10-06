"""Acquire disjoint mixed-label scores through the same Q -> Joern -> D stages."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .calibrate import calibrate
from .runner import classify_slices, extract_slices, generate_queries
from .schema import Case, digest, index_jsonl, read_jsonl, run_specs


def _samples(manifest: Path, analysis_clusters: set[str]) -> tuple[list[Case], dict[str, dict]]:
    cases: list[Case] = []
    metadata: dict[str, dict] = {}
    split_clusters = {"calibration": set(), "specificity": set()}
    for row in read_jsonl(manifest):
        sid, cluster, split, label = (row[key] for key in
                                      ("sample_id", "cluster_id", "split", "label"))
        if (not isinstance(sid, str) or not sid or sid in metadata or
                not isinstance(cluster, str) or not cluster or
                split not in split_clusters or label not in (0, 1) or
                cluster in analysis_clusters):
            raise ValueError(f"Invalid or overlapping calibration sample {sid!r}")
        if split == "specificity" and label != 0:
            raise ValueError("Specificity samples must be safe")
        source_path = manifest.parent / row["source"]
        source = source_path.read_text(encoding="utf-8")
        split_clusters[split].add(cluster)
        metadata[sid] = {"sample_id": sid, "cluster_id": cluster, "split": split,
                         "label": label, "source_sha256": digest(source)}
        # Stage runners use only U/source fields. No vulnerable referent is
        # invented for safe calibration examples.
        cases.append(Case(sid, cluster, row.get("cwe", "calibration"), {"U": source},
                          {"U": row["source"]}, {}, {}, {}, None, None))
    if not cases or split_clusters["calibration"] & split_clusters["specificity"]:
        raise ValueError("Calibration/specificity clusters must be present and disjoint")
    return cases, metadata


ABSTENTION_POLICIES = ("fail", "exclude")


def _abstention_summary(metadata: dict[str, dict], failures: list[dict]) -> dict[str, Any]:
    failed = {row["sample_id"] for row in failures}
    summary: dict[str, dict[str, dict[str, int]]] = {}
    for sample in metadata.values():
        cell = summary.setdefault(sample["split"], {}).setdefault(
            str(sample["label"]), {"enrolled": 0, "scored": 0, "abstained": 0})
        cell["enrolled"] += 1
        cell["abstained" if sample["sample_id"] in failed else "scored"] += 1
    statuses = Counter(f"{row['query_status']}/{row['slice_status']}/{row['detector_status']}"
                       for row in failures)
    return {"by_split_and_label": summary, "failure_statuses": dict(statuses)}


def score_and_calibrate(analysis_cases: list[Case], manifest: Path, work: Path,
                        cfg: dict[str, Any]) -> dict[str, Any]:
    """Persist every stage, then select a threshold under a predeclared abstention policy.

    ``detector_calibration_abstentions`` in the config decides what happens
    when a sample yields no D score (a Q, Joern or context failure): ``fail``
    (default) refuses a threshold; ``exclude`` calibrates on the scored samples
    and reports abstentions by split and label, since safe code often yields
    no flow and therefore no slice.
    """
    policy = cfg.get("detector_calibration_abstentions", "fail")
    if policy not in ABSTENTION_POLICIES:
        raise ValueError(f"detector_calibration_abstentions must be one of {ABSTENTION_POLICIES}")
    cases, metadata = _samples(manifest, {case.cluster_id for case in analysis_cases})
    stage_dir = work / "calibration_run"
    stage_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(manifest.read_bytes())
    # The threshold is this step's output, so it is not one of its inputs.
    h.update(json.dumps({k: v for k, v in cfg.items() if k != "threshold"},
                        sort_keys=True).encode("utf-8"))
    for sample in metadata.values():
        h.update(json.dumps(sample, sort_keys=True).encode("utf-8"))
    lock = stage_dir / "inputs.json"
    fingerprint = h.hexdigest()
    if lock.exists() and json.loads(lock.read_text(encoding="utf-8"))["fingerprint"] != fingerprint:
        raise ValueError("Calibration inputs changed; use a new --work directory")
    if not lock.exists():
        lock.write_text(json.dumps({"fingerprint": fingerprint,
                                    "samples": list(metadata.values()),
                                    "query_revision": cfg["query_revision"],
                                    "detector_revision": cfg["detector_revision"],
                                    "detector_base_revision": cfg["detector_base_revision"],
                                    "joern_digest": cfg["joern_digest"]}, indent=2) + "\n",
                        encoding="utf-8")
    # Verdicts in calibration_run/detector.jsonl use a placeholder threshold
    # and are never read; only p_vulnerable enters the sweep.
    scoring_cfg = {**cfg, "threshold": cfg.get("threshold", 0.5)}
    generate_queries(cases, stage_dir, scoring_cfg, repeats=1)
    extract_slices(cases, stage_dir, scoring_cfg, repeats=1)
    classify_slices(cases, stage_dir, scoring_cfg, repeats=1)
    queries = index_jsonl(stage_dir / "queries.jsonl", "run_id")
    slices = index_jsonl(stage_dir / "slices.jsonl", "run_id")
    detector = index_jsonl(stage_dir / "detector.jsonl", "run_id")
    rows, failures = [], []
    for spec in run_specs(cases, repeats=1):
        rid = spec["run_id"]
        meta = metadata[spec["case_id"]]
        q, slc, det = (records.get(rid, {}) for records in (queries, slices, detector))
        if (q.get("status"), slc.get("status"), det.get("status")) != ("ok", "ok", "ok"):
            failures.append({**meta, "run_id": rid, "query_status": q.get("status"),
                             "slice_status": slc.get("status"),
                             "detector_status": det.get("status")})
        else:
            rows.append({**meta, "run_id": rid, "p_vulnerable": det["p_vulnerable"]})
    score_path = work / "calibration_scores.jsonl"
    score_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                          encoding="utf-8")
    (work / "calibration_failures.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in failures), encoding="utf-8")
    abstentions = _abstention_summary(metadata, failures)
    if failures and policy == "fail":
        raise RuntimeError(f"{len(failures)} calibration samples lack Q -> Joern -> D scores; "
                           "inspect calibration_failures.jsonl. To calibrate on scored samples, "
                           "predeclare detector_calibration_abstentions='exclude' and use a "
                           "new calibration --work directory")
    result = calibrate(rows, {case.cluster_id for case in analysis_cases})
    result["abstention_policy"] = policy
    result["abstentions"] = abstentions
    result["score_sha256"] = hashlib.sha256(score_path.read_bytes()).hexdigest()
    result["calibration_input_fingerprint"] = fingerprint
    (work / "calibration.json").write_text(json.dumps(result, indent=2) + "\n",
                                            encoding="utf-8")
    return result
