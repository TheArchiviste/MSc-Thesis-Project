"""Safe recovery of the actual v4 Docker-side results; no mocked live experiment."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evidence_experiment.schema import load_cases
from rq1.conformance import GRAPH_QUERY, parse_graph
from rq1.recover_cpu import recover_graph, verify_legacy
from rq1.setup import CORPUS

AUDIT = Path(__file__).resolve().parents[1] / 'docs/audits/2026-10-30-v4-recovery'


@pytest.fixture
def prior():
    return json.loads((AUDIT / 'source-readiness.json').read_text())


@pytest.fixture
def real_graph(prior):
    row = next(r for r in prior['corpus_graphs'] if (r['case_id'], r['arm']) == ('D01', 'U'))
    source = next(c for c in load_cases(CORPUS / 'development.jsonl') if c.case_id == 'D01').source_for('U')
    return row, (AUDIT / 'sample-project-log.txt').read_text(), source


def test_original_v4_receipt_cannot_be_relabelled_after_assessor_protocol_change(prior):
    with pytest.raises(ValueError, match='Scientific code/source changed'):
        verify_legacy(prior)


def test_real_marker_is_recovered_from_its_exact_project(real_graph):
    row, log, source = real_graph
    result = recover_graph(row, log, source)
    assert result['graph_stdout'] == 'RQ1_GRAPH=1,1,1,1|15'
    assert result['output_channel'] == 'docker_log_recovered'
    assert result['original_rpc_stdout'] == ''
    assert result['caller_lines'] == [15]


@pytest.mark.parametrize('mutation', ['wrong_case', 'wrong_arm', 'duplicate_marker', 'missing_marker', 'wrong_line', 'prior_project_only'])
def test_ambiguous_wrong_or_borrowed_markers_cannot_recover(real_graph, mutation):
    row, log, source = real_graph
    if mutation == 'wrong_case':
        log = log.replace('rq1_graph_D01_U_', 'rq1_graph_D02_U_')
    elif mutation == 'wrong_arm':
        log = log.replace('rq1_graph_D01_U_', 'rq1_graph_D01_F_')
    elif mutation == 'duplicate_marker':
        log += '\n2026-10-30T14:00:00Z RQ1_GRAPH=1,1,1,1|15\n'
    elif mutation == 'missing_marker':
        log = log.replace('RQ1_GRAPH=', 'OTHER=')
    elif mutation == 'wrong_line':
        log = log.replace('RQ1_GRAPH=1,1,1,1|15', 'RQ1_GRAPH=1,1,1,1|999')
    else:
        log += '\nCreating project `rq1_graph_D01_U_123456789abc` for code at `/analysis/inputs/new/rq1_graph_D01_U.c`\n'
    with pytest.raises(ValueError):
        recover_graph(row, log, source)


@pytest.mark.parametrize('mutation', ['contract', 'fixture', 'missing_graph', 'reset', 'different_failure'])
def test_recovery_never_accepts_just_a_ready_flag_or_other_failures(prior, mutation):
    prior = copy.deepcopy(prior)
    if mutation == 'contract':
        prior['corpus_contract']['llmxcpg/joern/queries.py'] = 'changed'
    elif mutation == 'fixture':
        prior['outcome']['status'] = 'slice_exec'
    elif mutation == 'missing_graph':
        prior['corpus_graphs'].pop()
    elif mutation == 'reset':
        prior['corpus_graphs'][0]['reset_ok'] = False
    else:
        prior['corpus_graphs'][0]['error'] = 'different'
    with pytest.raises(ValueError):
        verify_legacy(prior)


def test_scientific_core_drift_blocks_recovery(prior, tmp_path, monkeypatch):
    from rq1 import setup
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    with pytest.raises(FileNotFoundError):
        verify_legacy(prior)


def test_new_graph_query_returns_a_value_without_relying_on_println():
    assert GRAPH_QUERY.startswith('val rq1_graph = ')
    assert 'println' not in GRAPH_QUERY
    source = 'void case_entry(){\ncase_sink(data);\n}'
    captured = '\x1b[33mval\x1b[0m \x1b[36mrq1_graph\x1b[0m: \x1b[32mString\x1b[0m = "RQ1_GRAPH=1,1,1,1|2"\n'
    assert parse_graph(captured, source)['caller_lines'] == [2]
    with pytest.raises(ValueError, match='Ambiguous'):
        parse_graph(captured + captured, source)


def prepare_recovery_fixture(tmp_path, prior, cfg):
    """Synthetic file-tree/probe fixture, confined to pytest temporary storage."""
    from evidence_experiment.schema import write_json
    previous = tmp_path / 'v4'
    proof = previous / 'joern-capability'
    write_json(proof / 'readiness.json', prior)
    cases = {c.case_id: c for split in ('development', 'main') for c in load_cases(CORPUS / f'{split}.jsonl')}
    for row in prior['corpus_graphs']:
        cid, arm = row['case_id'], row['arm']
        line = next(i for i, text in enumerate(cases[cid].source_for(arm).splitlines(), 1) if 'case_sink(data);' in text)
        log = (f'Creating project `rq1_graph_{cid}_{arm}_123456789abc` for code at `/analysis/test/rq1_graph_{cid}_{arm}.c`\n'
               f'2026-10-30T13:00:00Z RQ1_GRAPH=1,1,1,1|{line}\n')
        path = proof / f'{cid}-{arm}/server.log'; path.parent.mkdir(parents=True)
        path.write_text(log)
    # Real older source witnesses have unchanged source/plan hashes; retain them as test inputs.
    import shutil
    for split in ('development', 'main'):
        (previous / split).mkdir()
        shutil.copyfile(AUDIT.parent / '2026-10-30-v3' / f'{split}-witnesses.jsonl', previous / split / 'witness_validation.jsonl')
    root = tmp_path / 'v5'
    cfg.update(joern_capability_file=str(root / 'joern-capability/readiness.json'),
               rq1_calibration_file=str(root / 'calibration/acceptance.json'))
    config = tmp_path / 'config.json'; write_json(config, cfg)
    return previous, config, root


def test_v6_blocks_legacy_recovery_before_a_live_probe_or_new_receipt(tmp_path, prior, cfg, monkeypatch):
    from contextlib import contextmanager

    from llmxcpg.joern.client import QueryResult
    from rq1 import recover_cpu, setup
    previous, config, root = prepare_recovery_fixture(tmp_path, prior, cfg)
    monkeypatch.setattr(recover_cpu, 'environment', lambda: prior['environment'])
    monkeypatch.setattr(setup, 'token_audit', lambda config: None)
    monkeypatch.setattr(setup, 'doctor', lambda *a: True)
    calls = []
    class Probe:
        def import_code(self, source, project_name):
            calls.append(('import', project_name))
        def run(self, query):
            calls.append(('query', query))
            stdout = 'val rq1_graph: String = "RQ1_GRAPH=1,1,1,1|15"' if query == GRAPH_QUERY else 'val rq1_calls: String = "RQ1_CALLS=case_sink"'
            return QueryResult(stdout=stdout, value=stdout, success=True)
        def reset(self):
            calls.append(('reset',))
    @contextmanager
    def factory(cfg, work):
        yield Probe()
    with pytest.raises(ValueError, match='Scientific code/source changed'):
        recover_cpu.recover(previous, config, worker_factory=factory)
    assert not calls
    assert not (root / 'joern-capability/readiness.json').exists()
    assert not (root / 'calibration/acceptance.json').exists()


def test_failed_current_probe_cannot_accept_recovery(tmp_path, prior, cfg, monkeypatch):
    from contextlib import contextmanager

    from llmxcpg.joern.client import QueryResult
    from rq1 import recover_cpu, setup
    previous, config, root = prepare_recovery_fixture(tmp_path, prior, cfg)
    monkeypatch.setattr(recover_cpu, 'environment', lambda: prior['environment'])
    class Probe:
        def import_code(self, *a, **kw):
            pass
        def run(self, query):
            return QueryResult(stdout='', value=None, success=True)
        def reset(self):
            pass
    @contextmanager
    def factory(cfg, work):
        yield Probe()
    with pytest.raises(ValueError, match='Scientific code/source changed'):
        recover_cpu.recover(previous, config, worker_factory=factory)
    assert not (root / 'joern-capability/readiness.json').exists()
    with pytest.raises(FileNotFoundError):
        setup.capability_valid(cfg)
    assert not (root / 'calibration/acceptance.json').exists()
