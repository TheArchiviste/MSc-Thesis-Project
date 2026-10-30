> Historical v3 methodology change record. The current implementation adds the [v4 Joern compatibility repair](RQ1_JOERN_FIX_2026-10-30.md) without changing these scientific rules.

# RQ1 v3 methodology implementation — 30 October 2026

This revision applies the RQ1-only methodology evaluation before any real Q acquisition. It keeps the original Q, CPU Joern, 3 development/12 main disjoint blocks, one U/F run per case and finite source witnesses. No D, classifier, transformation or robustness experiment is added.

| Methodological issue | Implemented correction |
|---|---|
| R13 extent attributed to initialization | Explicit `memcpy(...,100*sizeof(char))` count is the extent fact. |
| Generic caller/object relation | Separate actual/formal facts and source-pointer, destination-pointer or scalar-index binding; alias, macro, initialization and termination facts are distinct. |
| Hidden source knowledge in grading | Public versioned task; exactly one excerpt per stateless request; no oracle/history/siblings. Actual provider/model/settings, exact messages, raw responses and real timestamps retained. |
| Weak discriminability check | 12 dev-only anchors: complete U/F, reduced sufficient U, and indistinguishable incomplete views; balanced 6/6. Require every predeclared label plus later source-proof audit. No Q retrieval dependency. |
| Later corrections promoted to primary | Primary is the immutable first excerpt-only grade conservatively confirmed by source support. Reference-informed corrections remain separate, with reasons and a transition table. |
| Line hits mistaken for semantic recall | Granular selected/context-only/absent visibility and separate relationship support; no semantic recall label. |
| Denominator ambiguity | Report A/N retrieval yield, A/R conditional sufficiency, no-excerpt reasons, and separate acquisition/assessment uncertainty. Zero shown denominators are not estimable. |
| Narrow Joern smoke | Full local and interprocedural/macro selector fixtures plus structural imports/caller mapping/reset for all 30 source inputs. No main adequacy/fact-coverage gate. |
| Assessment consistency overclaimed | Same calibrated identity/settings, seeded 25% subset, real ≥48-hour timestamps and separate second response provenance; within-assessor consistency only. |
| Stale work mixing | New `rq1-v3` contract, run IDs and work directory; old records preserved. Clean committed code and current receipts required. |

The 12 source anchors have an AI-assisted source answer key. Witnesses/Juliet supply external support; neither the key nor the later support audit is independent human annotation. Stateless grading limits provided context, not model pretraining or sibling recognition. The dissertation must state these limitations.

Software validation covers malformed/foreign responses, hidden request fields, actual identity/settings, altered provenance, missing proof audits, all-reject calibration, source-support failures despite line hits, no primary promotion, zero denominators, delayed deadlines/model drift, corpus identity, selector/parser failures, lock/environment drift and old command rejection. All simulations are confined to pytest temporary directories.

Real CPU preparation rechecks the 30 C inputs with GCC/ASan and audits 30 prompts using the pinned small tokenizer. These are apparatus/source checks, not evidence-adequacy observations. See retained raw records under `docs/audits/2026-10-30-v3`. Actual laptop Docker conformance and real assessor calibration remain pending. No Q weights or paid GPU execution were used for this revision.

Execute only [runbook checkpoint 1](../rq1/RUNBOOK.md), return its D: diagnostic ZIP and pause. The next checkpoint configures/calibrates an actual assessor service; no endpoint/access or free resource is assumed. Paid Q acquisition follows only after that instrument screen and separate GPU-doctor acceptance.
