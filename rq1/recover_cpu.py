"""Verify v4 Docker-side graph output and avoid repeating an already completed scan."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from evidence_experiment.locks import environment, now, policy, require_witnesses, work_lock
from evidence_experiment.schema import digest, file_digest, load_cases, write_json

from .conformance import (
    CALLS_QUERY,
    GRAPH_QUERY,
    INTERPROCEDURAL_QUERIES,
    INTERPROCEDURAL_SOURCE,
    QUERIES,
    SOURCE,
    expected_graphs,
    fixture_valid,
    parse_graph,
    validate_receipt,
)

# Exact full source/docs contract used by the returned real v4 CPU run, commit 2ddfc81.
V4_CONTRACT_SHA256 = 'd2d6e26c98e11055ac4339750d0703b9bccb651e37f82593a39ae85d3010d2a0'
LEGACY_GRAPH_QUERY = ('println("RQ1_GRAPH=" + List(cpg.method.nameExact("case_entry").size, '
                      'cpg.method.nameExact("case_sink").size, cpg.call.nameExact("case_sink").size, '
                      'cpg.method.nameExact("case_sink").parameter.index(1).size).mkString(",") + "|" + '
                      'cpg.call.nameExact("case_sink").lineNumber.l.toSet.toList.sorted.mkString(","))')


def verify_legacy(prior):
    from .setup import ROOT
    old = prior.get('corpus_contract', {})
    if digest(json.dumps(old, sort_keys=True)) != V4_CONTRACT_SHA256:
        raise ValueError('Only the exact audited v4 source contract may be recovered')
    if (prior.get('synthetic') is not False or prior.get('ready') is not False or
            prior.get('policy', {}).get('implementation_id') != 'rq1-v4' or
            prior.get('source') != SOURCE or prior.get('queries') != QUERIES or
            prior.get('interprocedural_source') != INTERPROCEDURAL_SOURCE or
            prior.get('interprocedural_queries') != INTERPROCEDURAL_QUERIES or
            not fixture_valid(prior.get('outcome', {})) or
            not fixture_valid(prior.get('interprocedural_outcome', {}), interprocedural=True)):
        raise ValueError('Both original real full-selector fixtures must have passed')
    # Operational readiness code may change; evaluated Q/selector/renderer,
    # acquisition/analysis logic, source corpus and rubric must remain identical.
    for name, expected in old.items():
        protected = (name.startswith(('llmxcpg/', 'evidence_experiment/', 'rq1/generated/', 'rq1/upstream/', 'rq1/support/')) or
                     name in {'pyproject.toml', 'rq1/assessment_protocol.py', 'rq1/references.py', 'rq1/prepare.py',
                              'rq1/main.jsonl', 'rq1/development.jsonl', 'rq1/referents.jsonl',
                              'rq1/selection.json', 'rq1/witness_plan.jsonl'})
        if protected:
            text = (ROOT / name).read_text().replace('rq1-v5', 'rq1-v4').replace('RQ1-v5', 'RQ1-v4')
            if digest(text) != expected:
                raise ValueError(f'Scientific code/source changed; recovery is inadmissible: {name}')
    rows = prior.get('corpus_graphs', [])
    if len(rows) != 30 or {(r['case_id'], r['arm']): r['source_sha256'] for r in rows} != expected_graphs():
        raise ValueError('The original graph scan must cover all 30 exact source inputs')
    if any(r.get('reset_ok') is not True or r.get('status') != 'blocked' or r.get('graph_stdout') != '' or
           r.get('error') != "ValueError('Missing or ambiguous corpus graph marker')" for r in rows):
        raise ValueError('Recovery applies only to the observed missing-RPC-marker failure, not other errors')


def recover_graph(row, log, source):
    cid, arm = row['case_id'], row['arm']
    projects = list(re.finditer(r'Creating project `([^`]+)` for code at `([^`]+)`', log))
    if not projects:
        raise ValueError('Missing source import provenance in Docker log')
    last = projects[-1]
    if (not re.fullmatch(rf'rq1_graph_{re.escape(cid)}_{arm}_[0-9a-f]{{12}}', last.group(1)) or
            not last.group(2).endswith(f'/rq1_graph_{cid}_{arm}.c')):
        raise ValueError('Latest Docker project is not this exact case/arm')
    # Earlier container restarts remain in v4 logs. Never borrow their markers.
    suffix = log[last.end():]
    markers = re.findall(r'(?m)^\S+ (RQ1_GRAPH=[0-9,]+\|[0-9,]*)\s*$', suffix)
    if len(markers) != 1:
        raise ValueError('Require exactly one graph marker after the latest matching import')
    parsed = parse_graph(markers[0], source)
    return {'case_id': cid, 'arm': arm, 'source_sha256': row['source_sha256'],
            'status': 'ok', 'reset_ok': True, 'graph_stdout': markers[0], 'graph_query': LEGACY_GRAPH_QUERY,
            'output_channel': 'docker_log_recovered', 'original_rpc_stdout': row['graph_stdout'],
            'project': last.group(1), 'server_log_sha256': digest(log), **parsed,
            'call_observations_success': False,
            'macro_and_call_observations': 'Not collected: v4 stopped this diagnostic after the RPC-marker check; this observation is not a capability criterion.'}


def recovered_rows(prior, proof_root):
    from .setup import CORPUS
    verify_legacy(prior)
    cases = {c.case_id: c for split in ('development', 'main') for c in load_cases(CORPUS / f'{split}.jsonl')}
    return [recover_graph(r, (proof_root / f"{r['case_id']}-{r['arm']}/server.log").read_text(),
                          cases[r['case_id']].source_for(r['arm'])) for r in prior['corpus_graphs']]


def validate_recovery(result, evidence_root):
    from .setup import CORPUS
    if evidence_root is None:
        raise ValueError('Recovery requires its retained raw source receipt and Docker logs')
    proof_root = evidence_root / 'recovery/v4'
    prior_path = proof_root / 'readiness.json'
    meta = result['recovery']
    if (meta.get('mode') != 'verified_v4_docker_stdout_plus_live_probe' or
            meta.get('source_receipt_sha256') != file_digest(prior_path)):
        raise ValueError('Recovery provenance changed')
    prior = json.loads(prior_path.read_text())
    if result['corpus_graphs'] != recovered_rows(prior, proof_root) or result.get('environment') != prior['environment']:
        raise ValueError('Recovered graphs or tested environment differ from the actual evidence')
    if (result['outcome'] != prior['outcome'] or result['interprocedural_outcome'] != prior['interprocedural_outcome'] or
            result['policy'] != {**prior['policy'], 'implementation_id': 'rq1-v5'}):
        raise ValueError('Recovery cannot substitute fixtures or alter experimental policy')
    probe = result.get('live_diagnostic_probe', {})
    case = next(c for c in load_cases(CORPUS / 'development.jsonl') if c.case_id == 'D01')
    if (probe.get('case_id') != 'D01' or probe.get('arm') != 'U' or probe.get('status') != 'ok' or
            probe.get('reset_ok') is not True or probe.get('source_sha256') != digest(case.source_for('U')) or
            probe.get('query') != GRAPH_QUERY or probe.get('query_success') is not True):
        raise ValueError('A real current diagnostic-return probe is still required')
    parse_graph(probe['stdout'], case.source_for('U'))


def _copy_exact(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if file_digest(source) != file_digest(destination):
            raise ValueError(f'Preserving differing recovery evidence: {destination}')
    else:
        shutil.copyfile(source, destination)


def recover(previous, config, *, worker_factory=None):
    from .joern_worker import fresh_worker
    from .setup import (
        CORPUS,
        ROOT,
        corpus_contract,
        doctor,
        initialize,
        load_config,
        token_audit,
        verify_corpus,
        verify_implementation,
    )
    verify_corpus()
    verify_implementation()
    previous = previous.resolve()
    prior_path = previous / 'joern-capability/readiness.json'
    prior = json.loads(prior_path.read_text())
    verify_legacy(prior)
    # Verify evidence before copying, contacting Docker, or creating a new bank.
    if prior['environment'] != environment():
        raise ValueError('Restore the exact v4 CPU Python/package environment before recovery')
    for split in ('development', 'main'):
        old_work = previous / split
        if any((old_work / name).exists() for name in ('queries.jsonl', 'slices.jsonl', 'experiment_lock.json', 'assessments.initial.jsonl')):
            raise ValueError('Recovery is restricted to preparation before any Q/assessment acquisition')
        require_witnesses(old_work, load_cases(CORPUS / f'{split}.jsonl'))
    if any((previous / 'calibration' / name).exists() for name in ('responses.jsonl', 'assessments.initial.jsonl', 'acceptance.json')):
        raise ValueError('Do not migrate an acquired/calibrated instrument with this preparation-only recovery')
    recovered_rows(prior, prior_path.parent)  # fail before writing if any marker/source fails
    if not config.exists():
        initialize(config)
    cfg = load_config(config)
    if policy(cfg) != {**prior['policy'], 'implementation_id': 'rq1-v5'}:
        raise ValueError('Recovery cannot change experimental policy')
    destination = ROOT / cfg['joern_capability_file']
    root = destination.parent.parent
    if previous == root.resolve() or previous in destination.resolve().parents:
        raise ValueError('Recovery outputs must be outside the preserved v4 source directory')
    if any((root / split / name).exists() for split in ('development', 'main')
           for name in ('queries.jsonl', 'slices.jsonl', 'experiment_lock.json', 'assessments.initial.jsonl')):
        raise ValueError('Do not update readiness after acquisition has begun in the target version')
    if any((root / 'calibration' / name).exists() for name in ('responses.jsonl', 'assessments.initial.jsonl', 'acceptance.json')):
        raise ValueError('Do not replace an acquired target calibration')
    for split in ('development', 'main'):
        _copy_exact(previous / split / 'witness_validation.jsonl', root / split / 'witness_validation.jsonl')
    proof_root = destination.parent / 'recovery/v4'
    _copy_exact(prior_path, proof_root / 'readiness.json')
    for row in prior['corpus_graphs']:
        rel = f"{row['case_id']}-{row['arm']}/server.log"
        _copy_exact(prior_path.parent / rel, proof_root / rel)
    result = {'utc': now(), 'ready': False, 'synthetic': False, 'fixture_only': False,
              'meaning': 'Derived verification of 30 real v4 graph outputs in Docker logs and its two real selector fixtures, plus one fresh v5 diagnostic-return probe. No repeated corpus scan or Q inference.',
              'corpus_contract': corpus_contract(), 'policy': policy(cfg), 'environment': prior['environment'],
              'source': SOURCE, 'queries': QUERIES, 'outcome': prior['outcome'],
              'interprocedural_source': INTERPROCEDURAL_SOURCE, 'interprocedural_queries': INTERPROCEDURAL_QUERIES,
              'interprocedural_outcome': prior['interprocedural_outcome'], 'corpus_graphs': recovered_rows(prior, proof_root),
              'recovery': {'mode': 'verified_v4_docker_stdout_plus_live_probe', 'source_receipt_sha256': file_digest(proof_root / 'readiness.json'),
                           'source_implementation': 'rq1-v4', 'validated_implementation': 'rq1-v5',
                           'limit': 'Historical execution is explicitly retained; no new 30-input scan is claimed.'}}
    case = next(c for c in load_cases(CORPUS / 'development.jsonl') if c.case_id == 'D01')
    probe = {'case_id': 'D01', 'arm': 'U', 'source_sha256': digest(case.source_for('U')), 'status': 'blocked', 'reset_ok': False, 'query': GRAPH_QUERY}
    destination.parent.mkdir(parents=True, exist_ok=True)
    probe_work = Path(tempfile.mkdtemp(prefix='diagnostic-probe-', dir=destination.parent))
    print('Recovered and verified all 30 v4 graph outputs. Checking one live diagnostic return on CPU.', flush=True)
    try:
        with (worker_factory or fresh_worker)(cfg, probe_work) as client:
            try:
                client.import_code(case.source_for('U'), project_name='rq1_diagnostic_probe')
                response = client.run(GRAPH_QUERY)
                probe.update(stdout=response.stdout, query_success=response.success)
                if not response.success:
                    raise ValueError('Current diagnostic query failed')
                probe.update(parse_graph(response.stdout, case.source_for('U')))
                calls = client.run(CALLS_QUERY)
                probe.update(calls_stdout=calls.stdout, calls_success=calls.success, status='ok')
            finally:
                client.reset()
                probe['reset_ok'] = True
    finally:
        result['live_diagnostic_probe'] = probe
        write_json(destination, result)
        write_json(probe_work / 'receipt.json', result)
    validate_receipt(result, evidence_root=destination.parent)
    result['ready'] = True
    write_json(destination, result)
    write_json(probe_work / 'receipt.json', result)
    from .calibration import prepare
    prepare(config)
    token_audit(config)
    if not doctor('local', config, root / 'local-doctor'):
        raise ValueError('Local technical doctor is still blocked')
    print('RQ1_CPU_RECOVERY_OK: 30 verified historical graph results + one fresh diagnostic probe; assessor calibration pending')
    return result


def main():
    from evidence_experiment.schema import IMPLEMENTATION_ID

    from .setup import DEFAULT_CONFIG, ROOT
    if IMPLEMENTATION_ID != 'rq1-v5':
        raise SystemExit('Historical v4-to-v5 recovery only. V6 requires a fresh local CPU checkpoint; preserve old receipts.')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous', type=Path, default=ROOT / 'work/rq1-v4')
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = p.parse_args()
    with work_lock(ROOT / 'work/rq1-v5'):
        recover(args.previous, args.config)


if __name__ == '__main__':
    main()
