# Bounded RQ1 evidence audit

Revised 30 October 2026 for implementation rq1-v2. This execution protocol implements the 27 October RQ1 plan, with AI-assisted assessment following the user's explicit delegation of judgement. It is provisional until the real development run and `freeze` succeed. No main Q/Joern outcome has been inspected.

**Question:** How well do original-program excerpts retrieved by the evaluated LLMxCPG configuration preserve source-grounded mechanism elements and relationships, and how often are they sufficient to justify the documented flaw under a predefined rubric?

Use original pretrained Q and real Joern. D, calibration, transformations and RQ2/RQ3 hypothesis tests are outside this execution. Only RQ1 commands are shipped. Retained failure traces explain observations; they do not establish unique causal stages.

## Corpus and primary unit

Juliet is pinned at `f88433e3443648a17671398797a04ea1f8e1a274`. The source frame is 38 C `_41` families grouped into 20 generator blocks (18 allocation twins and two singleton `sizeof` blocks). `selection.json` retains the deterministic seed `20261027`, ordered block representatives, upstream paths, Git blob identities and LF-normalized SHA256 hashes. This is a source-selected case study, not a probability sample of production vulnerabilities.

Three complete blocks are reserved for development: CWE131-copy, CWE129 and CWE193-copy. Of the other 17, two `sizeof` blocks lack the documented overflow on LP64 and are excluded before inference; the first 12 valid blocks are enrolled; three remain unused reserves. No block crosses development/main. `cluster_id` identifies a block, not an individual allocation family. Upstream CWE labels describe the generator; the actual overflowing object can have a different storage kind. Main currently contains ten stack-write and two heap-write mechanisms, so no balanced storage comparison is claimed.

Each enrolled case has U (vulnerable source) and F (documented repaired counterpart). Main has 12 U + 12 F; development has 3 U + 3 F. Run one primary Q generation and one Joern extraction per input (fixed repeat 0). F never enters the U denominator. No mandatory unchanged-input repetitions are needed for the narrowed RQ1.

Freeze selection, source maps, references, rubric, prompt/runtime settings, timeout/retry policy and token audit after real development and before any main query. Main is blocked until the freeze exists. Do not replace, drop or top up cases after observing main outputs. A necessary protocol repair needs a recorded deviation and consistent affected reruns, preserving earlier records. An unhelpfully large slice is an observation, not a reason to change flow type.

## Sources and reference

`referents.jsonl` is the source-grounded oracle, mirrored in the two manifests. Each record includes the claim, capacity/extent/access/guard/context roles, caller-to-callee and bound relationships, ABI assumptions, provenance and line maps. Generated C removes comments and good/bad/CWE identifier cues; transformations preserve source statements and retain exact upstream coordinates. The executable driver and support code are outside model input. No model-generated reference is presented as an independent annotation.

Permitted common assumptions: LP64 Linux (`char=1`, `int=4`, pointer/long=8), successful allocation, reachability of the selected entry, standard C library semantics, and the documented Juliet `ALLOCA` helper meaning stack allocation on Linux. These assumptions supply no hidden buffer capacity, initializer, alias selection, source length or caller/callee binding. Do not infer an omitted object's capacity from its familiar template.

Every U must compile and produce its predeclared ASan class on the specified witness. Every included F must compile, execute cleanly on that witness, and repair the particular mechanism by source reasoning. D02 also has a benign input. Other sources unconditionally reach the invalid access; their benign U check is explicitly not applicable. Finite witnesses support those executions and do not prove F safe for all programs/inputs. Retain compiler/version, flags, input, stdout/stderr, exit status, source and witness-plan hashes. Compiler flags include `-fno-builtin-memcpy` to keep the ASan interceptor diagnostic stable; model input is unchanged.

## Rubric and assessment

| Decision | Requirement |
|---|---|
| Adequate | The exact visible excerpt plus allowed assumptions supports a justified account of the specific flaw, including necessary value/pointer relationships. Cite visible lines and explain the violation. Alternative valid sufficient accounts are accepted. |
| Inadequate | Necessary information is missing or contradicted and no sufficient alternative is supported; terminal semantic acquisition failures deliver no usable evidence and also count here; unresolved mapping/infrastructure outcomes remain uncertain. |
| Uncertain | Mapping or sufficiency cannot be resolved confidently. Explain the unresolved issue; never force a cleaner proportion. |

Assess the **rendered reconstruction**, after the documented enclosing-block reconstruction. Retain selected lines, rendered lines, exact text and hashes. Line labels add coordinates, never source context. A line-overlap hit is descriptive and can still leave an essential relationship unresolved. Large excerpts are not automatically adequate.

The same AI assistant prepares references and assesses evidence, as delegated by the user. Use one honest identity (`codex_ai_assessor`), record timestamps, cited lines, relationships, allowed assumptions, missing context, limitations and detailed reasons. This is **AI-assisted single-assessor evaluation**, not author-only human grading or independent human validation. No inter-rater agreement is claimed. No independent-assessor mode is shipped.

First issue unchanged, deduplicated claim/excerpt packets with neutral IDs. `rq1.assess prepare` creates a seeded order avoiding adjacent sibling packets where possible and records unavoidable collisions. It emits unassessed forms; it never generates adequacy labels automatically. Assess the excerpt first and save `assessments.initial.jsonl`. In a separate matching pass, compare the proposed explanation against the source reference, preserving reasons in `adjudications.jsonl`. Retain any correction in `assessments.final.jsonl` with an audit trail. Exact identical claim/excerpt units share the initial judgement even when used by multiple cases or arms.

Label concealment has limits: the assistant knows the source corpus, sibling excerpts may be recognisable and code reveals repairs. Do not describe the process as fully blinded. For F, preserve the initial vulnerable-claim decision; false adequacy is reported among F excerpts actually shown, with failed F separately listed. It diagnoses assessment discriminability, not D's false-positive rate.

For main, select a frozen 25% of successful unique U/F packets, rounded up using seed `20261027`, for a second excerpt-only assessment at least 48 hours later. Keep the same assessor identity, retain both passes and report actual delay. `rq1.assess consistency` records short delays explicitly; `finalize` rejects an incomplete or short-delay check. This is within-assessor consistency only; it does not establish correctness or independence. No delayed check has yet taken place.

## Acquisition and failures

Use the content-hashed rq1-v2 implementation in [REFERENCE_CONTRACT.md](REFERENCE_CONTRACT.md), recording its actual Git commit. The QCRI prompt is release-aligned and the selector/renderer adaptations are explicit; the older core is historical lineage only. Q is `QCRI/LLMxCPG-Q` at `1f48ab60420d90277207394f1254d27d3375b07e`. Fixed generation settings: vLLM, temperature 0, batch 1, context 8192, generation allowance 2048, one GPU, memory fraction 0.85. Retain backend-resolved dtype, seed and sampling settings plus installed versions and load/generation times. These settings require a real development load before acceptance; the package stack has imported successfully on the user's H100, but loading Q and its real development generation remain untested.

Audit every complete U/F prompt with the pinned tokenizer and the pinned chat/prompt formatter on CPU. Never truncate sources to fit. Context overflows become explicit no-evidence outcomes. Inspect and record the actual running Joern OCI digest; a placeholder cannot pass acquisition. A real full-selector check on a separate synthetic fixture must pass; a greeting or simple method lookup alone is insufficient. Laptop and GPU deployment paths can differ; semantic configuration and per-stage packages are locked. Existing terminal observations are not regenerated on resume. Output receipts reject edits before downstream stages.

Provisional Joern budgets: 120 seconds per RPC, 600 seconds per case plus up to one RPC budget for cleanup. Allow three infrastructure attempts total per input. A transport failure, timeout or failed cleanup is saved, then collection pauses. Every input and retry starts a fresh Docker/Scala process. Resume the identical command; attempts are capped and retained in `slice_attempts.jsonl`. After the cap, preserve the terminal no-evidence result and restart before proceeding to remaining cases. Do not retry semantic query failures, empty slices or other valid misses for a better result. Q load/device errors stop collection with pending inputs, rather than fabricate outcomes; retain the command log, fix development infrastructure and resume. Unknown failures require inspection, not silent recoding. Invalid source coordinates are mapping failures; those and unresolved infrastructure count as uncertain, with bounds, rather than a semantic no-evidence finding.

Main analysis remains provisional until the required delayed consistency is complete. Development can be structurally accepted and frozen before its delayed check; development adequacy is never a performance cutoff.

## Outputs and interpretation

For N enrolled U cases, report A adequate, I inadequate, U_unc uncertain, with `A + I + U_unc = N`. Primary observed adequacy is `A/N`; unresolved-outcome bounds are `[A/N, (A+U_unc)/N]`. These are identification bounds, not confidence intervals. Acquisition failures remain in N and are reported separately. Also report adequacy conditional on successful retrieval, excerpt size, role-line overlap/missing context and reasoned mechanism correspondence. F and development results remain separate.

`analysis.json` retains machine-readable provenance; `rq1_report.md`, `rq1_cases.csv` and `rq1_element_visibility.csv` make the findings readable. `rq1.setup status` describes pending work without treating unrun stages as scientific failures. `enrollment.csv` and `selection_ledger.jsonl` retain every selection decision. Raw witness checks, queries, traces, packets, assessment passes and freeze metadata belong in the final reproducibility archive.

The dissertation must describe the narrowed baseline audit and its AI-assisted, source-curated limitations. It cannot claim independent human validation, tested transformation robustness, classifier accuracy, production prevalence or answers to RQ2/RQ3. Supervisor acceptance of this reduced contribution has not been established by an experiment script.
