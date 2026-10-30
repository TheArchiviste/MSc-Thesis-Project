# RQ1 evidence adequacy audit

This repository implements the dissertation's **RQ1 baseline evidence audit**. Original pretrained **LLMxCPG-Q** generates queries, **Joern** retrieves excerpts, a calibrated AI grades each excerpt in a stateless request, and a separate source-informed AI audit checks the visible justification. No independent human validation is claimed. Detector training/classification and transformation experiments are outside this experiment.

There are **3 development blocks and 12 main blocks**, each with vulnerable U and repaired F source. One primary run per input gives 6 development and 24 main Q/slice runs. F is reported separately. The evaluated configuration is **rq1-v5**, with fresh outputs in `work/rq1-v5`; preserve earlier runs.

The returned v4 run passed both real selector fixtures. Its 30 graph results were written to Docker logs instead of the RPC response. V5 verifies and reuses those results, then checks one fresh diagnostic return. See the [recovery record](docs/RQ1_CPU_RECOVERY_2026-10-30.md).

Read [the execution runbook](rq1/RUNBOOK.md), [protocol](rq1/PROTOCOL.md), [assessment procedure](rq1/ASSESSMENT.md), [implementation contract](rq1/REFERENCE_CONTRACT.md), and [current readiness](rq1/READINESS.md). The [source references](rq1/SOURCE_REFERENTS.md) explain each case's mechanism and required relationships.

## Next checkpoint: laptop CPU

Keep the rented GPU VM stopped. In your D-backed **Ubuntu-24.04** terminal:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh --recover-v4
```

Return the diagnostic ZIP created under `D:\Dissertation-RQ1\exports` and pause. This recovery verifies the existing 30 source witnesses, both real selector fixtures and all 30 Docker-side graph results, runs one fresh CPU diagnostic probe, and regenerates the tokenizer receipt and 12 ungraded calibration tasks. A fresh installation can use the script without `--recover-v4` for the full scan. Errors are also collected in the ZIP. No Q weights, experiment queries, grader API calls or cloud jobs are run. The next checkpoint is **assessor calibration**, before any paid Q acquisition.

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
