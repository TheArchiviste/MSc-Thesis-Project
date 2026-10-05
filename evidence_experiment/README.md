# Evidence retrieval experiment

This package runs a source-to-evidence study against LLMxCPG at
`7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b` without changing the detector.
It is an **experiment engine for a curated, documented corpus**. It does not
manufacture vulnerability ground truth or claim that finite tests prove source
equivalence. The study needs a separately prepared Juliet corpus, independent
mechanism annotations, admissible paired changes, and human review.

The four-case, source-first preparation pilot is in
[`juliet_pilot/`](../juliet_pilot/README.md). It supplies baseline U cases,
fixed controls, source line maps, a proposed adequacy rubric, and reproducible
ASan witnesses. It does not yet supply paired transformations or detector
outcomes.

## Research questions and estimands

* **RQ1:** All included documented vulnerable originals enter the baseline,
  whether detection succeeded, failed, or abstained. Report the externally
  adjudicated adequacy of what the detector actually saw, mechanism-element
  coverage, and adequacy crossed with verdict. A baseline miss is not screened
  away.
* **RQ2:** Among admissible, originally adequate cases with the target **and**
  matched control in the original selected slice, estimate the paired risk
  difference `Pr(adequacy(U)=1, adequacy(TM)=0 | adequate U) -
  Pr(adequacy(U)=1, adequacy(TN)=0 | adequate U)`. In this conditional population
  this reduces to `mean(loss_TM - loss_TN)`. The analysis reports both absolute
  rates, exclusions, unmodified assessment variation, and a cluster bootstrap
  interval. Correct verdicts despite evidence loss remain in the analysis.
* **RQ3:** Preserve generated queries, CPGQL calls and responses, raw failures,
  selected and rendered lines, detector results, and fixed-query/rule probes.
  The diagnostic table calls its labels *observed changes*. Different queries
  or a failed rule probe do not, by themselves, identify a unique cause.

Mechanism coverage uses source coordinate mappings; adequacy depends on a
blind assessment and a separate, case-specific check against the documented
mechanism. An alternative sufficient route may remain when the original
target line disappears. The measured quantity is evidence sufficiency under a
specified review rubric, not necessity or model faithfulness.

## Input contract

Supply `cases.jsonl` with one record per vulnerable case. Paths are relative
to its directory. A baseline-only case needs `U`, an externally prepared
referent, `case_id`, `cluster_id`, and `cwe`. A paired case also needs both
`TM` and `TN`, element mappings in each transformed source, line numbers for
the originally selected target and proposed control, an operator name, and
admissibility checks. `cluster_id` must group related Juliet flow variants.

```json
{"case_id":"c1","cluster_id":"functional_variant_1","cwe":"CWE-121","sources":{"U":"src/c1.c","TM":"src/c1_alias_target.c","TN":"src/c1_alias_control.c"},"operator":"alias","referent":{"elements":[{"id":"allocation","role":"allocation","lines":[12],"mapped_lines":{"TM":[13],"TN":[12]}},{"id":"sink","role":"sink","lines":[23],"mapped_lines":{"TM":[24],"TN":[24]}}],"relations":["write length exceeds destination bound under input condition"],"target_lines":[23],"control_lines":[18]},"validation":{"compile":"pass","benign_behavior":"pass","trigger":"pass","mechanism_preserved":"pass","line_map":"pass","match":"pass","control_purity":"pass"},"control_in_slice":true,"rule_queries":[]}
```

The example coordinates are illustrative. The prepared corpus must remove
Juliet label leaks before Q or D sees the code. Produce element accounts from
annotations, execution evidence, and human adjudication **without requiring
agreement with Joern**. A CPG rule is a diagnostic probe, not the ground truth;
`rule_queries` may be empty if no validated rule is available. Map moved and
newly introduced mechanism roles explicitly. Review absent guards and other
relations in the adequacy rubric, rather than pretending they are source lines.

The `validation` statuses require retained evidence. `compile`, `trigger` and
`benign_behavior` must additionally pass the executable witness command. The
other checks require a documented review of line mapping, control purity,
matching, and mechanism preservation. If any is uncertain, mark
`indeterminate`, and the case will not enter the paired arms. Prefer controls
of the same statement/operator kind and comparable structural depth and
position. The primary comparison enforces that the target and control both
occur in the first original slice. Report excluded pairs and balance by
operator, family, kind, depth, and change magnitude in the Methods/Results.

For finite witness checks, `witness_plan.jsonl` has one row per paired case:

```json
{"case_id":"c1","build_argv":["clang","-std=gnu11","-O0","-g","-fsanitize=address","{source}","driver.c","testcasesupport/io.c","-o","{binary}"],"benign_inputs":["0\n","5\n"],"trigger_input":"100\n","asan_class":"stack-buffer-overflow"}
```

Add `-I` and other fixed arguments needed by your build. `{source}` and
`{binary}` are replaced as individual argv items; there is no shell expansion.
The runner compares stdout, stderr and exit code on specified benign inputs
and the expected ASan class on the trigger. Preserve `witness_validation.jsonl`
and the original human admissibility evidence. Compilation and observed
execution are bounded checks, not a universal equivalence proof.

## Configuration and workflow

Create a JSON config with the exact pipeline commit, threshold frozen on a
**separate** calibration split, Q/D model revisions, Joern image digest,
server configuration, and inference engine:

```json
{"pipeline_commit":"7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b","threshold":0.5,"query_model":"QCRI/LLMxCPG-Q","query_revision":"FULL_HF_SHA","detector_model":"QCRI/LLMxCPG-D","detector_revision":"FULL_HF_SHA","joern_digest":"sha256:PINNED_DIGEST","query_engine":"vllm","joern_host":"localhost","joern_port":8080,"joern_input_dir":"work/joern-inputs","server_input_dir":"/analysis/inputs"}
```

The numeric threshold above is only a placeholder. Collect Q → slice → D
scores on a disjoint, mixed-label calibration split and a held-out safe
specificity split. Each row has `sample_id`, `cluster_id`, `split`, `label`,
and `p_vulnerable`. Run `python -m evidence_experiment calibrate --manifest
corpus/cases.jsonl --work run --calibration-scores corpus/calibration_scores.jsonl`.
This rejects cluster overlap, reports the full threshold sweep and a detector
usability screen, and writes `calibration.json`. Freeze its threshold in the
config **before** the main run. The adequacy estimand does not require a
correct classifier verdict for inclusion.

```bash
python -m evidence_experiment verify --manifest corpus/cases.jsonl --work run
python -m evidence_experiment validate --manifest corpus/cases.jsonl --work run --witness-plan corpus/witness_plan.jsonl
python -m evidence_experiment all --manifest corpus/cases.jsonl --work run --config corpus/config.json
python -m evidence_experiment packets --manifest corpus/cases.jsonl --work run --config corpus/config.json
```

The `all` command executes Q in batches, releases its model, runs Joern
sequentially, then loads D and classifies single snippets. Each phase can be
called separately as `query`, `slice`, or `detect`; JSONL outputs are
append-only and resumable. Input and harness hashes in
`experiment_lock.json` prevent accidental reuse after a change. Joern
transport failures, unknown errors and context overflows stay uncertain;
abstentions are never silently counted as safe predictions. Real timeout and
worker restart supervision should run outside this process in the GPU/Joern
deployment.

`blind_review_packets.jsonl` contains only `review_id` and numbered excerpt:
no arm, case identifier, known CWE, or detector verdict. Collect one or more
independent assessments per unique packet. Example row:

```json
{"review_id":"HASH_FROM_PACKET","assessor_id":"reviewer_1","adequacy":"adequate","cited_lines":[12,23],"relationships":["unchecked write length exceeds allocation"],"assumptions":["entry is reachable"],"explanation":"The allocation and input-controlled copy establish the documented condition."}
```

`adequacy` is `adequate`, `inadequate` or `uncertain`. A judge may be a separate
LLM family, but calibrate it against independently adjudicated human ratings,
including deficient and uncertain slices. Divergent assessor decisions become
uncertain in the primary analysis. Blind reviewers decide whether the excerpt
justifies a vulnerability; after unblinding, a separate adjudicator compares
their explanation with the documented mechanism. The second JSONL is:

```json
{"case_id":"c1","review_id":"HASH_FROM_PACKET","match":"yes","reason":"The cited length/bound relationship matches the documented flaw."}
```

`match` is `yes`, `no` or `uncertain`. Every assessed `(case_id, review_id)`
needs an adjudication. Missing or disputed assessments remain uncertain; they
are not silently imputed as adequate or inadequate.

```bash
python -m evidence_experiment analyze --manifest corpus/cases.jsonl --work run --config corpus/config.json --assessments reviews.jsonl --adjudications adjudications.jsonl
```

`analysis.json` contains baseline denominators, family breakdown, paired
adequacy-loss estimates, exclusion counts, and run-level diagnostics. Before
the main run, pre-register the corpus rules, transformations, reviewer rubric,
control matching, repeats, threshold, CI method and primary outcome. Report
the yield and uncertainty of all pre-analysis filters. These controlled cases
do not estimate prevalence in production code.

## Tests and operational boundaries

`python -m unittest discover -s tests -p 'test_evidence*.py'` tests the key
estimand on synthetic run data, including a missed baseline case and a correct
verdict after evidence loss. The interface tests run the pinned extractor with
a fake Joern client. They do not exercise the real model, Joern server, ASan,
or Juliet. Perform a 20-program smoke run with the exact pinned dependencies,
an instrumented CPG trace, and blinded human review before collecting the
main sample. The current package accepts externally authored source
transformations; it does not generate aliases/wrappers or perform independent
semantic annotation for you.
