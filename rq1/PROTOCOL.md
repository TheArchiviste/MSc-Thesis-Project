# RQ1 baseline evidence protocol

Implementation **rq1-v3**, revised 30 October 2026. This supersedes the v2 measurement rules before any main Q outputs. Earlier outputs are preserved. No RQ2/RQ3 experiment is included.

The 5 October literature review states RQ1: “How well do selected slices from original programs represent externally supported mechanism elements and their context, and when do they supply enough information for an independent, justified vulnerability assessment?”

The operational task is **claim-conditioned justification of the documented flaw along the selected `case_entry` path**. A candidate flaw class and operation are supplied uniformly, without sizes or a causal explanation. They are hypotheses, not evidence. We assess sufficiency independently of the evaluated Q and without a target classifier. We do not measure unrestricted vulnerability discovery, global program safety, or independently human-validated accuracy. The reference and support audit are AI-assisted; the stateless grader sees only one excerpt and the public task. This is the specific independence boundary, not a claim that AI-generated reference judgments are independent annotations.

## Population and unit

Juliet is pinned at `f88433e3443648a17671398797a04ea1f8e1a274`. The frame contains 38 C `_41` families in 20 related generator blocks. Selection uses seed `20261027`. Development reserves CWE131-copy, CWE129 and CWE193-copy. Of the remaining 17 blocks, two `sizeof` blocks are excluded by source/LP64 reasoning; 12 are enrolled, and three remain unused reserves. No related block crosses splits. This is a curated case study, not a probability sample of production vulnerabilities.

Each case has original vulnerable U and documented repaired F. Run Q and Joern once per input, repeat 0: 6 development and 24 main runs. The primary denominator is the 12 main U cases. F, development and calibration remain separate. Main contains ten stack-write and two heap-write mechanisms; no balanced storage comparison is claimed.

Do not drop, replace or top up a case after seeing its outputs. Large slices and genuine misses remain findings. Any necessary apparatus/protocol correction after freezing needs a versioned deviation, preserved prior records and consistent affected reruns.

## Ground truth and assumptions

Prepared sources remove comment/identifier cues while retaining source statements and exact upstream maps. The reference records granular facts, their roles and required causal relationships. Source inspection is independent of Q outputs. Witnesses and Juliet documentation externally support the reference; they do not make the AI annotation independently validated.

Distinguish actual from formal arguments. Some callers supply a source pointer, some a destination pointer, and D02 supplies an index scalar. Macro definitions, initialization, termination and alias selection are separate facts. For R13, the explicit `memcpy` count supplies the 100-byte extent, not source initialization. A fact's line being present does not prove its value or relationship.

Public assumptions: Linux LP64 (`char=1`, `int=4`, pointer/long=8 bytes), reachability of the selected entry and successful allocation, standard C library semantics, and Juliet `ALLOCA` stack allocation. These supply no hidden capacity, source length, alias, guard, macro value or caller binding. An arbitrary external caller or conditional warning about an unknown long input cannot establish the documented entry-path flaw.

Every U must compile and produce the predeclared ASan class on its finite witness; F must compile, run cleanly on that witness and repair the mechanism by source reasoning. D02 also has a benign witness. Other U paths unconditionally reach the invalid access, so their benign check is not applicable. Retain compiler, flags, inputs, stdout/stderr, exit status, source and witness-plan hashes. Finite tests do not prove all-input safety. Witness-only headers/driver are outside Q/Joern inputs.

## Instrument calibration and grading

See [ASSESSMENT.md](ASSESSMENT.md) for the exact boundary and commands. Before any Q acquisition, calibrate on **12 dev-only source anchors**: complete U, complete F, reduced sufficient U, and deliberately incomplete views for each of the three development cases. This gives 6 adequate and 6 inadequate anchors. Incomplete anchors omit all U/F-discriminating lines and are byte-identical under either source. Calibration is independent of Q retrieval, so failed F retrieval cannot erase its negative anchors.

Send one public packet per stateless API request, never the private key, source bank, sibling outputs or earlier conversation. Record actual provider, requested/reported model, revision availability, sampling, timestamps, exact messages and raw response. Freeze the same identity/settings for initial and delayed grading. Require all 12 predeclared labels and their later AI source-proof audits to pass. This small instrument screen is not an estimate of population accuracy. Failure remains recorded; do not regenerate a preferred answer or tune on main.

| Decision | Meaning for an actual shown excerpt |
|---|---|
| Adequate | Visible premises and permitted assumptions justify capacity, extent, binding and violation, with citations and causal relationships. Valid alternative sufficient accounts are accepted. |
| Inadequate | A necessary premise is absent or contradicted and no supported alternative suffices. Unknown omitted facts do not rescue an insufficient excerpt. |
| Uncertain | A specific interpretation/adjudication issue cannot be resolved confidently; explain it. |

Grade the exact rendered excerpt, including the fixed enclosing-block reconstruction. Packet IDs bind claim, code and rubric/assumptions. Identical units share one initial judgment. A seeded order spaces sibling packets where possible and reports collisions; label concealment is limited by code and sibling recognition.

The **first excerpt-only grade** is immutable. Then the assistant audits U correspondence to the documented mechanism and support for every required relationship, using references but citing only visible proof or allowed assumptions. The audit can reject an unsupported adequate claim; it cannot promote an initial inadequate/uncertain grade. No reference line checklist substitutes for semantic reasoning. Alternative supported accounts are explicitly recorded.

Optional source-informed corrections are secondary: retain real timestamps, actual assessor metadata, visible proof and a revision reason in a separate file. Report transitions and preserve the original primary result. F false adequacy uses initial grades among F excerpts actually shown; zero shown is not estimable, not a pass.

For main, freeze a seeded 25% of unique shown U/F packets, rounded up (at most six), for a second stateless pass at least 48 hours after their actual initial grading. Same model/settings, real timestamps and raw provenance are required. This measures within-assessor consistency, not correctness or independence. No repeated Q runs are required.

## Acquisition and freeze

Use original Q at the revision/settings in [REFERENCE_CONTRACT.md](REFERENCE_CONTRACT.md). On CPU audit all 30 complete prompts with its pinned tokenizer/template, without truncation. Inputs exceeding context remain explicit no-evidence outcomes. Read the running Joern OCI digest. Test the full selector on local and interprocedural/macro fixtures, plus structural import/caller mapping/reset on all 30 actual sources. These apparatus checks do not require main evidence coverage or preview its adequacy.

Require clean committed code, current source/implementation/CPU receipts and accepted calibration before Q generation. Keep Q on the H100 and slicing on laptop CPU, with complete environments locked separately. After real development queries, slices and source-audited grades, freeze code/corpus, policy, calibration, tool receipts and stage environments before main. Development has no adequacy-rate cutoff. It can be accepted before its delayed check; unresolved infrastructure/mapping must be repaired, preserving attempts.

Joern budgets: 120 seconds per RPC, 600 seconds per case, plus cleanup; three total infrastructure attempts per input. Save and pause after transport, timeout or reset failure. Every input/retry starts a fresh Docker/Scala process. Resume the identical command; never retry a valid semantic miss for a better answer. Q load/device failures leave inputs pending. Unknown failures need inspection. Invalid coordinates and unresolved infrastructure are acquisition uncertainty, separate from judgment uncertainty. Logs locate observed discrepancies without claiming a unique causal explanation.

## Reporting

Let N be all enrolled U, R usable U excerpts and A confirmed primary adequate cases. Report **adequate retrieval yield A/N** and **conditional adequacy A/R**, with R=0 not estimable. No usable excerpt is an acquisition outcome, not a grader-rejected packet. Keep terminal semantic misses, unresolved acquisition, and unresolved assessment distinct. Overall identification bounds are `[A/N, (A+K_acquisition+K_assessment)/N]`; conditional bounds use only assessment uncertainty among R. These are not confidence intervals.

Report exact counts, source correspondence, excerpt size, selected/context-only/absent facts, and supported/missing/contradicted/uncertain relationships. One/two changed main judgments shift yield by 8.33/16.67 percentage points. No inferential prevalence claim is made.

Outputs are `rq1_report.md`, `rq1_cases.csv`, `rq1_element_visibility.csv`, `rq1_relationship_support.csv`, `rq1_grade_changes.csv` and `analysis.json`. Main remains provisional until delayed consistency is complete. Archive every raw stage, response, source audit, environment, receipt and prior attempt. The small synthetic corpus, AI-assisted annotation, model familiarity and limited blinding constrain the dissertation's claims.
