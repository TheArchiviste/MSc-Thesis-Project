# RQ1 execution: run one checkpoint at a time

The Windows/WSL/Docker checks have returned: the Ubuntu/Docker integration works, RAM is 15.8 GiB, the installed Python is 3.14.4, and C: has 14.6 GiB free. The user requires bulk storage on D: (849 GB reported free). **The current checkpoint is [D_DRIVE_SETUP.md](D_DRIVE_SETUP.md): establish the D: storage root and a dedicated Ubuntu 24.04/Python 3.12 workspace, then return its verification output.** Later commands are prepared here; execute them after the previous checkpoint is inspected. No cluster or paid GPU has been started.

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

Expected: 3 development and 12 main cases; both `all_witnesses_pass_current_sources` fields true. These are real compiler/sanitizer checks, not adequacy scores. `init` and `validate` refuse to overwrite existing configuration/results. To rerun validation, retain the old output and choose a fresh `--work` directory; use that same directory for subsequent phases. Do not regenerate sources after acquisition.

```bash
python -m pip install -r rq1/requirements-tokenizer.txt
python -m rq1.setup token-audit
```

This downloads only the pinned tokenizer and audits all 30 prompts. It needs CPU and internet access, not model weights or a GPU. Return `work/rq1-token-audit.json` if any input does not fit; preserve the full input.

## 3. Laptop Joern acceptance — still no GPU

With Docker Desktop's WSL integration available and its resource budget checked:

```bash
mkdir -p work/joern-inputs
docker compose -f rq1/compose.yml up -d
docker compose -f rq1/compose.yml logs --tail=60
python -m rq1.setup pin-joern
python -m rq1.setup doctor --profile local --work work/rq1/local-readiness
```

The configuration permits an 8 GiB container and asks Java for a 6 GiB heap. This is provisional for the reported 16 GiB laptop: the first actual import and memory observation determine suitability. The service binds to loopback only. Return `work/rq1/local-readiness/readiness.json` and the last server log if blocked. A socket connection alone is insufficient: doctor imports staged C and queries the resulting CPG. If local Joern cannot pass, pause; select a CPU host before main freeze. A cluster is a fallback, not an automatic next step.

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
