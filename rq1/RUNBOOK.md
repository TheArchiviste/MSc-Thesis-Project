# RQ1 execution: run one checkpoint at a time

The local preparation log confirms all 3 development and 12 main U/F witness pairs pass on Ubuntu-24.04/WSL2 with Python 3.12.3. Its filesystem is on D:. The latest screenshot shows 7.8 GiB WSL RAM and 4 GiB swap, and the user has confirmed Docker bulk storage is on D:. **The laptop Joern check now passes all 8 checks. The current checkpoint is the CPU token audit in section 2**, also described in section 6 of [D_DRIVE_SETUP.md](D_DRIVE_SETUP.md). No cluster or paid GPU has been started.

## 1. Your Windows machine — completed diagnostic command

Open PowerShell and run:

```powershell
$report = Join-Path $env:USERPROFILE "rq1-machine-check.txt"
& {
    Get-Date -Format o
    Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version
    Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
    wsl --status
    wsl --list --verbose
    docker version
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
} *>&1 | Tee-Object -FilePath $report
```

The returned screenshots confirmed that Ubuntu and Docker work. The current storage/Python follow-up is in `D_DRIVE_SETUP.md`. The GTX 1660 Ti is not the Q host; the local targets are preparation, tokenizer auditing, Joern and reporting.

## 2. WSL2 CPU environment — after checkpoint 1 is reviewed

These commands target the **Ubuntu-24.04 distribution whose virtual disk is on D:**, with Python 3.12. Run them only after `D_DRIVE_SETUP.md` has been checked. Start that distribution from PowerShell with `wsl -d Ubuntu-24.04`. Keep the checkout in its Linux filesystem; its project files, virtual environment and caches will be backed by D:.

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv gcc libc6-dev
mkdir -p ~/projects
cd ~/projects
git clone --branch codex/rq1-execution https://github.com/TheArchiviste/MSc-Thesis-Project.git
cd MSc-Thesis-Project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r rq1/requirements-local.txt
python -m pip install --no-deps -e .
python -m rq1.setup verify
python -m rq1.setup init
python -m rq1.setup validate --split development
python -m rq1.setup validate --split main
```

For a fresh local setup, the same environment/source checks are automated by `bash rq1/local_prepare.sh` after installing the apt prerequisites and cloning above. The script preserves existing configs and witness records, rejects an unsuitable Python version, installs only local dependencies, and writes `work/rq1/local-preparation.md` plus a copy to `D:\Dissertation-RQ1\exports` when available. It does not pull images or load Q. Do not run both the manual and automated paths unnecessarily.

Expected: 3 development and 12 main cases; both `all_witnesses_pass_current_sources` fields true. These are real compiler/sanitizer checks, not adequacy scores. `init` and `validate` refuse to overwrite existing configuration/results. To rerun validation, retain the old output and choose a fresh `--work` directory; use that same directory for subsequent phases. Do not regenerate sources after acquisition.

```bash
python -m pip install -r rq1/requirements-tokenizer.txt
python -m rq1.setup token-audit
```

This downloads only the pinned tokenizer and audits all 30 prompts. The requirements explicitly include Jinja2 3.1.6, which Transformers 4.47.1 needs to render the real chat template; without it this version can fail with `NameError: Extension is not defined`. The matching Jinja pin is also present in the candidate GPU requirements. No model backend is needed for this audit, so the message about missing PyTorch/TensorFlow/Flax is expected. It needs CPU and internet access, not model weights or a GPU. Return `work/rq1-token-audit.json` if any input does not fit; preserve the full input.

## 3. Laptop Joern acceptance — still no GPU

With Docker Desktop's WSL integration available and its resource budget checked:

```bash
bash rq1/local_joern.sh
```

The helper starts the digest-pinned image (reusing the local copy when present), waits up to five minutes for the actual WebSocket handshake and `connected` greeting, records its digest, and runs the real import/query check with a bounded timeout. A published TCP port is insufficient: Docker can accept a connection before the Scala server has finished starting. Each attempt has a new `work/rq1/local-readiness-<timestamp>-<suffix>` directory. It preserves `startup.json` with every handshake attempt, complete timestamped server logs, reports, package versions, process arguments, library filenames, container state and a memory snapshot even if startup or the check fails. On failure, it captures diagnostics and stops the Joern container, retaining the image and named volume. When the D: exports folder exists, it creates a ZIP there and prints the path. Return that ZIP and pause. A startup failure may lack `readiness.md`; its command/server logs and `checkpoint.json` remain diagnostic evidence.

The configuration permits a 6 GiB container and explicitly passes `-J-Xmx4g` to Joern, leaving headroom inside the planned 8 GiB WSL VM. The VM's 4 GiB swap file belongs on D:. This budget is provisional: the first real import and memory observation determine suitability. Confirm Docker's disk image is on D: before pulling. The service binds to loopback only. A socket connection alone is insufficient: doctor imports staged C and queries the resulting CPG. If local Joern cannot pass, pause; select a CPU host before main freeze. A cluster is a fallback, not an automatic next step.

The earlier `ghcr.io/joernio/joern:v4.0.0` container tag was checked on 28 October 2026 and returns `MANIFEST_UNKNOWN`. `compose.yml` instead pins the available official linux/amd64 manifest `sha256:b847c9327adf8c3f19ba89bbbd1ce394353967538885ff5c2bcf812b3c3cc1e3`. GHCR metadata records creation on 28 October 2026 and image-build source revision `9fd178db7bca3ff5f1f5fd3d03b8d80de1ab5aeb`; its label is `nightly`. The image recipe installs the latest release at build time, so that source revision/label does not establish the installed Joern CLI version. The first returned laptop ZIP identifies the installed CLI as **4.0.667**, from `io.joern.joern-cli-4.0.667.jar`. Actual library filenames and server logs are retained for acceptance. Compressed layers total approximately 2.2 GiB; extraction needs additional D: space. This artifact is fixed before development. The first readiness attempt was blocked: the client tried its import approximately seven seconds after container start, while the captured server log was still processing the startup classpath. The container was running, `OOMKilled` was false, and the JVM arguments contained `-Xmx4g`. The subsequent returned laptop ZIP at commit `6efd081` passed the protocol greeting after 13.431 seconds and all 8 readiness checks, including a successful real CPG import/query. Its post-check container memory was 776.6 MiB with no OOM kill; this is a snapshot, not a peak measurement or a full corpus acceptance test. No main acquisition has run. No automatic fallback to a different image is allowed.

## 4. Q GPU development — separate explicit hardware checkpoint

Pause before arranging remote compute. Obtain an available Linux GPU with enough memory for the original checkpoint (the preflight targets a single 80 GB class CUDA/BF16 device); retain at least 100 GiB free model-cache space. No training or D is involved. Confirm the actual budget/instance first. The university cluster can replace a rental if access is available; allocation details need review before submitting anything.

On the agreed GPU host, use a full clone of this exact branch/commit and Python 3.11. Copy the **local** `work/rq1-config.json`, `work/rq1-token-audit.json` and `work/rq1/development/witness_validation.jsonl` to identical paths under the clone. Do not create a second Joern digest/config with different semantic settings. Never copy `.venv`; use a dedicated GPU environment.

```bash
python3.11 -m venv .venv-q
source .venv-q/bin/activate
python -m pip install -r rq1/requirements-gpu.txt
python -m pip install --no-deps -e .
mkdir -p work/rq1/development
python -m pip freeze > work/rq1/gpu-pip-freeze.txt
python -m rq1.setup doctor --profile gpu --work work/rq1/gpu-readiness
```

The pinned GPU package set is a candidate, not hardware-validated yet. Return readiness output before loading Q. If ready, the exact development command is:

```bash
set -o pipefail
python -m evidence_experiment query --manifest rq1/development.jsonl --config work/rq1-config.json --work work/rq1/development --repeats 1 2>&1 | tee work/rq1/development/query-command.log
python -m rq1.setup status --split development
```

Expected: six terminal Q records, with raw text/status and no Joern or D requirement on this host. Malformed Q output is an observation, not permission to regenerate for a better answer. Model-load/OOM failures stop and leave uncollected inputs pending. Retain the error and pause for diagnosis. Return the whole development work directory, including lock, receipts, phase log and query session metadata. Do not overwrite or selectively copy only successful queries.

## 5. Real development slicing and AI assessment — laptop

Restore the returned development directory to the laptop, retaining its witness file, query receipts and lock. Use the same project commit and config. Query-stage GPU dependencies may differ from the CPU slicing environment; each phase has its own dependency lock.

```bash
source .venv/bin/activate
python -m evidence_experiment slice --manifest rq1/development.jsonl --config work/rq1-config.json --work work/rq1/development --repeats 1
python -m evidence_experiment packets --manifest rq1/development.jsonl --config work/rq1-config.json --work work/rq1/development --repeats 1 --duplicate-fraction 0 --review-seed 20261027
python -m rq1.assess prepare --split development
```

Return `assessment_order.jsonl` for the assistant's excerpt-only first pass, followed by the reference matching pass. The forms intentionally contain no automatic judgements. The assistant supplies detailed reasons and an honest AI identity. Retain initial and final assessment files and matching records. Then:

```bash
python -m evidence_experiment analyze --manifest rq1/development.jsonl --config work/rq1-config.json --work work/rq1/development --repeats 1 --evidence-only --assessment-mode assistant --initial-assessments work/rq1/development/assessments.initial.jsonl --assessments work/rq1/development/assessments.final.jsonl --adjudications work/rq1/development/adjudications.jsonl --analysis-seed 20261027
python -m rq1.setup freeze
```

Low adequacy and well-justified uncertainty are legitimate findings. The acceptance gate concerns complete traceable data, real runtime, maps, infrastructure and a documented rubric. If development needs a semantic config/code repair, preserve its old run in a separate directory and consistently rerun the affected development stages. Refresh the final token audit before freezing. Do not use main outcomes to tune the rubric.

## 6. Frozen main acquisition

Copy the final commit, config, token audit, `work/rq1-freeze.json` and main `witness_validation.jsonl` to the GPU clone. Retain its accepted GPU environment. Main is blocked if the corpus or policy differs from freeze.

```bash
source .venv-q/bin/activate
mkdir -p work/rq1/main
set -o pipefail
python -m evidence_experiment query --manifest rq1/main.jsonl --config work/rq1-config.json --work work/rq1/main --repeats 1 2>&1 | tee work/rq1/main/query-command.log
python -m rq1.setup status --split main
```

Return the full main directory to the laptop. On the laptop:

```bash
source .venv/bin/activate
python -m evidence_experiment slice --manifest rq1/main.jsonl --config work/rq1-config.json --work work/rq1/main --repeats 1
python -m evidence_experiment packets --manifest rq1/main.jsonl --config work/rq1-config.json --work work/rq1/main --repeats 1 --duplicate-fraction 0 --review-seed 20261027
python -m rq1.assess prepare --split main
```

Expected: 24 terminal Q records and 24 slice records, covering all 12 U and 12 F. An unusable result is retained. For saved Joern infrastructure attempts, restart and resume the identical command:

```bash
docker compose -f rq1/compose.yml restart joern
python -m evidence_experiment slice --manifest rq1/main.jsonl --config work/rq1-config.json --work work/rq1/main --repeats 1
```

There are at most three infrastructure attempts per input. Never delete failure records to reset the budget. Semantic failures are not retried. Unknown failures require inspection; do not alter individual source inputs.

## 7. Main assessment, delayed check and final report

The assistant assesses actual packets and supplies explained initial ratings and mechanism matches. Preserve the initial file unchanged, then select the delayed subset:

```bash
python -m rq1.assess reassessment-plan --split main
```

At or after each recorded not-before time (at least 48 hours), return `reassessment_packets.jsonl` for the assistant's second pass under the same honest identity. After the real second-pass file exists:

```bash
python -m rq1.assess consistency --split main
python -m evidence_experiment analyze --manifest rq1/main.jsonl --config work/rq1-config.json --work work/rq1/main --repeats 1 --evidence-only --assessment-mode assistant --initial-assessments work/rq1/main/assessments.initial.jsonl --assessments work/rq1/main/assessments.final.jsonl --adjudications work/rq1/main/adjudications.jsonl --analysis-seed 20261027
```

Read `work/rq1/main/rq1_report.md`. `rq1_cases.csv` gives acquisition, adequacy, missing context and reasons; `rq1_element_visibility.csv` describes role-line overlap; `analysis.json` retains full results/provenance. Check that A + I + uncertain = 12; report exact counts, uncertainty bounds, failed retrievals and F false adequacy separately. The delayed check is within-assessor consistency, not inter-rater validation.

Archive the tested git commit, full `rq1/`, all `work/rq1*` files, local/GPU `pip freeze`, actual OCI digest, freeze, command logs, raw data and assessment passes. Revise the dissertation to the narrowed AI-assisted RQ1 contribution. Target freeze by 1 November, collection by 3 November, assessment by 6 November and analysis by 7 November; keep 8–12 November for writing and audit before 13 November submission.
