"""Regressions from the real laptop fixture, without claiming a live Joern run."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_experiment.runner import extract_one
from llmxcpg.joern.client import JoernClient, has_repl_failure
from llmxcpg.joern.queries import build_backward_slice_query

FIXTURE = Path(__file__).resolve().parents[1] / 'docs/audits/2026-10-30-joern-fix/observed-fixture-failure.json'


def client_with(raw):
    client = object.__new__(JoernClient)
    client._client = SimpleNamespace(execute=lambda query: raw)
    return client


def test_real_stdout_compiler_error_overrides_success_envelope():
    observed = json.loads(FIXTURE.read_text())
    last = observed['outcome']['trace'][-1]
    assert last['success'] is True  # the old client incorrectly reported this
    result = client_with({'stdout': last['stdout'], 'stderr': '', 'success': True}).run(last['query'])
    assert result.success is False and result.value is None
    assert result.stdout == last['stdout']  # retain ANSI/raw evidence


def test_replay_failure_is_slice_execution_not_source_mapping():
    observed = json.loads(FIXTURE.read_text())
    trace = iter(e for e in observed['outcome']['trace'] if 'query' in e)
    client = object.__new__(JoernClient)
    def execute(query):
        e = next(trace)
        return {'stdout': e['stdout'], 'stderr': '', 'success': True}
    client._client = SimpleNamespace(execute=execute)
    client.import_code = lambda *a, **kw: None
    client.reset = lambda: None
    result = extract_one(client, observed['source'], observed['queries'], 'replay_only')
    assert result['status'] == 'slice_exec'
    assert result['trace'][-1]['success'] is False
    assert 'reachableByFlows' in result['error']


@pytest.mark.parametrize('stdout', [
    '-- [E008] Not Found Error: ----\nvalue foo is not a member of Bar\n1 error found',
    '\x1b[31m-- [E040] Syntax Error: ----\x1b[0m\n1 error found',
    '-- Error: ----\nUnclosed string',
    'cmd1.sc:2: error: not found: value missing',
    'script.scala:2:3: error: bad expression',
    'java.lang.IllegalArgumentException: failure\n  at something',
    'scala.MatchError: x',
])
def test_structured_repl_diagnostics_fail(stdout):
    assert has_repl_failure(stdout)
    assert not client_with({'stdout': stdout, 'stderr': '', 'success': True}).run('test').success


@pytest.mark.parametrize('stdout', [
    'val x: String = "ERROR: Array index is negative."',
    'val x: String = "Compilation failed"',
    'val x: String = "java.lang.IllegalArgumentException: example text"',
    'WARNING: Unable to create a system terminal',
    'val slice_lines: List[Int] = List(1, 3, 4)\nRQ1_SLICE_LINES=1,3,4\n',
    '\x1b[33mval\x1b[0m x: Int = 1',
])
def test_normal_values_and_warnings_do_not_look_like_compiler_failure(stdout):
    assert not has_repl_failure(stdout)
    result = client_with({'stdout': stdout, 'stderr': '', 'success': True}).run('test')
    assert result.success and result.stdout == stdout


def test_failed_envelope_and_stderr_remain_failures():
    for raw in ({'stdout': 'List(1)', 'stderr': '', 'success': False},
                {'stdout': 'List(1)', 'stderr': 'failure', 'success': True}):
        assert not client_with(raw).run('test').success


def test_colored_simple_value_is_parsed_without_altering_raw_stdout():
    raw = '\x1b[33mval\x1b[0m\x1b[36m1\x1b[0m: Int = 42'
    result = client_with({'stdout': raw, 'stderr': '', 'success': True}).run('test')
    assert result.value == 42 and result.stdout == raw


def test_backward_helper_narrows_sinks_and_keeps_unrestricted_source():
    query = build_backward_slice_query()
    assert '.collect { case node: io.shiftleft.codepropertygraph.generated.nodes.CfgNode => node }' in query
    assert 'all_path_nodes.reachableByFlows(cpg.all).l' in query
    assert query.index('.collect') < query.index('.reachableByFlows')
    assert 'RQ1_SLICE_LINES=' in query
