# RQ1 evidence adequacy audit

This repository implements the dissertation's **RQ1 baseline evidence audit**. Original pretrained **LLMxCPG-Q** generates queries, **Joern** retrieves excerpts, a calibrated AI grades each excerpt in a stateless request, and a separate source-informed AI audit checks the visible justification. No independent human validation is claimed. Detector training/classification and transformation experiments are outside this experiment.

There are **3 development blocks and 12 main blocks**, each with vulnerable U and repaired F source. One primary run per input gives 6 development and 24 main Q/slice runs. F is reported separately. The evaluated configuration is **rq1-v6**, with fresh outputs in `work/rq1-v6`; preserve earlier runs.

The returned v4 run passed both real selector fixtures. Its 30 graph results were written to Docker logs instead of the RPC response. V5 verifies and reuses those results, then checks one fresh diagnostic return. See the [recovery record](docs/RQ1_CPU_RECOVERY_2026-10-30.md).

Read [the execution runbook](rq1/RUNBOOK.md), [protocol](rq1/PROTOCOL.md), [assessment procedure](rq1/ASSESSMENT.md), [implementation contract](rq1/REFERENCE_CONTRACT.md), and [current readiness](rq1/READINESS.md). The [source references](rq1/SOURCE_REFERENTS.md) explain each case's mechanism and required relationships.

## Next checkpoint: prepare the v6 VM transfer bundle

The H100 loaded the assessor and returned all twelve v1 calibration responses, which failed. [The repair record](docs/RQ1_ASSESSOR_REPAIR_2026-10-30.md) preserves that failure and defines rq1-excerpt-v2. The fresh v6 laptop CPU checkpoint is now accepted: thirty source witnesses, thirty fitting Q prompts, both real selector fixtures and all thirty corpus graphs passed. The twelve revised calibration packets reproduce exactly and remain ungraded. [CPU acceptance](docs/audits/2026-10-30-v6-cpu-accepted/checks.json) records the uploaded ZIP and source hashes. No Q/main outputs have been inspected.

Keep the VM stopped. In the laptop's D-backed Ubuntu-24.04 terminal:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
.venv/bin/python -m ops.rq1_vm_checkpoint prepare
```

Return the printed summary or its .summary.json file from D:\Dissertation-RQ1\exports and pause. This revalidates the accepted laptop environment, audits the revised assessor requests with the small pinned tokenizer, and packages checksummed public inputs/CPU proofs for transfer. It loads no model weights and starts no VM. The accepted scientific core stays unchanged; do not repeat the CPU scan. After this summary is checked, the [VM guide](docs/RQ1_VM_ONLY_CHECKPOINTS.md) covers transfer, fresh VM inspection and the one predeclared v2 calibration attempt. Preserve every v5 response and cached model weights.

## Developer checks

On Linux with Python 3.11 or 3.12:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m rq1.setup verify
```

Tests use isolated simulations, never empirical experiment results. Actual failed v1 calibration responses are reported separately. No Q/slice development or main results have been collected. Main is blocked until current CPU checks, source-checked calibration, real development inference/assessments and an immutable freeze pass.

The prompt follows the [QCRI release](https://github.com/qcri/llmxcpg). Selector and reconstruction adaptations are explicit; this is a bounded audit of the documented configuration. GPL-3.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
