# RQ1 repository readiness audit — 29 October 2026

**Verdict: hold experiment collection.** The corpus, finite witnesses, token lengths and rented GPU/package imports have passed their respective checks. The repository still has confirmed acquisition/reporting safeguards to repair and a reference-implementation identity issue to resolve. Passing the existing tests is insufficient to declare collection ready.

This is an investigation of the narrowed **RQ1-only** experiment. It does not approve D, calibration, training, transformations, RQ2 or RQ3. No model weights were downloaded and no real Q generation or experiment Joern slicing was performed during this audit. Synthetic fixtures below are software tests, never dissertation observations.

## Versions and current checkpoint

| Item | Audited state |
|---|---|
| Repository | `TheArchiviste/MSc-Thesis-Project` |
| Working branch at audit start | `codex/rq1-execution` |
| Branch head audited | `469b3050b6f35a6756b5ac66084e6bc52459471e` |
| Experiment source installed on Nebius | `81a7a8a7543a8c5bc9fab4ffc759b9e9f202b643` |
| Difference between those commits | Nebius documentation only; experiment code is identical |
| Fork's preserved Q/Joern core | `7023ff49fe7b800e8b26bcae52e2fcdafe95fa9b`; audited paths still match |
| Released Q checkpoint | `QCRI/LLMxCPG-Q`, revision `1f48ab60420d90277207394f1254d27d3375b07e` |
| QCRI comparison reference | `qcri/llmxcpg`, commit `fd7af0df8d2221ec196b85bc460da5cb40f6866c` |
| Laptop input transfer | User screenshot confirms upload of the three-file archive and its checksum file |
| Remote archive verification | Pending; an upload completion message is not a remote checksum check |
| Full GPU doctor / real Q load | Pending |
| Main acquisition freeze | Not issued |
| Real experiment outputs | None reported; the audit created no real Q/slice records |

The user-created Nebius VM should remain **Stopped** through the Nebius console during repairs. Its current stopped/running state was not inspected by this audit. A stopped VM's retained disk continues to incur storage charges. Read the existing dated `rq1/READINESS.md` as an earlier snapshot; this report records the later state. Updating a file inside `rq1/` would change the token-audit corpus contract, so this audit and the operational guide are kept under `docs/`.

## What was checked successfully

| Check | Result and limits |
|---|---|
| Existing test suite | **99 tests and 2 subtests pass** in the audit's complete local test environment |
| Repository-wide Ruff | **Pass** |
| Python compilation | `llmxcpg`, `scripts`, `tests`, `evidence_experiment` and `rq1` compile |
| Corpus verification | 3 development cases and 12 main cases; rendering, line maps, references and support hashes reproduce |
| Block separation | Development and main use disjoint generator blocks; one case per enrolled block |
| Inclusion ledger | 3 development + 12 main + 2 pre-inference exclusions + 3 unused reserves = 20 blocks |
| Fresh CPU witness audit | All **30** U/F sources compile; all **15 U** executions trigger their expected ASan class; all **15 F** executions pass their specified checks |
| Benign witness | Development CWE129 U/F pass the specified benign input; other U inputs have documented non-applicability |
| User's uploaded token audit | Exactly **30** expected records, no duplicates, matching source hashes and current corpus contract; all fit; largest prompt plus generation allowance is **2618 / 8192** tokens |
| Local Joern, prior user evidence | Real staged C import/query passed on digest-pinned Joern **4.0.667**; this was a basic CPG smoke test, not full slicing |
| GPU, user screenshot | One H100 80 GB, driver **580.173.02**, approximately **196 GiB RAM**, **224 GiB** free disk at the hardware check |
| GPU packages, user screenshot | Python **3.11.18**, Torch **2.5.1+cu124**, Transformers **4.47.1**, vLLM **0.6.6.post1**, CUDA visibility and BF16 checks pass |
| Shell syntax | Both local helper scripts and all **10** Bash blocks in the Nebius guide parse |
| Audit CPU package consistency | `pip check` passes |

The fresh witness audit ran here on CPU. It does not replace the user's retained laptop witness file, and its outputs must not be substituted into the uploaded archive. These are finite executions and do not prove F safe for arbitrary inputs. The package-import check does not establish that the 65.5 GB-class checkpoint loads successfully with the requested KV cache and runtime allocations.

The first local test invocations lacked the declared test tools/plugins in the audit environment. Installing the project's declared pytest, pytest-asyncio and Ruff tools produced the passing result above without changing experiment code. The separate GitHub CI failure below is a genuine workflow defect, not that local environment setup issue.

## Findings and required changes

| ID | Priority | Finding | Resolution point |
|---|---|---|---|
| R01 | High | The evaluated fork is not identical to QCRI's released prompt/context implementation | Define the reference contract before collecting Q outputs |
| R02 | High | Out-of-range CPG lines can become an empty excerpt with status `ok` | Repair before any slicing |
| R03 | High | Existing orphan query records can acquire a new lock and receipt without a model call | Repair before acquisition |
| R04 | High | Freeze can accept complete fixed-helper failures without proof of a successful full selector smoke test | Add an independent capability check and strengthen freeze evidence |
| R05 | Medium | Query environment enforcement omits important formatting/tokenizer dependencies and Python | Complete the environment contract before the accepted development run |
| R06 | Medium | Null assessment timestamps and foreign adjudication IDs are accepted | Repair before development assessment/freeze |
| R07 | Medium | Delayed consistency output is not integrated into the final report/completion state | Repair before final reporting |
| R08 | High | GitHub CI cannot access the historical pin after its shallow checkout | **Fixed and verified:** the corrected workflow passed remotely |
| R09 | Medium | A query piped through `tee` can hide Python's nonzero exit status | Correct execution blocks before collection |
| R10 | Low | Earlier status documents and guide checkpoint statements are stale | Guide updated; retain dated snapshots and refresh them with the next contract audit |

### R01 — implementation identity materially affects the research question

Matching this fork's core to commit `7023ff49...` establishes consistency with its own snapshot. It does **not** establish equivalence to QCRI's released implementation.

Two differences were directly reproduced without running Q or Joern:

1. `llmxcpg/prompts.py` renders a different Q prompt from QCRI's `gen_query_prompt`. Formatting, section text, fences and an example expression differ: the release uses `removedAll`, while the fork's example uses `removeAll`. The effect on actual Q outputs is unmeasured.
2. The fork's reconstruction adds enclosing function anchors. QCRI's context helper also restores enclosing control blocks. On the synthetic fixture below, selecting only the write produces fork lines **1, 4, 6**, while the released parser/context helper produces **1, 3, 4, 5, 6**. The latter includes the guard.

```c
void f(int n) {
  char a[4];
  if (n < 4) {
    a[n] = 0;
  }
}
```

This matters particularly for RQ1: missing a guard can change whether an excerpt justifies the claimed flaw. Reusing the original weights alone does not remove this implementation difference. QCRI's README also documents testing with Joern **4.0.408**, whereas the accepted local smoke test uses **4.0.667**. The fork explicitly uses a 2048-token generation allowance; the inspected release's LLM-manager default is 8128. These settings must be described as part of the evaluated configuration.

**Required action:** write an explicit compatibility/deviation contract for prompt construction, output parsing, path/slice construction, context expansion, generation limits and Joern version. For a dissertation intended to evaluate the released pipeline, align the relevant semantics with that reference before collection and record a new deliberate pipeline pin. If the existing fork is retained, describe the study as an audit of that adapted implementation and bound the conclusions accordingly. Do not silently change context expansion after looking at main outputs, and do not adopt every upstream default without checking its memory/context implications.

Sources at the inspected QCRI commit: [query prompt](https://github.com/qcri/llmxcpg/blob/fd7af0df8d2221ec196b85bc460da5cb40f6866c/queries/generate_and_run_queries.py), [context helper](https://github.com/qcri/llmxcpg/blob/fd7af0df8d2221ec196b85bc460da5cb40f6866c/queries/Components/enhancer.py), [block parser](https://github.com/qcri/llmxcpg/blob/fd7af0df8d2221ec196b85bc460da5cb40f6866c/queries/Components/c_parser.py), [LLM manager](https://github.com/qcri/llmxcpg/blob/fd7af0df8d2221ec196b85bc460da5cb40f6866c/queries/Components/model.py), and [README](https://github.com/qcri/llmxcpg/blob/fd7af0df8d2221ec196b85bc460da5cb40f6866c/README.md).

### R02 — empty evidence can be called successful retrieval

Location: `evidence_experiment/runner.py`, `extract_one`, `_rendered_lines` and `_reconstruction_check`.

A synthetic Joern result `List(999)` for a four-line source returns:

```json
{"status": "ok", "slice_lines": [999], "rendered_lines": [], "slice_code": ""}
```

The renderer drops invalid coordinates; both reconstruction comparisons then agree on an empty string. `rq1_report.py` counts status `ok` as a retrieved nonempty excerpt, so retrieval reporting becomes incorrect and an empty packet can be issued. Mixed valid/invalid coordinates are also silently filtered during reconstruction.

**Required action:** validate coordinates before accepting extraction, require a nonempty rendered excerpt, preserve the original returned line set/trace, and record an explicit mapping/no-evidence outcome. Predeclare how an unresolved mapping is scored; do not silently infer that an invalid coordinate refers to another source line. Add regression cases for all-invalid, mixed-invalid, zero and valid coordinates. This can be repaired in the experiment wrapper without silently modifying the frozen core renderer.

### R03 — orphan outputs can be adopted as a new run

Location: `evidence_experiment/locks.py`, `lock_inputs` / `write_stage_receipt`; `runner.py`, `generate_queries`.

In an isolated negative fixture, six pre-existing query rows for the canonical development run were placed in a directory with no experiment lock or stage receipts. The code created a fresh lock; query generation saw no pending IDs, made **no model-loader call**, and a new query receipt was written. No query-session record existed. The fixture deliberately used false provenance tags to test the guard; those records were temporary tests and were never stored as real study data.

This exposes accidental partial-restore or mixed-run risks. A run ID binds case/arm/repeat/source, not the generating configuration or runtime.

**Required action:** reject acquisition directories containing stage outputs without their original matching lock/provenance. Preserve the normal fresh directory containing only validated witnesses. Require retained model-session metadata for real Q collection and validate expected IDs/status fields before issuing a receipt. Do not create a new provenance claim merely because an existing file can be hashed.

### R04 — selector capability and development freeze are different checks

Location: `rq1/setup.py`, `doctor`, `_probe_joern` and `freeze`.

The real laptop check proves import and `cpg.method.name("main").size`. It does not exercise generated-query binding, interacters, backward slicing or reconstruction together.

A separate synthetic gate fixture containing six `slice_exec` failures, zero excerpts and no Q-session file was accepted by `freeze` once its current required files/receipts were present. The infrastructure exclusion list blocks transport, timeout, unknown and reset failures, but not the fixed helper compilation statuses. This test used mocked metadata in a temporary directory. It does **not** show that the actual Joern helper has failed.

**Required action:** add a distinct, known-good synthetic full-selector conformance test on the pinned Joern image and retain its receipt. Verify that successful real Q-session metadata exists. Diagnose universal fixed-helper failures before allowing freeze.

Do **not** impose an adequacy, parse-rate or minimum successful-excerpt threshold on the dissertation sample. Legitimate model misses remain results. A capability fixture should establish that the implementation can execute its own fixed operations, independently of the empirical cases. A `context_exec` error can also originate in a Q-generated value of the wrong type, so blanket recoding of all such errors as infrastructure would be inappropriate.

### R05 — the enforced query environment is incomplete

Location: `evidence_experiment/locks.py`, `QUERY_PACKAGES` and main admission in `rq1/setup.py`.

The enforced query package tuple contains only `vllm`, `torch` and `transformers`. It omits `jinja2`, `tokenizers`, `huggingface-hub` and `numpy`; Python is recorded but not compared as part of the stage environment. The earlier real missing-Jinja failure demonstrates that formatting dependencies matter. Capturing a full `pip freeze` is valuable evidence but is not the same as enforcing replay of that environment.

**Required action:** retain a replayable per-stage dependency lock, include the prompt/tokenizer dependencies and Python in the accepted query environment, and record CUDA/driver/device metadata. Preserve separate GPU-query and CPU-slice locks. Do not require the laptop's NumPy/Python packages to match the GPU's packages across different stages.

The inspected vLLM 0.6.6.post1 implementation inherits the model revision when `tokenizer_revision` is unspecified. Thus the absence of a separate tokenizer revision argument is **not** a confirmed revision-drift bug here. That distinction was checked against versioned source.

### R06 — assessment forms need stricter validation

Location: `evidence_experiment/analysis.py`, `_assessments` and `analyze`; `rq1/setup.py`, `freeze`.

The current reader accepted two ratings with `assessed_utc: null`. It also accepted an adjudication whose `case_id` was `MISSPELLED_CASE`; the foreign row was ignored when outcomes were assembled. Missing matches default to uncertain, which can conceal a data-entry omission.

**Required action:** require actual timezone-aware timestamps, reject future/invalid timestamps, validate case/packet pairs, and require an explicit match decision or reasoned uncertainty for every shown U packet. Require the declared assessment fields and preserve initial/final provenance. Validate the initial-pass provenance and same-assessor identity consistently. Continue to allow justified uncertainty; completeness checks must not force a confident judgement.

### R07 — delayed consistency is separate from the report

Location: `rq1/assess.py`, `consistency`; `evidence_experiment/rq1_report.py`.

The consistency tool correctly selects a seeded 25% subset and records whether the actual delay reached 48 hours. The primary report does not read `consistency.json` or clearly mark that mandatory check pending. A report can therefore be emitted before that part of the protocol is complete.

**Required action:** join the delayed-check summary into the readable report and provenance, reporting selected/completed packet counts, actual delays, agreement and missing/short-delay status. Add an explicit study-completion check. Initial analysis can remain provisional while waiting; no independent-review claim should be introduced.

### R08 — GitHub CI was failing on missing history

The current branch's [CI run](https://github.com/TheArchiviste/MSc-Thesis-Project/actions/runs/40962342742) ended with **7 failed, 92 passed**. Logs show `actions/checkout` using `fetch-depth: 1`, followed by provenance failures because the historical pipeline commit was unavailable. Local full-clone tests pass.

**Correction made and verified in this audit:** `.github/workflows/ci.yml` now explicitly uses `fetch-depth: 0`. No provenance guard was weakened. The corrected workflow passed in [CI run 40973956155](https://github.com/TheArchiviste/MSc-Thesis-Project/actions/runs/40973956155), on commit `61752db6f9e2f3e601c7147d78e8a602cd777d96`. That remote result is separate from the passing local test suite. Green CI does not resolve the additional negative-fixture findings above.

### R09 — preserve the query command's exit status

Location: the `query ... 2>&1 | tee ...` examples in `rq1/RUNBOOK.md` and `docs/NEBIUS_RQ1_GUIDE.md`.

Without `pipefail`, a failed Python process can leave a pipeline exit status of zero because `tee` succeeded. Completion counts would still block main freeze, but an operator could mistake a failed paid session for successful collection.

**Required action:** use a shell with `set -o pipefail`, capture the actual phase exit code, retain partial outputs and logs, and print a success marker only after validating all expected terminal IDs. Keep model-load failures separate from legitimate per-input model outcomes. Query load errors must leave uncollected inputs pending.

### R10 — operational status documentation

The earlier RQ1 readiness/runbook text still describes token auditing as pending and says no GPU has been rented. Later user evidence has superseded those statements. The Nebius guide now links this audit and marks Q collection on hold. Its installation commands are labelled historical setup instructions; they must not be used to bypass the hold.

The dated corpus documents were not edited during this audit because they participate in the accepted corpus hash. Refresh them alongside the necessary implementation changes and then repeat the CPU token audit once, avoiding repeated contract churn.

## Strategy checks that remain appropriate

- One primary U run per case and a separate F control match the narrowed RQ1. F never enters the U adequacy denominator.
- One representative per generator block avoids counting stack/heap generator twins as independent units.
- Terminal no-evidence outcomes stay in the enrolled denominator, with failure status retained. Pending work is not converted into a scientific failure.
- Rendered-line overlap remains descriptive; it does not establish the necessary value, pointer or guard relationships.
- The A/N point outcome and unresolved-outcome identification bounds are appropriate descriptive summaries for this small source-selected case study. They are not population confidence intervals.
- The initial F assessment is preserved separately from source-matched corrections. Report the shown F denominator and the number of unique packets.
- AI-assisted single-assessor judgement, source familiarity and related excerpts must remain explicit limitations. No independent human validation is established.
- A mandatory 48-hour delayed check needs calendar time, not GPU time. Keep the rented GPU stopped during local slicing, assessment and writing.

Legacy calibration/three-RQ code remains in the repository. This audit does not certify that it implements the earlier broader strategy; it is excluded from the intended RQ1 execution path.

## Concrete order for resuming safely

1. **Keep paid collection paused.** Retain the VM/disk, installed environment, transfer archive and all logs. Confirm the VM is Stopped in the console.
2. **Resolve implementation identity.** Record the selected release/paper/fork contract and its explicit deviations before collecting any Q outputs. Preserve the current snapshot for comparison.
3. **Repair collection safeguards locally.** Address R02/R03/R04 and complete the per-stage environment contract. Add meaningful regression tests reproducing each observed defect. Update the log/exit-status handling.
4. **Repair assessment/report checks in the same source revision.** Address R06/R07, update the dated operational documents, and run the full suite/lint/compilation/source verification. Confirm remote CI is green after the full-history checkout correction.
5. **Refresh the CPU audit once for the final source contract.** Re-run witnesses only if sources, support, witness plans or their execution contract changed. Re-run token auditing after prompt, settings or hashed-code/document changes. Preserve the previous audit and use a new data directory where acquisition fingerprints change.
6. **Prove the complete selector on the laptop CPU.** Use a clearly labelled synthetic fixture, bounded RPC/case budgets and the inspected Joern digest. Check fresh/reused worker behaviour and reject invalid source coordinates. This is a software capability test, not an RQ1 outcome.
7. **Prepare the remote checkout while stopped where possible.** Assemble the corrected source/config/lock/audit/witness transfer locally. On restart, re-read the dynamic public IP, verify remote archive checksums and source pin, restore the accepted GPU environment, then run the full GPU doctor. Keep the old input archive as provenance; do not silently overwrite an acquired run.
8. **Run only the development collection.** The model's actual load and memory fit remain empirical checks. Collect exactly six terminal Q records, then slice on the laptop, assess the complete issued queue and review the traces. Save any model-load errors without creating fake outcomes or selectively regenerating malformed outputs.
9. **Freeze before main.** The accepted source, rubric, maps, prompt/runtime, budgets, environment, token audit and complete development evidence must match. Main then contains exactly 24 planned Q/slice inputs for 12 U/F cases.
10. **Finish assessment and reporting.** Complete the delayed consistency check, preserve initial/final/matching records, report A + I + uncertain = 12, separate F results and failure counts, and archive the exact sources and raw records. No D or retraining is required.

Changing only this report, the operational Nebius guide and the CI checkout leaves the accepted corpus/token contract intact. The proposed experiment-code repairs will require a new contract audit before execution. No existing dissertation outcome needs to be discarded because none has been collected.

## Evidence files

Machine-readable audit evidence is in [audits/2026-10-29/checks.json](audits/2026-10-29/checks.json) and [audits/2026-10-29/probe-results.json](audits/2026-10-29/probe-results.json). The latter contains deliberately synthetic negative fixtures, including the temporary freeze-admission test. These files contain no real model generations or adequacy judgements.

The local audit workspace retains test output, fresh compiler/ASan logs, shell checks and the inspected reference source objects under `work/readiness-audit-20261029/`. That directory is separate from `work/rq1/development` and `work/rq1/main` and must never be imported as experimental acquisition data.
