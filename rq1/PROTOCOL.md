# RQ1 baseline evidence protocol — v7 / assessor v3

The [30 October v3 amendment](../docs/RQ1_V3_AMENDMENT_2026-10-30.md) is the authoritative pre-run revision after the preserved v1/v2 calibration failures. It records the changed interface, candidate, anchors and separation of acquisition from assessment. No main outcomes informed these decisions.

RQ1: “How well do selected slices from original programs represent externally supported mechanism elements and their context, and when do they supply enough information for an independent, justified vulnerability assessment?”

The operational task is **claim-conditioned justification of the documented flaw along the selected case_entry path**. A hypothesis names the flaw class and operation uniformly, without sizes or a causal explanation. The stateless assessor sees one numbered excerpt and the public task. This measures neither unrestricted discovery nor global safety. References and source audits are AI-assisted; operational separation from Q and private source information does not establish independent human annotation or independent training data.

## Population and source support

Juliet is pinned at f88433e3443648a17671398797a04ea1f8e1a274. The census has 38 families in 20 related blocks. Seed 20261027 reserves three development blocks; two sizeof blocks are excluded for LP64 validity, twelve blocks remain the unchanged main sample, two former reserves become assessor-only response checks, and one remains unused. No block crosses these splits. This is a curated case study, not a production-vulnerability probability sample.

Each development/main case has U and repaired F. One primary run gives six development and twenty-four main Q/slice inputs. Main has twelve U in its primary denominator; F and calibration are separate. R15/R17 receive source witnesses and assessor anchors only, not experimental Q queries. Main has ten stack-write and two heap-write mechanisms; no balanced storage comparison is claimed. Do not drop, replace or top up cases after outcomes.

Prepared C removes identifier/comment cues while retaining exact upstream line maps. All thirty experiment C inputs and original Q/selector/reconstruction settings are unchanged by v3. The reference separates value-supplying facts, caller/formal/alias bindings, loop/input dependencies and causal relationships. A line hit is visibility, not proof. Each U must compile and trigger its predeclared ASan class; F must compile, run cleanly on that finite witness and repair the mechanism by source reasoning. D02 also has a benign input. Finite tests do not prove all-input safety.

Public assumptions: Linux LP64, selected entry reachability and successful allocation, standard C library semantics and the Juliet ALLOCA helper. These supply no hidden capacity, macro value, string length, alias, guard or caller binding. A warning conditional on arbitrary unknown input does not justify the documented entry-path flaw. Source-only key/referent material never enters first grading.

## Assessment instrument

One candidate: GPT-6 Astra via stateless Responses API, high reasoning, 25,000 output-token allowance including reasoning, Standard tier, no temperature parameter, no tools or previous-response state. Identity/settings, exact messages/schema order, execution timestamps, raw envelopes, token usage and profile hashes are retained. The model's suitability and API access must be established through the declared checkpoints; the API ID is not a verified immutable weight snapshot.

One rubric, readable source, evidence before verdict, and a provider-compatible constrained schema replace duplicated sorted JSON. The local validator retains full proof/citation/uniqueness/conditional rules. Require source citations supplying quantities and dependencies, arithmetic and binding explanations. Accept supported alternative accounts rather than an exact line checklist. Refusal, truncation, malformed content and substantive errors remain distinct recorded failures; no automatic content repair or preferred-answer retry.

Twenty calibration anchors comprise twelve reused-development packets and eight fresh response checks from two previously unused blocks. Each source yields complete U, complete F, a source-checked essential-fact view rendered through production context_lines, and an identical-under-U/F incomplete stress control. The latter is post-render masking; it is not claimed to be a natural Joern output. D02's production renderer restores its guard. Freeze both cohorts and all settings before any v3 response; do not tune between them. Require all twenty valid labels and later source-proof audits. Report both cohorts and source-case patterns, not independent-trial population accuracy. Reuse history and remaining snprintf/strncat-specific calibration gaps are explicit limitations.

Adequate means visible premises and assumptions justify this flaw, with capacity, extent, binding and violation support. Inadequate means a necessary premise is absent/contradicted without a sufficient alternative. Uncertain means a specific interpretation cannot be resolved; explain it. A correct label with false reasoning fails calibration.

The first excerpt-only grade is immutable. The later U source audit can reject unsupported sufficiency but cannot promote an initial inadequate/uncertain judgment using source knowledge. Optional reference-informed corrections remain secondary. F false adequacy is computed only among F excerpts actually shown; zero shown is not estimable. Identical packets share judgments. Seeded spacing reduces sibling adjacency where possible; code familiarity and imperfect label blinding remain limitations.

## Acquisition, seals and release

Freeze the actual CPU apparatus, Q profile, source/reference inputs and stage-specific acquisition contract before Q. Q uses the pinned original checkpoint, BF16, seed zero, temperature zero, top-p one, batch one, 8192 context and 2048 output allowance, without source truncation. Check all thirty prompts and real selector fixtures/graphs on laptop CPU. Use H100 for Q and CPU for Joern, with complete stage package environments locked separately.

Collect query/slice outputs sealed while assessor validation is pending. Never feed outputs back into assessor development. Main collection must preserve the development stage environment; unresolved development slicing infrastructure/mapping blocks main slicing. Capture native/Python logs privately and return only safe counts and committed archive hashes. Seals detect alteration, not access. Declare accidental/diagnostic exposure honestly. Q/Joern receipt fingerprints exclude calibration and judging code; shared acquisition changes still require a versioned deviation and preserved history.

Accept calibration before releasing development. Grade its real excerpts and complete source audits, then freeze assessment code/profile, calibration and the development report. No adequate-rate cutoff applies. Main release additionally requires this freeze. Main may have been collected earlier while sealed; its content remains unavailable for instrument decisions until release.

RPC/case budgets remain 120/600 seconds with three total infrastructure attempts, each in a fresh Docker/Scala worker. Infrastructure failures pause for diagnosis. Semantic misses remain terminal; Q device/load failures leave pending inputs. Preserve all attempts and distinguish unresolved acquisition from judgment uncertainty.

## Reporting and completion

Deterministic structural reporting is available without grades: sizes, selected/context/absent reference lines, partial versus complete line groups and visibility of listed relationship prerequisites. These do not establish semantic relationship support or validate the reference. Structural results can be computed sealed without being inspected during assessor development.

For enrolled U N=12, usable excerpts R and source-confirmed primary adequate A, report yield A/N and conditional adequacy A/R; R=0 is not estimable. No usable excerpt is an acquisition outcome, not a grader-rejected packet. Report acquisition/assessment uncertainty separately. Identification bounds [A/N, (A+K_acquisition+K_assessment)/N] describe unresolved cases, not confidence intervals. One/two changed primary judgments move yield by 8.33/16.67 percentage points.

Freeze a seeded 25% of unique main U/F packets, rounded up to at most six, for another stateless grade at least 48 actual hours later using identical settings/identity. It measures within-assessor consistency, not correctness. No repeated Q runs. Main remains provisional until completion or explicit not-applicable status when no excerpts were shown.

Preserve raw evidence, references/maps, source witnesses, Git/version contracts, both freezes, seals, stage environments, initial grades, source audits, delayed records and all failed calibration attempts. The final dissertation must state the curated synthetic scope, small correlated anchor set, AI-only validation, model familiarity, remaining mechanism/operation gaps and hosted-model reproducibility limitations. No RQ2/RQ3 experiment or D classifier is included.
