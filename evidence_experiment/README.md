# Evidence retrieval experiment

This package runs a source-to-evidence study against LLMxCPG. Q generation and
Joern slicing are pinned to `7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b`; the
detector loader was revised afterwards to take explicit adapter and base pins.
Every lock records the actual checkout and checks that the Q/Joern files still
match the pinned commit (see [Locks](#locks-and-provenance)).

It is an **experiment engine for a curated, documented corpus**. It does not
manufacture vulnerability ground truth or claim that finite tests prove source
equivalence. The study needs a separately prepared Juliet corpus, independent
mechanism annotations, admissible paired changes, and human review.

The four-case, source-first preparation pilot is in
[`juliet_pilot/`](../juliet_pilot/README.md). It supplies baseline U cases,
fixed controls, source line maps, a proposed adequacy rubric, templated review
claims, and reproducible ASan witnesses. It does not yet supply paired
transformations or detector outcomes. The ordered execution checklist is in
[NEXT_ACTIONS.md](NEXT_ACTIONS.md).

## Research questions and estimands

* **RQ1:** All included documented vulnerable originals enter the baseline,
  whether detection succeeded, failed, or abstained. Report the externally
  adjudicated adequacy of what the detector actually saw, mechanism-element
  coverage, and adequacy crossed with verdict. A baseline miss is not screened
  away.
* **RQ2:** Among admissible, originally adequate cases with the target **and**
  matched control in the original selected slice, estimate the paired risk
  difference `Pr(adequacy(U)=1, adequacy(TM)=0 | adequate U) -
  Pr(adequacy(U)=1, adequacy(TN)=0 | adequate U)`, which reduces to
  `mean(loss_TM - loss_TN)` in this population. `analysis.json` reports:
  * all resolved pairs, with a cluster bootstrap interval when at least two
    clusters remain;
  * `one_case_per_cluster`: one seeded pair per template cluster, with the
    exact McNemar p-value and a Newcombe (method 10) interval. With fewer than
    about 30 clusters this independent-pairs analysis is the better primary
    choice; the protocol must say which is primary;
  * worst-case bounds that keep unresolved transformed outcomes in the
    eligible denominator;
  * `coverage_change_all_admissible`: the reviewer-free change in referent
    element coverage for every admissible pair, inside and outside the
    primary population. This is descriptive, not sufficiency.

  Correct verdicts despite evidence loss remain in the analysis.
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
referent with a templated `review_claim`, `case_id`, `cluster_id`, and `cwe`.
A paired case also needs both `TM` and `TN`, element mappings in each
transformed source, line numbers for the originally selected target and
proposed control, an operator name, and admissibility checks. `cluster_id`
must be one id per flaw template: [`juliet_pilot/templates.py`](../juliet_pilot/templates.py)
derives it from a Juliet path so source, data-type, allocation-style and flow
variants of one template share a cluster.

```json
{"case_id":"c1","cluster_id":"CWE121-CWE805-copy","cwe":"CWE-121","sources":{"U":"src/c1.c","TM":"src/c1_alias_target.c","TN":"src/c1_alias_control.c","F":"src/c1_fixed.c"},"operator":"alias","referent":{"review_claim":{"flaw_class":"stack buffer overflow","operation":"memcpy call"},"elements":[{"id":"allocation","role":"allocation","lines":[12],"mapped_lines":{"TM":[13],"TN":[12]}},{"id":"sink","role":"sink","lines":[23],"mapped_lines":{"TM":[24],"TN":[24]}}],"relations":["write length exceeds destination bound under input condition"],"target_lines":[23],"control_lines":[18]},"validation":{"compile":"pass","benign_behavior":"pass","trigger":"pass","mechanism_preserved":"pass","line_map":"pass","match":"pass","control_purity":"pass"},"control_in_slice":true,"rule_queries":{"U":["VALIDATED_BASELINE_CPGQL"],"TM":["VALIDATED_TRANSFORMED_CPGQL"],"TN":["VALIDATED_CONTROL_CPGQL"]}}
```

* **`review_claim`** asks every case at one granularity:
  `{"flaw_class": ..., "operation": ...}` renders as *"Does this excerpt justify
  a stack buffer overflow at the memcpy call?"*. `flaw_class` comes from a
  controlled vocabulary (`evidence_experiment.review.CLAIM_CLASSES`).
  `operation` names the statement or call in at most five words, with no
  numbers and no causal words (`terminator`, `bound`, `guard`, `size`,
  `freed`, …). Final `packets` and `analyze` refuse free-text claims;
  `verify` lists any claim problems.
* **`sources.F`** (optional) is the documented fixed variant of the same
  template. It runs once through regenerated Q → Joern (and D), and its
  excerpt enters the blind queue with the same claim as a decoy. It never
  enters RQ1–RQ3. See [Review queue](#review-queue).

The example coordinates are illustrative. The prepared corpus must remove
Juliet label leaks before Q or D sees the code. Produce element accounts from
annotations, execution evidence, and human adjudication **without requiring
agreement with Joern**. A CPG rule is a diagnostic probe, not the ground truth;
`rule_queries` may be `{}` if no validated rule is available. Each available
rule is written for its own arm and executed once on that arm; a baseline
rule cannot be assumed to have the same source coordinates after a transform.
Map moved and newly introduced mechanism roles explicitly. Review absent
guards and other relations in the adequacy rubric, rather than pretending they
are source lines.

The whole manifest is part of the acquisition fingerprint, so referents,
target/control lines and claims are frozen before Q runs. That is deliberate:
they must not be revised after seeing slices.

The `validation` statuses require retained evidence. `compile`, `trigger` and
`benign_behavior` must additionally pass the executable witness command when
benign inputs exist. If none are feasible, use `"benign_behavior":"not_applicable"`
with a documented `benign_reason`, and set `benign_inputs` to `[]` in the
witness plan. This reduces the strength of the validation claim and should be
reported as such. The other checks require a documented review of line
mapping, control purity, matching, and mechanism preservation. If any is
uncertain, mark `indeterminate`, and the case will not enter the paired arms.
Prefer controls of the same statement/operator kind and comparable structural
depth and position. The primary comparison enforces that the target and
control both occur in the first original slice. Report excluded pairs and
balance by operator, family, kind, depth, and change magnitude.

For finite witness checks, `witness_plan.jsonl` has one row per paired case:

```json
{"case_id":"c1","build_argv":["clang","-std=gnu11","-O0","-g","-fsanitize=address","{source}","driver.c","testcasesupport/io.c","-o","{binary}"],"benign_inputs":["0\n","5\n"],"trigger_input":"100\n","asan_class":"stack-buffer-overflow"}
```

Add `-I` and other fixed arguments needed by your build. `{source}` and
`{binary}` are replaced as individual argv items; there is no shell expansion.
The runner compares stdout, stderr (with process ids and addresses
normalised) and exit code on benign inputs, and the expected ASan class on the
trigger. With `-g`, the ASan report also names the source lines of the faulting
access and, for heap objects, the allocation and free sites; compare those with
`mapped_lines` when reviewing `mechanism_preserved`. Preserve
`witness_validation.jsonl` and the human admissibility evidence. Compilation
and observed execution are bounded checks, not a universal equivalence proof.

## Configuration and workflow

Create a JSON config with the pinned pipeline commit, Q/D model revisions,
Joern image digest, server configuration, inference engine and the
predeclared calibration abstention policy. `threshold` is added only after
calibration:

```json
{"pipeline_commit":"7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b","query_model":"QCRI/LLMxCPG-Q","query_revision":"FULL_HF_SHA","detector_model":"QCRI/LLMxCPG-D","detector_revision":"FULL_ADAPTER_SHA","detector_base_model":"unsloth/qwq-32b-preview-bnb-4bit","detector_base_revision":"FULL_BASE_SHA","detector_calibration_abstentions":"exclude","joern_digest":"sha256:PINNED_DIGEST","query_engine":"vllm","joern_host":"localhost","joern_port":8080,"joern_input_dir":"work/joern-inputs","server_input_dir":"/analysis/inputs"}
```

Keys named `threshold` or `detector_*` belong to the detector lock, so
changing them never invalidates acquired Q/Joern evidence.

### 1. Acquire and review evidence (no D needed)

```bash
python -m evidence_experiment verify   --manifest corpus/cases.jsonl --work work/main-001
python -m evidence_experiment validate --manifest corpus/cases.jsonl --work work/main-001 --witness-plan corpus/witness_plan.jsonl
python -m evidence_experiment query    --manifest corpus/cases.jsonl --work work/main-001 --config corpus/config.json --repeats 1
python -m evidence_experiment slice    --manifest corpus/cases.jsonl --work work/main-001 --config corpus/config.json --repeats 1
python -m evidence_experiment packets  --manifest corpus/cases.jsonl --work work/main-001 --config corpus/config.json --repeats 1 --duplicate-fraction 0.1 --review-seed 20261006
```

Pass the same `--repeats` to every command for a work directory. Stage JSONL
outputs are append-only and resumable. Joern transport failures, unknown
errors and context overflows stay uncertain; abstentions are never silently
counted as safe predictions. Real timeout and worker restart supervision
should run outside this process in the GPU/Joern deployment.

### 2. Calibrate D in its own directory

Write `corpus/calibration_manifest.jsonl` with one predeclared source per row:
`sample_id`, `cluster_id`, `split` (`calibration` or `specificity`), `label`
(`0` safe or `1` vulnerable), and `source` (path relative to this manifest).
The calibration split needs both labels; the held-out specificity split must
be safe. Neither split may share a template cluster with the analysis corpus
or each other. The same Q → Joern → D stages score every sample, with traces:

```bash
python -m evidence_experiment score-calibration --manifest corpus/cases.jsonl --calibration-manifest corpus/calibration_manifest.jsonl --config corpus/config.json --work work/calibration-001
```

Samples without a score (Q, Joern or context failures; common for safe code,
where Q's query may find no flow) follow `detector_calibration_abstentions`:
`fail` (default) refuses a threshold; `exclude` calibrates on the scored
samples and reports enrolled/scored/abstained counts by split and label in
`calibration.json`. Decide the policy in the protocol. If you must change the
calibration sample list, use a new `work/calibration-00N` directory; the
acquisition directory is unaffected.

Inspect `work/calibration-001/calibration_run/{queries,slices,detector}.jsonl`,
`calibration_failures.jsonl`, the threshold sweep and the usability screen in
`calibration.json`. `calibrate --calibration-scores` is an offline exploratory
check; its untraced result cannot unlock detection.

### 3. Detect and analyse

Copy the calibrated threshold into the config, then:

```bash
python -m evidence_experiment detect  --manifest corpus/cases.jsonl --work work/main-001 --config corpus/config.json --repeats 1 --calibration work/calibration-001/calibration.json
python -m evidence_experiment analyze --manifest corpus/cases.jsonl --work work/main-001 --config corpus/config.json --repeats 1 --assessments reviews.jsonl --adjudications adjudications.jsonl --resolutions resolutions.jsonl
```

`detect` checks that the calibration's scores and analysis manifest are
unchanged and that its usability gate passed, and records the calibration
path and hash in `detector_lock.json`. The `all` command runs every model
phase in one call.

## Review queue

`packets` writes two files:

* `blind_review_packets.jsonl` for reviewers: `review_id`, the templated
  claim, and a numbered excerpt. No arm, case id, CWE or verdict. Packets are
  ordered by `review_id` (a content hash), which interleaves cases and arms.
* `review_key.jsonl` for the coordinator only: each packet's kind
  (`evidence`, `decoy`, `evidence_and_decoy`, `duplicate`) and, for
  duplicates, the original packet and line offset. Do not share it or the
  work directory with reviewers.

Decoys are the fixed variants (`sources.F`). A decoy rated adequate is a false
adequacy; a decoy excerpt identical to its vulnerable excerpt
(`evidence_and_decoy`) shows the slice dropped the distinguishing lines.
Tell reviewers that some excerpts come from programs where the claim is false.

`--duplicate-fraction` re-issues a seeded share of evidence packets with every
line label shifted by a random offset and a new `review_id`, to estimate rater
test-retest agreement. The issued queue is frozen: running `packets` again with
different settings or evidence refuses to overwrite it.

Collect two independent assessments per packet. Example row:

```json
{"review_id":"HASH_FROM_PACKET","assessor_id":"reviewer_1","adequacy":"adequate","cited_lines":[12,23],"relationships":["unchecked write length exceeds allocation"],"assumptions":["entry is reachable"],"explanation":"The allocation and input-controlled copy establish the documented condition."}
```

`adequacy` is `adequate`, `inadequate` or `uncertain`. A judge may be a separate
LLM family, but calibrate it against independently adjudicated human ratings,
including deficient and uncertain slices. Missing second ratings and unresolved
disagreements remain uncertain. For a disagreement, supply a separate
`--resolutions` JSONL row with `review_id`, `method` (`third_review` or
`consensus`), `adequacy`, and `reason`; an adequate resolution also needs
`cited_lines` and `relationships`, while a third review needs a distinct
`assessor_id`. Blind reviewers decide whether the excerpt justifies the claim;
after unblinding, a separate adjudicator compares their explanation with the
documented mechanism. Adjudications are needed for evidence packets only, not
decoys or duplicates:

```json
{"case_id":"c1","review_id":"HASH_FROM_PACKET","match":"yes","reason":"The cited length/bound relationship matches the documented flaw."}
```

`match` is `yes`, `no` or `uncertain`. Missing or disputed assessments remain
uncertain; they are not silently imputed as adequate or inadequate.

Add `--evidence-only` to `analyze` if D has not been run; the verdict
dimension is then `not_run`, never a missed or abstained classification.
`analysis.json` contains baseline denominators, family breakdown, the RQ2
estimates above, exclusion counts, RQ3 patterns, and `review_quality`:
percent agreement, Fleiss' kappa and Gwet's AC1 overall and by arm; decoy
false-adequacy rates and the vulnerable-by-fixed rating table; and duplicate
test-retest agreement. `analysis_provenance` records the analysis and review
code hashes, input file hashes, the analysis seed and the checkout.

Before the main run, pre-register the corpus rules, transformations, reviewer
rubric, claim vocabulary, control matching, repeats, abstention policy,
primary RQ2 analysis, CI method and decoy/duplicate shares. Report the yield
and uncertainty of all pre-analysis filters. These controlled cases do not
estimate prevalence in production code.

## Locks and provenance

| Lock | Freezes | Enforced in | Package versions |
|---|---|---|---|
| `experiment_lock.json` | manifest, sources, acquisition config, repeats, witness results, `runner.py`/`schema.py`/`validate.py`, Q/Joern `llmxcpg` files (repository-relative paths) | every phase after `validate` | `cpgqls-client`, `websocket-client`, `vllm`, `torch`, `transformers`, enforced only for `query`, `slice`, `all` |
| `detector_lock.json` | calibration file, `threshold` and `detector_*` settings, D loader code | `detect`, `all` | `torch`, `transformers`, `peft`, `bitsandbytes`, `accelerate` |
| `review_key.jsonl` | the issued review queue | `packets` | none |

`packets` and `analyze` only record their environment in `phase_log.jsonl`, so
review and analysis can run on a laptop or from a fresh clone at another path.
Acquisition refuses to run when the Q/Joern files differ from the pinned
commit; a shallow clone without that commit records the check as
`unverifiable`. Locks written before this format are refused: start a new work
directory.

## Tests and operational boundaries

`python -m pytest -q` runs the synthetic estimand, review-queue, statistics,
lock and witness tests. The interface tests run the pinned extractor with a
fake Joern client. They do not exercise the real model, Joern server, ASan, or
Juliet. Perform a small smoke run with the exact pinned dependencies, an
instrumented CPG trace, and blinded human review before collecting the main
sample. The current package accepts externally authored source
transformations; it does not generate aliases/wrappers or perform independent
semantic annotation for you.
