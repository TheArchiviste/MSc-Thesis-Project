# Accepted v7 laptop CPU checkpoint — 30 October 2026

The returned `local-attempt-20261030T202535Z-4iVZhD.zip` completed successfully on the existing D-backed WSL laptop at clean execution commit `c6121b970de16186b2eddf7ab35f04d74fbca0cf`. The acquisition freeze was created at 20:36:45 UTC. Its archive SHA-256 is `b9aa0eb6c471469f2cb1a0ad3f45688d9a098424eb4455e4ceaf2e366c3bdfca`.

The separate offline receipt audit passed. This inspected the returned records and reran their validators against the execution code; it did not rerun the laptop's compiler or Docker apparatus in the assistant workspace.

| Check | Verified result |
|---|---|
| Source witnesses | 17 cases / 34 U/F sources across development, main and assessor-only holdout |
| Raw witness evidence | All builds pass; U triggers match their declared ASan class; F triggers are clean; planned benign checks pass |
| Original Q prompt lengths | 30/30 fit; 413–577 prompt tokens plus the fixed 2,048-token generation allowance within 8,192 |
| Full-selector fixtures | Local and interprocedural/macro fixtures pass with complete stage traces |
| Corpus graph checks | All 30 source imports, method/call/parameter counts, caller coordinates and resets pass |
| Worker isolation | 32 distinct fresh container start records for the two fixtures and 30 graph checks |
| Contracts and freeze | Current code/corpus/policy match; all four freeze-bound file hashes match |
| CPU environment | Tokenizer, selector, doctor and acquisition-freeze receipts agree |
| Assessor preparation | The exact 20 requests reproduce from the declared bank: 12 reused-development and 8 fresh held-out checks |
| Experiment execution | No Q outputs, experiment slices, live assessor responses or calibration acceptance in this checkpoint |

Detailed checks, source archive identity and the actual laptop environment are retained in [checks.json](audits/2026-10-30-v7-cpu-accepted/checks.json). The original ZIP remains the raw evidence; this summary does not replace it.

The doctor's `technical_ready: true` establishes CPU apparatus readiness. Its `ready: false` reflects the missing assessor calibration acceptance and does not invalidate the CPU checkpoint. The prepared Astra profile remains `gpt-6-astra`, high reasoning, 25,000 output tokens including reasoning. Access and assessment suitability remain unverified. The recorded calibration planning estimate is $27.70, not an enforceable billing cap.

Continue with [runbook checkpoint 2](../rq1/RUNBOOK.md): on the accepted laptop, prepare the Q-input transfer summary and independently check API model access with a privately entered key. Return both receipts. Keep Nebius stopped and preserve the frozen CPU files and environment. No paid request, VM start or Q load is part of those preparations.

This acceptance changes documentation only. Acquisition and assessment code, source inputs, contracts, prepared requests and original failed calibration evidence remain unchanged. Finite witnesses support the specified source behaviour; they do not establish excerpt adequacy, general safety or independent human validation.
