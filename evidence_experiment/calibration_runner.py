"""Acquire disjoint mixed-label scores through the same Q -> Joern -> D stages."""

from __future__ import annotations

import hashlib
import json
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


def score_and_calibrate(analysis_cases: list[Case], manifest: Path, work: Path,
                        cfg: dict[str, Any]) -> dict[str, Any]:
    """Persist every stage and refuse a threshold when any enrolled score is missing."""
    cases, metadata = _samples(manifest, {case.cluster_id for case in analysis_cases})
    stage_dir = work / "calibration_run"
    stage_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(manifest.read_bytes())
    h.update(json.dumps(cfg, sort_keys=True).encode("utf-8"))
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
    generate_queries(cases, stage_dir, cfg, repeats=1)
    extract_slices(cases, stage_dir, cfg, repeats=1)
    classify_slices(cases, stage_dir, cfg, repeats=1)
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
    if failures:
        raise RuntimeError(f"{len(failures)} calibration samples lack Q -> Joern -> D scores; "
                           "inspect calibration_failures.jsonl before selecting a threshold")
    result = calibrate(rows, {case.cluster_id for case in analysis_cases})
    result["score_sha256"] = hashlib.sha256(score_path.read_bytes()).hexdigest()
    result["calibration_input_fingerprint"] = fingerprint
    (work / "calibration.json").write_text(json.dumps(result, indent=2) + "\n",
                                            encoding="utf-8")
    return result
