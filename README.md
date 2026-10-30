# RQ1 evidence adequacy audit

This repository implements the dissertation's **RQ1 baseline evidence audit**. Original pretrained **LLMxCPG-Q** generates queries, **Joern** retrieves excerpts, a calibrated AI grades each excerpt in a stateless request, and a separate source-informed AI audit checks the visible justification. No independent human validation is claimed. Detector training/classification and transformation experiments are outside this experiment.

There are **3 development blocks and 12 main blocks**, each with vulnerable U and repaired F source. One primary run per input gives 6 development and 24 main Q/slice runs. F is reported separately. The evaluated configuration is **rq1-v5**, with fresh outputs in `work/rq1-v5`; preserve earlier runs.

The returned v4 run passed both real selector fixtures. Its 30 graph results were written to Docker logs instead of the RPC response. V5 verifies and reuses those results, then checks one fresh diagnostic return. See the [recovery record](docs/RQ1_CPU_RECOVERY_2026-10-30.md).

Read [the execution runbook](rq1/RUNBOOK.md), [protocol](rq1/PROTOCOL.md), [assessment procedure](rq1/ASSESSMENT.md), [implementation contract](rq1/REFERENCE_CONTRACT.md), and [current readiness](rq1/READINESS.md). The [source references](rq1/SOURCE_REFERENTS.md) explain each case's mechanism and required relationships.

## Next checkpoint: acquire assessor calibration on the existing VM

The laptop CPU checkpoint, input transfer and VM technical inspection are accepted. Continue with the [VM-only checkpoint guide](docs/RQ1_VM_ONLY_CHECKPOINTS.md): the existing H100 will host Q and a separately calibrated assessor sequentially, while Joern stays on laptop CPU. Token Factory is optional. The VM has 79.2 GiB CUDA/BF16 capacity and 216.6 GiB free cache storage; actual model loading and calibration are still pending.

After starting the existing VM and connecting by SSH, run there:

```bash
set -euo pipefail
cd ~/rq1-project
git fetch origin
git switch main
git pull --ff-only origin main
export HF_HOME="$HOME/rq1-storage/huggingface"
.venv-q/bin/python -m ops.rq1_vm_calibration
```

The runner checks server imports before downloading weights, loads the pinned assessor, acquires the 12 frozen stateless calibration responses, imports valid grades, stops its owned model server and exports actual evidence/diagnostics. Download/checksum-verify its archive from `work/rq1-v5/calibration-exports` into `D:\Dissertation-RQ1\exports`, then stop the VM in the Nebius console and return the archive. Calibration remains pending until the assistant audits all labels and source proofs. Preserve failures and do not rerun acquired answers. The accepted scientific core and CPU evidence are unchanged; no scan rerun is needed.

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
