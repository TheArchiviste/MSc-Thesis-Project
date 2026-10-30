# RQ1 evidence adequacy audit

This repository implements the dissertation's **RQ1 baseline evidence audit**. Original pretrained **LLMxCPG-Q** generates queries, **Joern** retrieves excerpts, a calibrated AI grades each excerpt in a stateless request, and a separate source-informed AI audit checks the visible justification. No independent human validation is claimed. Detector training/classification and transformation experiments are outside this experiment.

There are **3 development blocks and 12 main blocks**, each with vulnerable U and repaired F source. One primary run per input gives 6 development and 24 main Q/slice runs. F is reported separately. The evaluated configuration is **rq1-v6**, with fresh outputs in `work/rq1-v6`; preserve earlier runs.

The returned v4 run passed both real selector fixtures. Its 30 graph results were written to Docker logs instead of the RPC response. V5 verifies and reuses those results, then checks one fresh diagnostic return. See the [recovery record](docs/RQ1_CPU_RECOVERY_2026-10-30.md).

Read [the execution runbook](rq1/RUNBOOK.md), [protocol](rq1/PROTOCOL.md), [assessment procedure](rq1/ASSESSMENT.md), [implementation contract](rq1/REFERENCE_CONTRACT.md), and [current readiness](rq1/READINESS.md). The [source references](rq1/SOURCE_REFERENTS.md) explain each case's mechanism and required relationships.

## Current checkpoint: v2 assessor calibration failed; pause inference

The fresh v6 laptop CPU checkpoint and VM inspection passed. The one predeclared v2 assessor attempt then returned twelve nontruncated JSON responses. Four omit required fields; three declared labels disagree with the development key. Even some matching labels have unsupported explanations. The complete strict import failed, and calibration is **not accepted**. [The result and next decision](docs/RQ1_ASSESSOR_V2_RESULT_2026-10-30.md) include a twelve-row source audit and verified archive/provenance hashes. Earlier v1 evidence and its [repair record](docs/RQ1_ASSESSOR_REPAIR_2026-10-30.md) remain unchanged.

Keep the Nebius VM stopped and preserve both calibration archives. No new command is required. The protocol explicitly pauses after a failed v2 attempt for an assessor/design decision; do not rerun responses, repair grades, lower the acceptance rule or start Q acquisition. The recommendation is to replace the assessor in a separately declared revision, keeping the existing source bank, proof requirements and failed-attempt history. Such a revision has **not** been implemented or run.

The accepted CPU evidence still covers thirty witnesses, thirty fitting Q prompts, both real selector fixtures and all thirty corpus graphs. [CPU acceptance](docs/audits/2026-10-30-v6-cpu-accepted/checks.json) binds those inputs. Documentation of the result does not change the sealed scientific core or require another CPU scan. Real Q outputs and experiment slices have not been collected. The [VM guide](docs/RQ1_VM_ONLY_CHECKPOINTS.md) records the completed handoff and session procedure for reference.

## Developer checks

On Linux with Python 3.11 or 3.12:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m rq1.setup verify
```

Tests use isolated simulations, never empirical experiment results. Actual failed v1 and v2 calibration responses are reported separately. No Q/slice development or main results have been collected. Main is blocked until source-checked calibration, real development inference/assessments and an immutable freeze pass.

The prompt follows the [QCRI release](https://github.com/qcri/llmxcpg). Selector and reconstruction adaptations are explicit; this is a bounded audit of the documented configuration. GPL-3.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
