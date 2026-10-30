"""Renderer and selector failure regressions, using simulated Joern only."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from evidence_experiment.runner import (
    WorkerResetError,
    extract_one,
    extract_slices,
    generate_queries,
)
from evidence_experiment.schema import append_jsonl, read_jsonl, run_specs
from llmxcpg.inference.query_generator import QueryGenerator
from llmxcpg.joern.client import JoernError, QueryResult
from llmxcpg.prompts import render_query_prompt
from llmxcpg.slicing.extractor import SliceExtractor
from llmxcpg.slicing.reconstruction import context_lines, reconstruct_code_from_lines

SOURCE = 'void f(int n) {\n char a[4];\n if (n < 4) {\n  a[n]=1;\n }\n}\n'
QUERIES = ['val execution_path = sink.reachableByFlows(source).l']


class FakeJoern:
    def __init__(self, lines=None, fail=None):
        self.lines = [4] if lines is None else lines
        self.fail = fail

    def import_code(self, *args, **kwargs):
        if self.fail == 'import':
            raise JoernError('Failed to import code: test')

    def run(self, query):
        if self.fail == 'transport':
            raise JoernError('RPC timeout: test')
        if self.fail and self.fail in query:
            return QueryResult(stdout='Compilation failed', value=None, success=False)
        return QueryResult(stdout=f'List({",".join(map(str, self.lines))})', value=self.lines, success=True)

    def reset(self):
        if self.fail == 'reset':
            raise JoernError('reset failed')


def test_upstream_prompt_serialization_hash():
    from evidence_experiment.schema import digest
    assert digest(render_query_prompt('int x;')) == '3e7ab3194262d19809fb5e43cbbbef52a8cc916c6f6ca330cb3199a1f335dbdb'


@pytest.mark.parametrize('raw', ['', '{}', '{"queries":[]}', '{"queries":[1]}', '{"queries":["cpg.call.l"]}'])
def test_malformed_q_output_is_not_success(raw):
    assert not QueryGenerator._parse(raw).parsed_ok


def test_q_parser_retains_raw_text():
    raw = '```json\n{"queries": ["val execution_path = sink.reachableByFlows(source).l"]}\n```'
    out = QueryGenerator._parse(raw)
    assert out.parsed_ok and out.raw_text == raw and out.queries == QUERIES


def test_enclosing_guard_and_function_are_visible():
    assert context_lines(SOURCE, [4]) == [1, 3, 4, 5, 6]
    assert 'if (n < 4)' in reconstruct_code_from_lines(SOURCE, [4])
    assert 'char a[4]' not in reconstruct_code_from_lines(SOURCE, [4])


def test_next_line_braces_multiline_header_and_quoted_braces():
    source = 'void f(void)\n{\n char *s="}"; /* { */\n if (s &&\n     *s)\n {\n  puts(s);\n }\n}\n'
    assert context_lines(source, [7]) == [1, 2, 4, 5, 6, 7, 8, 9]


def test_braceless_header_is_retained():
    assert context_lines('void f(int n) {\n if(n)\n  n++;\n}\n', [3]) == [1, 2, 3, 4]


@pytest.mark.parametrize('coords', [[], [0], [-1], [999], [4, 999], [True], ['4']])
def test_invalid_or_mixed_coordinates_rejected(coords):
    with pytest.raises(ValueError, match='coordinates'):
        context_lines(SOURCE, coords)


@pytest.mark.parametrize('value', [[4, '999'], [True], [4, -1], [999]])
def test_malformed_or_out_of_range_joern_mapping_is_failure(value):
    assert extract_one(FakeJoern(value), SOURCE, QUERIES, 'test')['status'] == 'mapping_error'


def test_trace_proves_whole_fixed_selector_was_called():
    row = extract_one(FakeJoern(), SOURCE, QUERIES, 'test')
    assert row['status'] == 'ok'
    assert {'graph_import', 'query_execution', 'context_expansion', 'slice_construction'} <= {e['stage'] for e in row['trace']}


@pytest.mark.parametrize('fail,status', [('import', 'joern_import'), ('transport', 'timeout'), ('interacters', 'context_exec'), ('slice_lines', 'slice_exec'), ('reachableByFlows', 'query_exec')])
def test_failures_remain_at_their_observed_stage(fail, status):
    assert extract_one(FakeJoern(fail=fail), SOURCE, QUERIES, 'test')['status'] == status


def test_reset_failure_preserves_prior_outcome():
    with pytest.raises(WorkerResetError) as caught:
        extract_one(FakeJoern(fail='reset'), SOURCE, QUERIES, 'test')
    assert caught.value.outcome['prior_outcome']['status'] == 'ok'


def test_empty_slice_and_unsafe_scala():
    assert extract_one(FakeJoern([]), SOURCE, QUERIES, 'test')['status'] == 'empty_slice'
    assert extract_one(FakeJoern(), SOURCE, ['java.lang.Runtime.getRuntime(); sink.reachableByFlows(source).l'], 'test')['status'] == 'query_invalid'
    with pytest.raises(ValueError, match='Malformed'):
        SliceExtractor._parse_line_list(None, 'List(4, broken)')


def test_synthetic_generation_cannot_masquerade_as_real(witnessed, cases, cfg):
    calls = []
    class Generator:
        def generate_batch(self, sources):
            calls.extend(sources)
            return [SimpleNamespace(parsed_ok=True, queries=QUERIES, raw_text='test', error=None, finish_reason='stop', output_tokens=2)]
    generate_queries(cases, witnessed, cfg, generator=Generator())
    assert len(calls) == 6
    generate_queries(cases, witnessed, cfg, generator=Generator())
    assert len(calls) == 6  # resumed terminal queries are never regenerated
    assert all(r['synthetic'] for r in read_jsonl(witnessed / 'queries.jsonl'))


def test_infrastructure_attempts_are_capped_and_resume_preserves_queries(tmp_path, cases, cfg):
    specs = run_specs(cases)
    for s in specs:
        append_jsonl(tmp_path / 'queries.jsonl', {'run_id': s['run_id'], 'status': 'ok', 'queries': QUERIES})
    starts = []
    @contextmanager
    def failing_worker(config, path):
        starts.append(path)
        yield FakeJoern(fail='transport')
    for _ in range(3):
        with pytest.raises(RuntimeError):
            extract_slices(cases, tmp_path, cfg, worker_factory=failing_worker)
    attempts = read_jsonl(tmp_path / 'slice_attempts.jsonl')
    assert len(attempts) == 3 and [r['attempt'] for r in attempts] == [1, 2, 3]
    assert len(read_jsonl(tmp_path / 'slices.jsonl')) == 1
    assert len(starts) == 3


def test_semantic_failure_is_not_retried(tmp_path, cases, cfg):
    for s in run_specs(cases):
        append_jsonl(tmp_path / 'queries.jsonl', {'run_id': s['run_id'], 'status': 'ok', 'queries': QUERIES})
    @contextmanager
    def worker(config, path):
        yield FakeJoern(fail='reachableByFlows')
    extract_slices(cases, tmp_path, cfg, worker_factory=worker)
    extract_slices(cases, tmp_path, cfg, worker_factory=worker)
    assert len(read_jsonl(tmp_path / 'slice_attempts.jsonl')) == 6
    assert len(read_jsonl(tmp_path / 'slices.jsonl')) == 6


def test_selector_marker_overrides_incidental_joern_list_bindings():
    stdout = 'val nodes: List[Node] = List(Identifier(x))\nRQ1_SLICE_LINES=3,4\nval result: List[Int] = List(3,4)'
    assert SliceExtractor._parse_line_list(stdout, stdout) == [3, 4]
    with pytest.raises(ValueError, match='Malformed'):
        SliceExtractor._parse_line_list(None, 'RQ1_SLICE_LINES=4,oops\nList(4)')


def test_else_branch_keeps_preceding_condition_without_its_body():
    source = 'void f(int n) {\n if (n) {\n  n++;\n } else {\n  n--;\n }\n}\n'
    rendered = context_lines(source, [5])
    assert {1, 2, 4, 5, 6, 7} == set(rendered)
    assert 3 not in rendered


def test_every_enrolled_line_has_valid_reconstruction():
    from evidence_experiment.review import numbered_view
    from evidence_experiment.schema import load_cases
    from rq1.setup import CORPUS
    for split in ('development', 'main'):
        for case in load_cases(CORPUS / f'{split}.jsonl'):
            for source in case.sources.values():
                for n in range(1, len(source.splitlines()) + 1):
                    rendered = context_lines(source, [n])
                    assert n in rendered
                    assert numbered_view(source, rendered)


def test_bare_final_path_is_bound_once_and_previous_binding_does_not_override_it():
    joern = FakeJoern()
    result = SliceExtractor(joern).extract(SOURCE, [
        'val execution_path = source', 'sink.reachableByFlows(source).l'])
    assert result.cpgql_queries[1] == 'val execution_path = sink.reachableByFlows(source).l'
    assert SliceExtractor._normalise_execution_path([
        'val execution_path = source', 'val final_path = sink.reachableByFlows(source).l']) == 'val execution_path = final_path'
    assert sum(q.count('sink.reachableByFlows(source)') for q in result.cpgql_queries) == 1
