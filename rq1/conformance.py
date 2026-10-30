"""Run the complete fixed selector on a known, synthetic C fixture, on CPU."""
from __future__ import annotations

from evidence_experiment.locks import now, policy
from evidence_experiment.runner import extract_one
from evidence_experiment.schema import write_json

SOURCE = """void fixture(int n) {
    char buffer[4];
    if (n >= 0 && n < 4) {
        buffer[n] = 1;
    }
}
"""
QUERIES = [
    'val source = cpg.method.nameExact("fixture").parameter.nameExact("n").l',
    'val sink = cpg.call.nameExact("<operator>.indirectIndexAccess").argument(2).l',
    'val execution_path = sink.reachableByFlows(source).l',
]


def check(config):
    from .joern_worker import fresh_worker
    from .setup import ROOT, corpus_contract, load_config, verify_corpus, verify_implementation
    verify_corpus()
    verify_implementation()
    cfg = load_config(config)
    destination = ROOT / cfg["joern_capability_file"]
    result = {"utc": now(), "ready": False, "synthetic": False, "fixture_only": True,
              "meaning": "Real Joern on a synthetic capability fixture; not dissertation data.",
              "corpus_contract": corpus_contract(), "policy": policy(cfg),
              "source": SOURCE, "queries": QUERIES}
    try:
        with fresh_worker(cfg, destination.parent / "worker") as client:
            outcome = extract_one(client, SOURCE, QUERIES, "rq1_capability")
        result["outcome"] = outcome
        result["ready"] = (outcome["status"] == "ok" and
                           4 in outcome["slice_lines"] and
                           {1, 3, 4, 5, 6} <= set(outcome["rendered_lines"]))
    except Exception as exc:  # noqa: BLE001 - preserve unexpected failures as explicit diagnostic records
        result["error"] = repr(exc)
    write_json(destination, result)
    (destination.parent / "readiness.md").write_text(
        f"# Full selector capability\n\nResult: **{'PASS' if result['ready'] else 'BLOCKED'}**.\n\n"
        "This tests import, fixed execution path, interacters, backward slice and enclosing-block rendering.\n"
        "It does not test Q generation or measure evidence adequacy. See readiness.json and worker logs.\n")
    print(f"Full-selector capability: {'PASS' if result['ready'] else 'BLOCKED'}; {destination}")
    return result["ready"]
