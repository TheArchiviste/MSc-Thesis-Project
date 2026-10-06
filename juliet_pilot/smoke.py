"""Run the four Juliet cases through the experiment interfaces without GPU/Joern.

Q uses the original pipeline's explicit dummy mode. Joern returns every source
line, and D returns a fixed synthetic score. This is an integration check only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# Let `python juliet_pilot/<script>.py` import the experiment from a checkout
# whose editable install predates the evidence_experiment package entry.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidence_experiment.analysis import analyze
from evidence_experiment.review import build_queue, write_queue
from evidence_experiment.runner import (
    classify_slices,
    extract_slices,
    generate_queries,
    load_config,
)
from evidence_experiment.schema import load_cases, read_jsonl
from llmxcpg.joern.client import QueryResult

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "generated" / "cases.jsonl"
CONFIG = ROOT / "smoke_config.json"


class FullSourceJoern:
    """Test double for the Joern interface; it does not execute CPGQL."""

    def __init__(self) -> None:
        self.source: str | None = None
        self.resets = 0

    def import_code(self, source: str, project_name: str = "snippet") -> None:
        if self.source is not None:
            raise RuntimeError("Prior simulated Joern session was not reset")
        self.source = source

    def run(self, query: str) -> QueryResult:
        if self.source is None:
            raise RuntimeError("No source imported")
        if "slice_lines" in query:
            numbers = list(range(1, len(self.source.splitlines()) + 1))
            rendered = "List(" + ", ".join(map(str, numbers)) + ")"
            return QueryResult(rendered, rendered, True)
        return QueryResult("List()", "List()", True)

    def reset(self) -> None:
        self.source = None
        self.resets += 1


class FixedScoreDetector:
    """Test double for D; its fixed verdict is never a research observation."""

    def __init__(self) -> None:
        self.input_hashes: list[str] = []

    def classify(self, code: str, threshold: float) -> SimpleNamespace:
        self.input_hashes.append(hashlib.sha256(code.encode()).hexdigest())
        return SimpleNamespace(is_vulnerable=False, probability_vulnerable=0.25,
                               probability_safe=0.75, raw_logits=(1.0, 0.0))


def run(work: Path) -> dict:
    if not MANIFEST.exists():
        raise FileNotFoundError("Run python juliet_pilot/prepare.py first")
    cfg = load_config(CONFIG)
    if cfg.get("query_engine") != "dummy" or not cfg.get("allow_dummy"):
        raise ValueError("The smoke run requires explicit dummy mode")
    cases = load_cases(MANIFEST)
    work.mkdir(parents=True, exist_ok=True)
    graph = FullSourceJoern()
    detector = FixedScoreDetector()
    repeats = 3
    prior_slices = len(read_jsonl(work / "slices.jsonl"))
    prior_detector = len(read_jsonl(work / "detector.jsonl"))

    # This invokes the pinned QueryGenerator in its documented dummy mode.
    generate_queries(cases, work, cfg, repeats=repeats)
    extract_slices(cases, work, cfg, repeats=repeats, joern=graph)
    classify_slices(cases, work, cfg, repeats=repeats, classifier=detector)
    packets, key = build_queue(cases, work, repeats)
    write_queue(work, packets, key, {"duplicate_fraction": 0.0, "seed": 0, "repeats": repeats})

    # No invented human decisions. Successfully produced slices stay uncertain.
    assessments = work / "assessments.jsonl"
    adjudications = work / "adjudications.jsonl"
    assessments.touch()
    adjudications.touch()
    analysis = analyze(cases, work, assessments, adjudications, repeats=repeats)
    (work / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n",
                                        encoding="utf-8")

    queries = read_jsonl(work / "queries.jsonl")
    slices = read_jsonl(work / "slices.jsonl")
    classifications = read_jsonl(work / "detector.jsonl")
    expected = len(cases) * repeats
    if any(len(rows) != expected for rows in (queries, slices, classifications)):
        raise AssertionError("Incomplete phase grid")
    if (any(row["status"] != "ok" for row in (*queries, *slices, *classifications))
            or graph.resets != expected - prior_slices
            or len(detector.input_hashes) != expected - prior_detector):
        raise AssertionError("A smoke phase or simulated reset failed")
    baseline_adequacy = analysis["rq1"]["adequacy"]
    if baseline_adequacy.get("uncertain") != len(cases):
        raise AssertionError("Unreviewed evidence must remain uncertain")
    report = {
        "kind": "simulation_only",
        "pipeline_commit": cfg["pipeline_commit"],
        "cases": len(cases),
        "query_runs": len(queries),
        "slice_runs": len(slices),
        "detector_runs": len(classifications),
        "blind_packets": len(packets),
        "joern_resets": graph.resets,
        "resumed_from_slices": prior_slices,
        "resumed_from_detector": prior_detector,
        "baseline_adequacy": baseline_adequacy,
        "synthetic_q": "pipeline dummy query bundle, identical on every input",
        "synthetic_joern": "returns all source lines without running CPGQL",
        "synthetic_d": "fixed safe verdict and 0.25 vulnerable probability",
        "research_results": False,
    }
    (work / "smoke_summary.json").write_text(json.dumps(report, indent=2) + "\n",
                                             encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.work), indent=2))
