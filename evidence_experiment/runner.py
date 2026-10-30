"""Resumable primary Q generation and isolated Joern extraction for U/F only."""
from __future__ import annotations

import time
import uuid

from .schema import append_jsonl, index_jsonl, run_specs

QUERY_STATUSES = {"ok", "query_parse", "context_overflow"}
INFRA_STATUSES = {"timeout", "joern_transport", "worker_reset_failed", "unknown_slice_failure"}
SLICE_STATUSES = QUERY_STATUSES | INFRA_STATUSES | {
    "query_invalid", "query_exec", "path_binding", "context_exec", "slice_exec",
    "empty_slice", "joern_import", "mapping_error"}


def load_config(path, **unused):
    from rq1.setup import load_config as load
    return load(path)


def _models(cfg):
    from llmxcpg.config import ModelConfig
    return ModelConfig(cfg["query_model"], cfg["query_revision"], cfg["query_max_context"],
                       cfg["query_temperature"], cfg["query_gpu_memory_utilization"],
                       cfg["query_tensor_parallel_size"])


def generate_queries(cases, work, cfg, repeats=1, *, generator=None):
    from llmxcpg.inference.query_generator import QueryGenerator
    from llmxcpg.prompts import render_query_prompt

    from .locks import environment, now
    specs = run_specs(cases, repeats)
    by_case = {c.case_id: c for c in cases}
    destination = work / "queries.jsonl"
    done = index_jsonl(destination, "run_id")
    if set(done) - {s["run_id"] for s in specs}:
        raise ValueError("Foreign query IDs in this run directory")
    pending = [s for s in specs if s["run_id"] not in done]
    if not pending:
        return
    owned = generator is None
    started = time.monotonic()
    try:
        q = QueryGenerator.from_config(_models(cfg)) if owned else generator
    except Exception as exc:
        append_jsonl(work / "query_load_errors.jsonl", {"utc": now(), "error": repr(exc)})
        raise
    engine = getattr(q, "_llm", None)
    model = getattr(getattr(engine, "llm_engine", None), "model_config", None)
    session_id = uuid.uuid4().hex
    append_jsonl(work / "query_sessions.jsonl", {
        "session_id": session_id, "utc": now(), "query_model": cfg["query_model"],
        "query_revision": cfg["query_revision"], "synthetic": not owned,
        "model_load_seconds": max(time.monotonic() - started, 1e-9),
        "effective_dtype": str(getattr(model, "dtype", "synthetic" if not owned else "unknown")),
        "effective_seed": getattr(model, "seed", None),
        "effective_max_context": getattr(model, "max_model_len", None),
        "generation_allowance": 2048, "temperature": 0.0, "top_p": 1.0,
        "runtime": environment(),
    })
    try:
        for spec in pending:
            source = by_case[spec["case_id"]].source_for(spec["arm"])
            count = None
            if owned:
                prompt = q._format_vllm_prompt(render_query_prompt(source))
                count = len(engine.get_tokenizer().encode(prompt))
            common = {"run_id": spec["run_id"], "session_id": session_id,
                      "query_engine": "vllm", "synthetic": not owned,
                      "prompt_tokens": count, "generation_allowance": 2048}
            if count is not None and count + 2048 > cfg["query_max_context"]:
                append_jsonl(destination, {**common, "status": "context_overflow", "queries": [],
                                          "raw_text": "", "error": "Complete prompt exceeds context"})
                continue
            began = time.monotonic()
            outputs = q.generate_batch([source])
            if len(outputs) != 1:
                raise RuntimeError("Q must return exactly one result for the primary input")
            out = outputs[0]
            append_jsonl(destination, {**common, "status": "ok" if out.parsed_ok else "query_parse",
                "queries": out.queries, "raw_text": out.raw_text, "error": out.error,
                "finish_reason": out.finish_reason, "output_tokens": out.output_tokens,
                "generation_seconds": time.monotonic() - began})
    except Exception as exc:
        append_jsonl(work / "query_runtime_errors.jsonl", {"utc": now(), "error": repr(exc)})
        raise
    finally:
        if owned:
            q.close()


class WorkerResetError(RuntimeError):
    def __init__(self, outcome):
        super().__init__("Joern cleanup failed; the next attempt needs a fresh worker")
        self.outcome = outcome


class TracedJoern:
    def __init__(self, inner):
        self.inner, self.events = inner, []

    def import_code(self, source, project_name="snippet"):
        try:
            self.inner.import_code(source, project_name=project_name)
        except Exception as exc:
            self.events.append({"stage": "graph_import", "success": False, "error": repr(exc)})
            raise
        self.events.append({"stage": "graph_import", "success": True})

    def run(self, query):
        stage = "slice_construction" if "slice_lines" in query else (
            "context_expansion" if "interacters" in query else "query_execution")
        try:
            result = self.inner.run(query)
        except Exception as exc:
            self.events.append({"stage": stage, "query": query,
                                "success": False, "error": repr(exc)})
            raise
        self.events.append({"stage": stage, "query": query, "success": result.success,
                            "stdout": result.stdout, "value": str(result.value)})
        return result


def _failure_status(message):
    for prefix, status in (("Q-generated CPGQL failed", "query_exec"),
            ("Could not bind", "path_binding"), ("Interacters query failed", "context_exec"),
            ("Backward slice query failed", "slice_exec"),
            ("Backward slice produced no lines", "empty_slice"),
            ("No CPGQL", "query_invalid"), ("The final generated", "query_invalid"),
            ("Generated CPGQL", "query_invalid")):
        if message.startswith(prefix):
            return status
    return "unknown_slice_failure"


def extract_one(joern, source, queries, project_name):
    from llmxcpg.joern.client import JoernError
    from llmxcpg.slicing.extractor import SliceExtractor, SliceFailure
    from llmxcpg.slicing.reconstruction import context_lines, reconstruct_code_from_lines
    traced, outcome = TracedJoern(joern), {}
    try:
        slc = SliceExtractor(traced).extract(source, queries, project_name=project_name)
        selected = sorted(set(slc.line_numbers))
        rendered = context_lines(source, selected)
        if not slc.code.strip() or slc.code != reconstruct_code_from_lines(source, selected):
            raise ValueError("Reconstructed excerpt is empty or inconsistent")
        outcome = {"status": "ok", "slice_lines": selected, "rendered_lines": rendered,
                   "slice_code": slc.code, "executed_queries": slc.cpgql_queries}
    except SliceFailure as exc:
        outcome = {"status": _failure_status(str(exc)), "error": str(exc)}
    except JoernError as exc:
        status = "timeout" if str(exc).startswith("RPC timeout") else (
            "joern_import" if str(exc).startswith("Failed to import code") else "joern_transport")
        outcome = {"status": status, "error": str(exc)}
    except ValueError as exc:
        outcome = {"status": "mapping_error", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - preserve unexpected failures as explicit diagnostic records
        outcome = {"status": "unknown_slice_failure", "error": repr(exc)}
    finally:
        try:
            joern.reset()
        except Exception as exc:
            raise WorkerResetError({"status": "worker_reset_failed", "error": repr(exc),
                                    "prior_outcome": outcome, "trace": traced.events}) from exc
    return {**outcome, "trace": traced.events}


def extract_slices(cases, work, cfg, repeats=1, *, worker_factory=None):
    from rq1.joern_worker import fresh_worker

    from .schema import read_jsonl
    specs = run_specs(cases, repeats)
    by_case = {c.case_id: c for c in cases}
    queries = index_jsonl(work / "queries.jsonl", "run_id")
    done = index_jsonl(work / "slices.jsonl", "run_id")
    expected = {s["run_id"] for s in specs}
    if set(queries) != expected or set(done) - expected:
        raise ValueError("Query inputs are incomplete or stage IDs are foreign")
    attempts_path = work / "slice_attempts.jsonl"
    all_attempts = read_jsonl(attempts_path)
    for spec in specs:
        rid = spec["run_id"]
        if rid in done:
            continue
        query = queries[rid]
        if query["status"] != "ok":
            outcome = {"status": query["status"], "error": query.get("error"), "trace": []}
        else:
            attempts = [r for r in all_attempts if r["run_id"] == rid]
            if attempts and (len(attempts) >= cfg["infrastructure_attempts"] or
                             attempts[-1]["outcome"]["status"] not in INFRA_STATUSES):
                outcome = attempts[-1]["outcome"]
            else:
                number = len(attempts) + 1
                try:
                    factory = worker_factory or fresh_worker
                    with factory(cfg, work / "workers" / f"{rid}-{number}") as joern:
                        outcome = extract_one(joern, by_case[spec["case_id"]].source_for(spec["arm"]),
                                              query["queries"], rid[:20])
                except WorkerResetError as exc:
                    outcome = exc.outcome
                except Exception as exc:  # noqa: BLE001 - preserve unexpected failures as explicit diagnostic records
                    outcome = {"status": "joern_transport", "error": repr(exc), "trace": []}
                attempt = {"run_id": rid, "attempt": number, "outcome": outcome}
                append_jsonl(attempts_path, attempt)
                all_attempts.append(attempt)
                if outcome["status"] in INFRA_STATUSES and number < cfg["infrastructure_attempts"]:
                    raise RuntimeError("Infrastructure attempt saved; inspect logs and resume unchanged")
        append_jsonl(work / "slices.jsonl", {"run_id": rid, "queries": query["queries"], **outcome})
        if outcome["status"] in INFRA_STATUSES | {"mapping_error"}:
            raise RuntimeError("Terminal or mapping failure saved; inspect before resuming")
