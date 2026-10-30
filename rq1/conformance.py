"""CPU apparatus checks: fixed selector fixtures and all 30 corpus graph imports."""
from __future__ import annotations

import re
import traceback

from evidence_experiment.locks import environment, now, policy
from evidence_experiment.runner import extract_one
from evidence_experiment.schema import digest, load_cases, write_json

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
INTERPROCEDURAL_SOURCE = """#define RQ1_VALUE 1
#define RQ1_ID(x) (x)
void fixture_sink(int n) {
    char buffer[4];
    if (n >= 0) {
        buffer[n] = RQ1_VALUE;
    }
}
void fixture_entry(int n) {
    fixture_sink(RQ1_ID(n));
}
"""
INTERPROCEDURAL_QUERIES = [
    'val source = cpg.method.nameExact("fixture_entry").parameter.nameExact("n").l',
    'val sink = cpg.call.nameExact("<operator>.indirectIndexAccess").argument(2).l',
    'val execution_path = sink.reachableByFlows(source).l',
]
GRAPH_QUERY = ('println("RQ1_GRAPH=" + List(cpg.method.nameExact("case_entry").size, '
               'cpg.method.nameExact("case_sink").size, cpg.call.nameExact("case_sink").size, '
               'cpg.method.nameExact("case_sink").parameter.index(1).size).mkString(",") + "|" + '
               'cpg.call.nameExact("case_sink").lineNumber.l.toSet.toList.sorted.mkString(","))')
CALLS_QUERY = 'println("RQ1_CALLS=" + cpg.call.name.l.distinct.sorted.mkString(","))'


def parse_graph(stdout, source):
    matches = re.findall(r'(?m)^RQ1_GRAPH=([0-9,]+)\|([0-9,]*)\s*$', stdout)
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous corpus graph marker')
    counts = [int(n) for n in matches[0][0].split(',')]
    coords = [int(n) for n in matches[0][1].split(',') if n]
    expected = [i for i, line in enumerate(source.splitlines(), 1) if 'case_sink(data);' in line]
    if counts != [1, 1, 1, 1] or coords != expected or len(expected) != 1:
        raise ValueError(f'Apparatus graph/line mapping mismatch: counts={counts}, call={coords}, expected={expected}')
    return {'method_call_parameter_counts': counts, 'caller_lines': coords}


def fixture_valid(outcome, *, interprocedural=False):
    selected = 6 if interprocedural else 4
    required = {3, 5, 6, 7, 8} if interprocedural else {1, 3, 4, 5, 6}
    stages = {r.get('stage') for r in outcome.get('trace', []) if r.get('success')}
    return (outcome.get('status') == 'ok' and selected in outcome.get('slice_lines', []) and
            required <= set(outcome.get('rendered_lines', [])) and
            {'graph_import', 'query_execution', 'context_expansion', 'slice_construction'} <= stages)


def expected_graphs():
    from .setup import CORPUS
    return {(c.case_id, arm): digest(source) for split in ('development', 'main')
            for c in load_cases(CORPUS / f'{split}.jsonl') for arm, source in c.sources.items()}


def validate_receipt(result):
    if (result.get('source') != SOURCE or result.get('queries') != QUERIES or
            not fixture_valid(result.get('outcome', {})) or
            result.get('interprocedural_source') != INTERPROCEDURAL_SOURCE or
            result.get('interprocedural_queries') != INTERPROCEDURAL_QUERIES or
            not fixture_valid(result.get('interprocedural_outcome', {}), interprocedural=True)):
        raise ValueError('Capability receipt lacks complete successful local and interprocedural selector traces')
    rows = result.get('corpus_graphs', [])
    expected = expected_graphs()
    if len(rows) != len(expected) or {(r['case_id'], r['arm']): r['source_sha256'] for r in rows} != expected:
        raise ValueError('Capability receipt must cover exactly all 30 current U/F source graphs')
    from .setup import CORPUS
    sources = {(c.case_id, a): s for split in ('development', 'main')
               for c in load_cases(CORPUS / f'{split}.jsonl') for a, s in c.sources.items()}
    for row in rows:
        if row.get('status') != 'ok' or row.get('reset_ok') is not True:
            raise ValueError('A corpus graph import/mapping/reset remains blocked')
        parse_graph(row['graph_stdout'], sources[row['case_id'], row['arm']])


def check(config):
    from .joern_worker import fresh_worker
    from .setup import ROOT, corpus_contract, load_config, verify_corpus, verify_implementation
    verify_corpus()
    verify_implementation()
    cfg = load_config(config)
    destination = ROOT / cfg['joern_capability_file']
    result = {'utc': now(), 'ready': False, 'synthetic': False, 'fixture_only': False,
              'meaning': 'Real CPU Joern: two synthetic apparatus fixtures and structural imports of 30 corpus sources. No generated Q queries or main adequacy previews; no fact-coverage gate.',
              'corpus_contract': corpus_contract(), 'policy': policy(cfg), 'environment': environment(), 'source': SOURCE, 'queries': QUERIES,
              'interprocedural_source': INTERPROCEDURAL_SOURCE, 'interprocedural_queries': INTERPROCEDURAL_QUERIES,
              'corpus_graphs': []}
    try:
        for name, source, queries, interproc in (
                ('outcome', SOURCE, QUERIES, False),
                ('interprocedural_outcome', INTERPROCEDURAL_SOURCE, INTERPROCEDURAL_QUERIES, True)):
            with fresh_worker(cfg, destination.parent / name) as client:
                result[name] = extract_one(client, source, queries, 'rq1_' + name)
            write_json(destination, result)
            if not fixture_valid(result[name], interprocedural=interproc):
                raise ValueError(f'Fixed selector apparatus fixture failed: {name}')
        from .setup import CORPUS
        for split in ('development', 'main'):
            for case in load_cases(CORPUS / f'{split}.jsonl'):
                for arm, source in case.sources.items():
                    record = {'case_id': case.case_id, 'arm': arm, 'source_sha256': digest(source), 'status': 'blocked', 'reset_ok': False}
                    print(f'CPU graph check {len(result["corpus_graphs"])+1}/30: {case.case_id}/{arm}', flush=True)
                    try:
                        with fresh_worker(cfg, destination.parent / f'{case.case_id}-{arm}') as client:
                            try:
                                client.import_code(source, project_name=f'rq1_graph_{case.case_id}_{arm}')
                                query = client.run(GRAPH_QUERY)
                                record['graph_stdout'] = query.stdout
                                if not query.success:
                                    raise ValueError('Graph structural query failed')
                                record.update(parse_graph(query.stdout, source))
                                calls = client.run(CALLS_QUERY)
                                record['macro_and_call_observations'] = calls.stdout
                                record['call_observations_success'] = calls.success
                                record['status'] = 'ok'
                            finally:
                                client.reset()
                                record['reset_ok'] = True
                    except Exception as exc:  # noqa: BLE001 - keep apparatus failure and continue diagnostic census
                        record['error'] = repr(exc)
                        record['traceback'] = traceback.format_exc()
                    result['corpus_graphs'].append(record)
                    write_json(destination, result)
        validate_receipt(result)
        result['ready'] = True
    except Exception as exc:  # noqa: BLE001 - retain full diagnostic, never manufacture readiness
        result['error'] = repr(exc)
        result['traceback'] = traceback.format_exc()
        if hasattr(exc, 'outcome'):
            result['failed_worker_outcome'] = exc.outcome
    write_json(destination, result)
    (destination.parent / 'readiness.md').write_text(
        f'# CPU selector and corpus graph readiness\n\nResult: **{"PASS" if result["ready"] else "BLOCKED"}**.\n\n'
        f'Corpus graph records: {len(result["corpus_graphs"])}/30. Fixed local and interprocedural/macro fixtures test the apparatus.\n'
        'Corpus checks verify methods, caller coordinates and fresh import/reset; macro/call observations are diagnostics.\n'
        'Missing mechanism evidence in later Q-selected slices remains an RQ1 finding. No source fact coverage is required here.\n'
        'Inspect readiness.json and per-input worker/server logs. No Q model is loaded.\n')
    print(f'CPU capability: {"PASS" if result["ready"] else "BLOCKED"}; {destination}')
    return result['ready']
