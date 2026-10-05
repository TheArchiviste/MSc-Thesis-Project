"""Resumable Q -> Joern -> D phases without calling detect/detect_batch.

One Joern client is used sequentially; use a separate process and Joern server
per parallel worker. The complete query/response trace is retained for RQ3.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .schema import Case, append_jsonl, digest, index_jsonl, run_specs

log = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    pinned = "7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b"
    if cfg.get("pipeline_commit") != pinned:
        raise ValueError(f"Experiment requires pinned pipeline commit {pinned}")
    if not 0 <= cfg["threshold"] <= 1:
        raise ValueError("threshold must be in [0, 1] and frozen before analysis")
    if cfg.get("query_engine", "vllm") == "dummy" and not cfg.get("allow_dummy", False):
        raise ValueError("dummy query engine is for smoke tests only")
    if not cfg.get("allow_dummy", False) and not all(
        cfg.get(key) for key in ("query_revision", "detector_revision", "joern_digest")
    ):
        raise ValueError("pin both model revisions and the Joern image digest")
    return cfg


def _models(cfg: dict[str, Any]):
    from llmxcpg.config import ModelConfig

    return ModelConfig(
        query_model_path=cfg.get("query_model", "QCRI/LLMxCPG-Q"),
        query_model_revision=cfg.get("query_revision"),
        query_engine=cfg.get("query_engine", "vllm"),
        query_base_url=cfg.get("query_base_url"),
        query_temperature=cfg.get("query_temperature", 0.0),
        detector_model_path=cfg.get("detector_model", "QCRI/LLMxCPG-D"),
        detector_model_revision=cfg.get("detector_revision"),
    )


def _sources(cases: list[Case]) -> dict[str, Case]:
    return {case.case_id: case for case in cases}


def _check_q_context(q, code: str) -> None:
    """Fail closed instead of silently truncating a query prompt."""
    if not hasattr(q, "_llm") or q._llm is None or not hasattr(q._llm, "get_tokenizer"):
        return  # external server owns token limits; its configuration must be recorded
    from llmxcpg.prompts import render_query_prompt

    prompt = q._format_vllm_prompt(render_query_prompt(code))
    n = len(q._llm.get_tokenizer().encode(prompt))
    if n + 2048 > q.max_context:
        raise ValueError(f"Q prompt + generation exceeds context ({n} + 2048)")


def generate_queries(cases: list[Case], work: Path, cfg: dict[str, Any],
                     repeats: int = 3, batch_size: int = 32, generator=None) -> None:
    """Generate new queries for U, TM and TN; fixed and rule arms reuse bundles."""
    all_specs = run_specs(cases, repeats)
    by_case = _sources(cases)
    dest = work / "queries.jsonl"
    done = index_jsonl(dest, "run_id")
    pending = [s for s in all_specs if s["arm"] in ("U", "TM", "TN")
               and s["run_id"] not in done]
    if not pending:
        return
    owned = generator is None
    if owned:
        from llmxcpg.inference.query_generator import QueryGenerator
        q = QueryGenerator.from_config(_models(cfg))
    else:
        q = generator
    try:
        for i in range(0, len(pending), batch_size):
            chunk = pending[i:i + batch_size]
            sources = [by_case[s["case_id"]].source_for(s["arm"]) for s in chunk]
            for source in sources:
                _check_q_context(q, source)
            outs = q.generate_batch(sources)
            if len(outs) != len(chunk):
                raise RuntimeError("Q returned a different number of results")
            for spec, out in zip(chunk, outs):
                append_jsonl(dest, {"run_id": spec["run_id"],
                                    "status": "ok" if out.parsed_ok else "query_parse",
                                    "queries": out.queries, "raw_text": out.raw_text,
                                    "error": out.error})
    finally:
        if owned:
            q.close()


class TracedJoern:
    """Record each call, including a failing call that SliceExtractor omits."""

    def __init__(self, inner):
        self.inner = inner
        self.events: list[dict[str, Any]] = []

    def import_code(self, source, project_name="snippet"):
        try:
            self.inner.import_code(source, project_name=project_name)
        except Exception as exc:
            self.events.append({"stage": "graph_import", "success": False, "error": str(exc)})
            raise
        self.events.append({"stage": "graph_import", "success": True})

    def run(self, query):
        stage = ("slice_construction" if "slice_lines" in query else
                 "context_expansion" if "interacters" in query else
                 "query_execution")
        try:
            result = self.inner.run(query)
        except Exception as exc:
            self.events.append({"stage": stage, "query": query,
                                "success": False, "error": str(exc)})
            raise
        self.events.append({"stage": stage, "query": query,
                            "success": result.success, "stdout": result.stdout,
                            "value": str(result.value)})
        return result

    def reset(self):
        return self.inner.reset()


def _failure_status(message: str) -> str:
    if message.startswith("Q-generated CPGQL failed"):
        return "query_exec"
    if message.startswith("Backward slice produced no lines"):
        return "empty_slice"
    if message.startswith("Could not bind"):
        return "path_binding"
    if message.startswith("Interacters query failed"):
        return "context_exec"
    if message.startswith("Backward slice query failed"):
        return "slice_exec"
    if message.startswith(("No CPGQL", "The final generated query",
                           "Generated CPGQL query")):
        return "query_invalid"
    return "unknown_slice_failure"  # never silently recode an unfamiliar error


def _rendered_lines(source: str, lines: list[int]) -> list[int]:
    from llmxcpg.slicing.reconstruction import _enclosing_function_lines

    original = source.splitlines()
    selected = {n for n in lines if 1 <= n <= len(original)}
    for n in list(selected):
        box = _enclosing_function_lines(original, n)
        if box:
            selected.update(box)
    return sorted(selected)


def _reconstruction_check(source: str, selected: list[int], rendered: list[int], code: str):
    from llmxcpg.slicing.reconstruction import reconstruct_code_from_lines

    if code != reconstruct_code_from_lines(source, selected):
        raise RuntimeError("slice text does not match pinned reconstruction")
    lines = source.splitlines()
    out: list[str] = []
    last = 0
    for n in rendered:
        if n - last > 1 and last:
            out.append("")
        out.append(lines[n - 1])
        last = n
    if "\n".join(out) != code:
        raise RuntimeError("rendered line map disagrees with the detector input")


def extract_one(joern, source: str, queries: list[str], project_name: str) -> dict[str, Any]:
    from llmxcpg.joern.client import JoernError
    from llmxcpg.slicing.extractor import SliceExtractor, SliceFailure

    traced = TracedJoern(joern)
    try:
        slc = SliceExtractor(traced).extract(source, queries, project_name=project_name)
        selected = sorted(set(slc.line_numbers))
        rendered = _rendered_lines(source, selected)
        _reconstruction_check(source, selected, rendered, slc.code)
        return {"status": "ok", "slice_lines": selected, "rendered_lines": rendered,
                "slice_code": slc.code, "executed_queries": slc.cpgql_queries,
                "trace": traced.events}
    except SliceFailure as exc:
        return {"status": _failure_status(str(exc)), "error": str(exc),
                "trace": traced.events}
    except JoernError as exc:
        status = "joern_import" if str(exc).startswith("Failed to import code") else "joern_transport"
        return {"status": status, "error": str(exc), "trace": traced.events}
    finally:
        try:
            joern.reset()
        except Exception as exc:
            # A contaminated worker must be restarted. Do not treat this as a
            # successful clean run; surface it to the operator explicitly.
            raise RuntimeError(f"Joern reset failed for {project_name}: {exc}") from exc


def extract_slices(cases: list[Case], work: Path, cfg: dict[str, Any],
                   repeats: int = 3, joern=None) -> None:
    specs = run_specs(cases, repeats)
    by_case = _sources(cases)
    q = index_jsonl(work / "queries.jsonl", "run_id")
    dest = work / "slices.jsonl"
    done = index_jsonl(dest, "run_id")
    owned = joern is None
    if owned:
        from llmxcpg.joern.client import JoernClient
        # Match docker/docker-compose.yml's read-only mount.
        joern = JoernClient(host=cfg.get("joern_host", "localhost"),
                            port=cfg.get("joern_port", 8080),
                            local_input_dir=Path(cfg.get("joern_input_dir", "work/joern-inputs")),
                            server_input_dir=cfg.get("server_input_dir", "/analysis/inputs"))
    try:
        for spec in specs:
            if spec["run_id"] in done:
                continue
            arm, case = spec["arm"], by_case[spec["case_id"]]
            if arm.endswith("_fixed"):
                baseline = next(s for s in specs if s["case_id"] == spec["case_id"]
                                and s["arm"] == "U" and s["repeat"] == 0)
                query_record = q.get(baseline["run_id"])
            elif arm.endswith("_rule"):
                query_record = {"status": "ok", "queries": case.rule_queries}
            else:
                query_record = q.get(spec["run_id"])
            if query_record is None:
                raise ValueError(f"Query phase incomplete for {spec['run_id']}")
            if query_record["status"] != "ok":
                outcome = {"status": query_record["status"], "error": query_record.get("error"),
                           "trace": []}
            else:
                outcome = extract_one(joern, case.source_for(arm), query_record["queries"],
                                      spec["run_id"][:20])
            append_jsonl(dest, {"run_id": spec["run_id"],
                                "query_origin": ("baseline" if arm.endswith("_fixed") else
                                                 "rule" if arm.endswith("_rule") else "regenerated"),
                                "queries": query_record["queries"], **outcome})
    finally:
        if owned and hasattr(joern, "close"):
            joern.close()


def classify_slices(cases: list[Case], work: Path, cfg: dict[str, Any],
                    repeats: int = 3, classifier=None) -> None:
    from llmxcpg.prompts import render_detection_prompt

    slices = index_jsonl(work / "slices.jsonl", "run_id")
    specs = run_specs(cases, repeats)
    dest = work / "detector.jsonl"
    done = index_jsonl(dest, "run_id")
    owned = classifier is None
    if owned:
        from llmxcpg.inference.classifier import VulnerabilityClassifier
        d = VulnerabilityClassifier.from_config(_models(cfg))
    else:
        d = classifier
    try:
        for spec in specs:
            rid = spec["run_id"]
            if rid in done:
                continue
            slc = slices.get(rid)
            if slc is None:
                raise ValueError(f"Slice phase incomplete for {rid}")
            if slc["status"] != "ok":
                append_jsonl(dest, {"run_id": rid, "status": "abstain",
                                    "reason": slc["status"]})
                continue
            prompt = render_detection_prompt(slc["slice_code"])
            if hasattr(d, "tokenizer"):
                n = len(d.tokenizer.encode(prompt, add_special_tokens=False))
                if n > d.max_context:
                    append_jsonl(dest, {"run_id": rid, "status": "context_overflow",
                                        "prompt_tokens": n})
                    continue
            out = d.classify(slc["slice_code"], threshold=cfg["threshold"])
            append_jsonl(dest, {"run_id": rid, "status": "ok",
                                "verdict": out.is_vulnerable,
                                "p_vulnerable": out.probability_vulnerable,
                                "p_safe": out.probability_safe,
                                "raw_logits": list(out.raw_logits),
                                "threshold": cfg["threshold"]})
    finally:
        if owned:
            del d


def numbered_view(source: str, rendered_lines: list[int]) -> str:
    lines = source.splitlines()
    numbered: list[str] = []
    last = 0
    for n in rendered_lines:
        if last and n - last > 1:
            numbered.append("...")
        numbered.append(f"L{n}: {lines[n - 1]}")
        last = n
    return "\n".join(numbered)


def packet_index(cases: list[Case], work: Path, repeats: int = 3
                 ) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Return blind packet content and the private run-to-review join key."""
    slices = index_jsonl(work / "slices.jsonl", "run_id")
    by_case = _sources(cases)
    packets: dict[str, dict[str, str]] = {}
    joins: dict[str, str] = {}
    for spec in run_specs(cases, repeats):
        slc = slices.get(spec["run_id"])
        if slc is None or slc["status"] != "ok":
            continue
        view = numbered_view(by_case[spec["case_id"]].source_for(spec["arm"]),
                             slc["rendered_lines"])
        review_id = digest(view)
        packets[review_id] = {"review_id": review_id, "code": view}
        joins[spec["run_id"]] = review_id
    return packets, joins


def review_packets(cases: list[Case], work: Path, repeats: int = 3) -> list[dict[str, str]]:
    """Blind packets: no case, CWE, arm, model verdict or treatment metadata."""
    packets, _ = packet_index(cases, work, repeats)
    return sorted(packets.values(), key=lambda p: p["review_id"])
