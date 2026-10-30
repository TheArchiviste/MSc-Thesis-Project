# RQ1 readiness — 30 October 2026

**The repository is narrowed to RQ1. No real Q generation, experiment slicing or excerpt-adequacy assessment has been completed. Main remains blocked.**

| Item | Evidence and next gate |
|---|---|
| Corpus | 3 development + 12 main disjoint generator blocks; one U and one F each. Selected sources, maps, witness plans and source-only references retained. |
| Existing CPU witnesses | Earlier workspace and laptop checks passed all 30 sources. rq1-v2 local acceptance rechecks their current source hashes and compiler results. |
| Earlier tokenizer audit | Historical preparation only. rq1-v2 uses the release-aligned prompt, so a fresh 30-input CPU token audit is required. |
| Earlier laptop Joern smoke | Real import/method lookup passed with CLI 4.0.667. This does not establish full selector compatibility. The new synthetic full-selector conformance gate is pending on the laptop. |
| Rented VM | User selected regular H100 80 GB, 16 vCPU, 200 GiB RAM, Ubuntu 24.04 CUDA image and 250 GiB disk in Finland. Hardware was observed; Python 3.11/Torch/vLLM/BF16 imports passed. Current power state is unverified: keep it stopped during CPU work. |
| Uploaded files | Historical input archive reached `/home/rq1/`. It belongs to the older implementation; do not extract it over rq1-v2 work. A fresh, checksummed transfer will be prepared after laptop acceptance. |
| Q load | Not attempted. GPU doctor, real model load and six development queries remain separate checkpoints. |
| Development selector/assessment | Six real primary slice outcomes and all shown excerpt judgments required before freeze. No adequacy-rate or slice-size acceptance cutoff. |
| Main | No freeze; no main query. After development acceptance, acquire exactly 24 U/F runs, assess shown packets, then perform the frozen delayed check. |

The audit of 29 October is historical evidence of the previous implementation. The [change record](../docs/RQ1_IMPLEMENTATION_2026-10-30.md) explains its fixes and the remaining hardware checks. Unit tests include simulations and are never experiment results.

Next: follow **checkpoint 1** in [RUNBOOK.md](RUNBOOK.md), return the D: diagnostic ZIP, and pause. No university cluster is necessary for this CPU checkpoint.
