> Current VM-only route: [RQ1_VM_ONLY_CHECKPOINTS.md](RQ1_VM_ONLY_CHECKPOINTS.md). The CPU checkpoint has passed. Prepare the handoff locally first; assessor calibration will run on the existing VM before Q acquisition. The older sequence below describes the later Q handoff.

# Nebius handoff for the RQ1-only experiment

Updated 30 October 2026. **Current action: finish laptop CPU acceptance and return its ZIP, then complete assessor calibration before any Q load. Keep the VM stopped.** This guide records later checkpoints; it does not authorize bypassing the pauses in [RUNBOOK.md](../rq1/RUNBOOK.md).

## Existing setup

The user has already funded the account with $25 and configured a budget. The observed VM has one regular H100 80 GB, 16 vCPU, approximately 200 GiB RAM, a 250 GiB SSD, and the Ubuntu 24.04 CUDA image in Finland. SSH user is `rq1`; the private key stays at `~/.ssh/nebius_rq1` on the laptop. The last public IP was `89.169.114.61`; read the current console IP after restarting instead of assuming it is unchanged.

The VM source at the earlier hardware checkpoint was `81a7a8a7543a8c5bc9fab4ffc759b9e9f202b643`. Python 3.11.18, Torch 2.5.1+cu124, Transformers 4.47.1, vLLM 0.6.6.post1 and BF16 imports passed. No original Q weights have been deliberately loaded. The previous input archive reached `/home/rq1/` but belongs to the older pipeline; preserve it without extracting over rq1-v5.

## Budget and stopping

Review the console's actual current VM/disk estimate and billing balance before restarting. The previous running estimate was approximately $4.53/hour before tax; that is a historical quote, not a new price guarantee. Keep GPU sessions short: development queries, stop/download/assess locally, then main queries in a separate accepted session. Model download/load time also uses the running VM.

A budget alert is not an automatic VM shutdown. A stopped VM can retain billable disks and other resources. Use the console **Stop** action and verify **Stopped** when waiting. Before deleting anything, download and verify all experiment files; inspect retained disks, IPs and balances separately. No automated resource deletion or payment changes are performed by this repository.

Current official references: [prices](https://nebius.com/prices), [budgets](https://docs.nebius.com/signup-billing/budgets), [PAYG](https://docs.nebius.com/signup-billing/billing-models/payg), [stop/start](https://docs.nebius.com/compute/virtual-machines/stop-start), [billing documents](https://docs.nebius.com/signup-billing/payments/invoices). Check the console for the actual amount, tax and account conditions when acting.

## After accepted laptop CPU output and assessor calibration

The new inputs live under `work/rq1-v5`. Package the accepted config, tokenizer audit, entire selector capability directory (including any recovery proofs and probe logs), development/main witness files, and full accepted calibration directory with public requests, raw responses, private key, proof audit and acceptance/provenance receipts. Exclude the API profile/credentials. Q readiness revalidates this calibration without contacting the grader. Use a fresh archive name, compute SHA256, upload archive and checksum, and verify before extraction. Keep all relative paths. The assistant will issue the exact SCP command after the current IP and accepted files are known; no private keys or model weights belong in the archive.

On the VM, after the explicit restart/transfer checkpoint, update the existing checkout and Q environment:

```bash
set -euo pipefail
cd ~/rq1-project
git fetch origin
git switch main
git pull --ff-only origin main
.venv-q/bin/python -m pip install --no-cache-dir -r rq1/requirements-gpu.txt
.venv-q/bin/python -m pip install --no-cache-dir -e .
.venv-q/bin/python -m pip check
mkdir -p ~/rq1-storage/huggingface work/rq1-v5/development work/rq1-v5/main
export HF_HOME="$HOME/rq1-storage/huggingface"
.venv-q/bin/python -m rq1.setup verify
.venv-q/bin/python -m rq1.setup doctor --profile gpu --work work/rq1-v5/gpu-doctor
```

The accepted archive must be checksum-verified and extracted **before doctor**; do not substitute old checked-in workspace logs for the user's actual laptop files. Return the doctor output and pause before downloading/loading Q. No Docker selector is needed on the GPU VM; its CPU capability receipt is transferred from the laptop. Q and slicing have distinct locked environments.

## Accepted development Q session

Only after doctor acceptance, run the following inside tmux on the VM:

```bash
set -euo pipefail
cd ~/rq1-project
export HF_HOME="$HOME/rq1-storage/huggingface"
.venv-q/bin/python -m evidence_experiment query --split development 2>&1 | tee work/rq1-v5/development/query-command.log
.venv-q/bin/python -m rq1.setup status --split development
```

Expected: six terminal primary queries and a query-stage receipt. A model load/OOM exception is a blocked infrastructure checkpoint, not six fabricated semantic misses. Retain partial files and resume only after inspection. Download the entire development directory, model-session metadata, runtime requirements, doctor report, config and both CPU audits with a checksum. Verify the downloaded archive and stop the VM. Laptop CPU slicing and actual AI-assisted assessment follow; main is blocked until a pre-main freeze.

## Main Q session

Transfer the accepted `freeze.json` and main witnesses, use the same clean implementation and Q package environment as development, and run only after its separate checkpoint is accepted:

```bash
set -euo pipefail
cd ~/rq1-project
export HF_HOME="$HOME/rq1-storage/huggingface"
.venv-q/bin/python -m evidence_experiment query --split main 2>&1 | tee work/rq1-v5/main/query-command.log
.venv-q/bin/python -m rq1.setup status --split main
```

Expected: 24 terminal primary query records. Download and checksum-verify the entire main run directory, then stop the VM before CPU slicing or assessment. No main case replacement, output-based rerun, training or detector stage is permitted. Follow runbook checkpoints 6–8 for final data, including the delayed 48-hour consistency check.
