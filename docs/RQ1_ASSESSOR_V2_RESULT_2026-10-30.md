# Second assessor calibration: failed; pause before Q

The one predeclared rq1-excerpt-v2 attempt **failed calibration**. The H100 successfully served the pinned Qwen2.5-32B-Instruct checkpoint, returned all twelve responses and stopped its owned server processes. Hardware readiness passed; the assessment instrument did not. No real Q generation, experiment slices or main results have been collected.

This records the actual session at clean main commit `91a2280d92bb6b921dddecb6930bc0dcba6905c5`, from 16:20:04 to 16:32:09 UTC on 30 October 2026, approximately twelve minutes. Model readiness was recorded at 16:29:39. Startup did not exceed its thirty-minute limit. The cloud VM's power state was not observed; the user must keep it stopped in the Nebius console while this failure is reviewed.

## Verified result

| Check | Observation |
|---|---|
| Archive SHA256 and complete export manifest | Pass; all fifteen listed members plus the manifest verified |
| Scientific core, packets and exact requests | Match the accepted v6 CPU inputs and current contract |
| VM preflight and complete software environment | Match the accepted inspection and the acquisition session |
| Model, pinned revision and sampling | Match the frozen BF16 plan; twelve separate two-message requests |
| Responses | 12/12, all with finish reason `stop` |
| Parseable JSON | 12/12 |
| Individually passing the existing strict response validator | 8/12 |
| Complete imported assessment set | None; import is atomic and failed |
| Verbatim declared labels matching the key | 9/12, diagnostic only |
| Accepted calibration | No |
| Owned server shutdown | Confirmed by the runner; cloud VM shutdown is separate |

The nine matching labels are a development diagnostic, not accepted grades or a population accuracy estimate. Reusing the same development anchors after the v1 repair also limits interpretation. Full acceptance still requires twelve valid responses, twelve correct labels and twelve supported source proofs. The [machine-readable audit](audits/2026-10-30-assessor-v2-result/evaluation.json) records each response's hash, real assessment/audit times, required-field omissions, strict validation result, source citations and reasoning. No content was repaired, regraded or imported as a partial set.

The original import error reproduced locally against the unmodified files:

```text
ValueError: Explain each assessment from the visible excerpt
```

Three D02 responses omit the required top-level `explanation`: complete U, reduced sufficient U and incomplete. The D03 reduced response omits both `missing_context` and `limitations`. All twelve use lowercase labels and integer citations, so those particular v1 interface failures were resolved. The v2 task explicitly requires the remaining fields; their absence is a model compliance failure. These omissions cannot explain away the substantive errors below.

## Source audit of all twelve responses

“Supported” below describes diagnostic reasoning support, not acceptance of a malformed grade. “Partial” means a required fact is uncited or an additional execution claim is unsupported. A correct label with an incorrect explanation does not pass the proof screen.

| Case / excerpt | Expected → declared label | Strict response | Source reasoning |
|---|---|---|---|
| D01 complete U | adequate → inadequate | Valid | Unsupported: interprets `ALLOCA(10)` as ten integers rather than ten bytes |
| D01 complete F | inadequate → inadequate | Valid | Supported: forty-byte allocation and forty-byte copy fit |
| D01 reduced U | adequate → inadequate | Valid | Unsupported: repeats the allocation error and calls visible size information missing |
| D01 incomplete | inadequate → inadequate | Valid | Partial: missing capacity is real, but it also assumes no assignment occurs in the gap |
| D02 complete U | adequate → adequate | Missing explanation | Structured argument supports an admitted out-of-bounds index |
| D02 complete F | inadequate → inadequate | Valid | Unsupported: claims the type/constraint is missing despite visible declarations and upper-bound guard |
| D02 reduced U | adequate → adequate | Missing explanation | Structured argument supports an admitted out-of-bounds index |
| D02 incomplete | inadequate → adequate | Missing explanation | Unsupported: assumes the omitted guard permits the violating input |
| D03 complete U | adequate → adequate | Valid | Partial: asserts actual string length from array size without citing the supplying macro |
| D03 complete F | inadequate → inadequate | Valid | Partial: correct intended comparison, same unsupported string-length inference |
| D03 reduced U | adequate → adequate | Missing two fields | Partial: same string-length citation gap |
| D03 incomplete | inadequate → inadequate | Valid | Supported: identifies the missing choice between the ten- and eleven-byte buffers |

D01 is decisive even if all formatting issues were resolved. `ALLOCA(10)` allocates ten bytes; casting its result to `int *` does not enlarge the allocation. The visible copy requests `10*sizeof(int)`, forty bytes under the declared LP64 assumptions. Both adequate D01 anchors are therefore wrongly rejected.

D02 incomplete is also decisive: its omitted guard could be the repaired `data >= 0 && data < 10`. The excerpt is identical under U and F. Seeing input acquisition and `buffer[data]` does not show that an invalid index passes the missing guard. Conversely, the full U and reduced U do show the nonnegative-only guard; a value such as 11 is permitted by visible acquisition and violates the ten-int object's bounds. Their structured reasoning supports that account, although both omit a mandatory field.

D02 F illustrates why label matching is insufficient. Its response says `data` has no visible type and no clear input constraint. The entry declares `int data`, the sink accepts an int, and the upper-bound guard precedes the write. Its rejection label agrees with the key for the wrong stated reasons.

For D03, an eleven-byte array declaration does not by itself prove an eleven-byte string copy. The visible `SRC_STRING` definition supplies ten characters plus NUL. The three complete/reduced length accounts fail to cite that supplying line. The audit records this as partial support, without claiming the excerpt lacks the definition or requiring proof of unrelated program safety. The complete U response does cite the selected object and actual call binding. The incomplete response correctly declines to invent the missing alias assignment.

## Next action and boundary

Keep the VM stopped. Preserve the v1 and v2 archives, raw responses, cached weights and accepted CPU evidence. There is no laptop command to run now, and no additional CPU scan is needed for this documentation update.

The frozen protocol explicitly says: “If this v2 attempt fails, preserve it and pause for an explicit instrument/design decision; no automatic further prompt/model search is part of this revision.” See [PROTOCOL.md](../rq1/PROTOCOL.md). This result reaches that stopping condition. No v3 revision, new model download, paid request, threshold change or Q run has been started.

The recommendation is a separately declared replacement assessor rather than another wording-only retry of this candidate. Its task must retain excerpt-only isolation, exact source coordinates, the current proof obligations and all-twelve acceptance rule. Schema enforcement should prevent omitted fields, but it cannot fix the demonstrated allocation/guard reasoning errors. A replacement's model identity, revision availability, execution route, schema support, cost and any context limit must be checked before a new command is issued. Preserve the development history; further reuse of these anchors must be disclosed and cannot serve as independent evidence of general grading accuracy.

If no acceptable assessor is available, any fallback to source-informed descriptive coverage must be an explicit change in dissertation claims: those measurements alone do not establish the full RQ1 sufficiency judgment. Do not silently bypass the calibration gate or substitute this source-informed audit for a fresh excerpt-only first assessment.

## Evidence identity

The supplied archive was `rq1-assessor-calibration-20261030T162004Z-1937.tgz`.

```text
archive SHA256:
bee6292a8b75243df6b255e7c867f538ec3020b0316c74b9033b8ca0a52acb6b
raw responses SHA256:
7fbf60af17c446b5fd5e4d0aa67ede08924cf719b1eb77fc506cc68590a34771
public requests SHA256:
3e732ece3b0ffeb77d0e122c0bd42c4c4c0e911da762e80cbfdfd6ab64d4ad36
```

The response content was read only by this later source audit. Actual grader requests contain the fixed rubric and one public numbered excerpt; they exclude the private key, source referents, sibling packets and prior answers. The session used the same checkpoint/settings as v1. The recorded shutdown warnings follow the intentional interrupt; the runner retained the primary import error and confirmed no live owned process-group workers remained. Neither those warnings nor the previous v1 shutdown uncertainty change the v2 calibration result.
