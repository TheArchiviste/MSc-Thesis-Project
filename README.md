# RQ1 evidence adequacy audit

This repository implements the dissertation's **RQ1 baseline evidence audit**. Original pretrained **LLMxCPG-Q** generates queries, **Joern** retrieves excerpts, a calibrated AI grades each excerpt in a stateless request, and a separate source-informed AI audit checks the visible justification. No independent human validation is claimed. Detector training/classification and transformation experiments are outside this experiment.

There are **3 development blocks and 12 main blocks**, each with vulnerable U and repaired F source. One primary run per input gives 6 development and 24 main Q/slice runs. F is reported separately. The evaluated configuration is **rq1-v5**, with fresh outputs in `work/rq1-v5`; preserve earlier runs.

The returned v4 run passed both real selector fixtures. Its 30 graph results were written to Docker logs instead of the RPC response. V5 verifies and reuses those results, then checks one fresh diagnostic return. See the [recovery record](docs/RQ1_CPU_RECOVERY_2026-10-30.md).

Read [the execution runbook](rq1/RUNBOOK.md), [protocol](rq1/PROTOCOL.md), [assessment procedure](rq1/ASSESSMENT.md), [implementation contract](rq1/REFERENCE_CONTRACT.md), and [current readiness](rq1/READINESS.md). The [source references](rq1/SOURCE_REFERENTS.md) explain each case's mechanism and required relationships.

## Next checkpoint: prepare the existing VM handoff

The laptop CPU checkpoint is accepted. Continue with the [VM-only checkpoint guide](docs/RQ1_VM_ONLY_CHECKPOINTS.md): the existing H100 will host Q and a separately calibrated assessor sequentially, while Joern stays on laptop CPU. Token Factory is optional.

Keep the VM stopped and run in D-backed Ubuntu-24.04:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
.venv/bin/python -m ops.rq1_vm_checkpoint prepare
```

Return the JSON summary or `.summary.json` file from `D:\Dissertation-RQ1\exports`, then pause. This checks the assessor tokenizer and creates a small checksummed transfer bundle. It starts no VM, downloads no model weights and generates no grades. The accepted CPU source contract is unchanged; no scan rerun is needed.

## Developer checks

On Linux with Python 3.11 or 3.12:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m rq1.setup verify
```

Tests use isolated simulations, never empirical experiment results. No actual excerpt grades or main results have been collected. Main is blocked until the current CPU checks, source-checked assessor calibration, real development inference and assessments, and an immutable freeze pass.

The prompt follows the [QCRI release](https://github.com/qcri/llmxcpg). Selector and reconstruction adaptations are explicit; this is a bounded audit of the documented configuration. GPL-3.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
