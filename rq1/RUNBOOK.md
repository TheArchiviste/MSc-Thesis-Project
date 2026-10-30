# RQ1 execution checkpoints

Run from a clean `main` source checkout. This implementation uses `work/rq1-v2`; never mix earlier `work/rq1` outputs into it. Return each requested result and pause before the next checkpoint. The assistant performs the delegated assessments from actual excerpts and gives detailed reasons; empty forms are never auto-labelled.

## 1. Laptop CPU acceptance — run now

Keep the Nebius VM stopped. In D-backed Ubuntu-24.04:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh
```

Expected: `RQ1_LOCAL_ACCEPTANCE_OK`, 3 development and 12 main witness pairs, 30 audited prompts, full-selector conformance PASS, and a local doctor PASS. The script installs only CPU tools/tokenizer dependencies, checks a separate synthetic Joern fixture, stops the Docker service and creates a ZIP in `D:\Dissertation-RQ1\exports`, including errors if a stage fails. Return that ZIP and **pause**. Do not delete any older work to make a check pass.

The Linux project and virtual environment are on the verified D-backed Ubuntu virtual disk. Hugging Face downloads and returned ZIPs explicitly use `D:\Dissertation-RQ1`. [Storage details](D_DRIVE_SETUP.md).

## 2. Transfer the accepted inputs — wait for checkpoint 1 review

After the local ZIP is accepted, package these files, preserving their paths: new `config.json`, `token-audit.json`, `joern-capability/readiness.json` and development/main `witness_validation.jsonl`. Include a SHA256 checksum. The assistant will provide the exact packaging and SCP commands for the confirmed files/IP. Never transfer the private SSH key. Start the H100 only when ready to use it; re-read its public IP after restart. The previously uploaded archive is historical and must not overwrite rq1-v2 data.

On the VM, update `~/rq1-project` to clean `main`, retain the Python 3.11 Q environment and install this source version with its pinned GPU requirements. Verify the archive checksum before extraction. The local selector receipt describes CPU capability; it does not require Docker on the GPU VM. Copying development/main witness files does not create query or slice records.

## 3. GPU doctor and six development Q inputs — wait for checkpoint 2

The later commands, inside the accepted Q virtual environment and repository root, are (development/main work directories must already exist from the accepted input transfer):

```bash
set -euo pipefail
python -m rq1.setup doctor --profile gpu --work work/rq1-v2/gpu-doctor
python -m evidence_experiment query --split development 2>&1 | tee work/rq1-v2/development/query-command.log
python -m rq1.setup status --split development
```

First return the doctor result before executing Q generation. Q uses BF16 pretrained weights, not training. Model loading is the expensive acceptance check. A load/device error leaves inputs pending and logs the error; it is not an inadequate excerpt. Success requires six terminal query records, linked real model sessions and a query receipt. Retain the entire development directory, both session/runtime logs, and config/audits. Download a checksummed copy to D:, verify it, then stop the VM. [Nebius handoff](../docs/NEBIUS_RQ1_GUIDE.md).

## 4. Development Joern on the laptop — after accepted Q transfer

Use the same accepted CPU environment as checkpoint 1 and the exact development directory downloaded from the GPU. Do not regenerate its lock. The Q and slice environments are stored separately.

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment slice --split development
.venv/bin/python -m evidence_experiment packets --split development
.venv/bin/python -m rq1.assess prepare --split development
```

A fresh Docker/Scala process is used for each input. Infrastructure errors save an attempt and stop; return the worker logs before resuming the **same** command. Three attempts total are allowed. Terminal semantic query failures and empty slices are retained without retries for a better outcome. Mapping errors pause and remain uncertain.

Return actual packets, query/slice traces and forms. The assistant assesses each excerpt first, saving `assessments.initial.jsonl`, then compares U explanations with source references in `adjudications.jsonl`. Corrections go in `assessments.final.jsonl` with actual timestamps. F controls retain their initial decisions. No minimum adequacy rate is required for development acceptance.

## 5. Development report and pre-main freeze

After the assistant returns completed assessment files:

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment analyze --split development
.venv/bin/python -m rq1.setup freeze --split development
```

Freeze revalidates the exact six observations, real model metadata, full CPU/GPU environments, source contract, all shown assessments and full-selector receipt. Unresolved development infrastructure/mapping failures must be repaired consistently before freeze; honest semantic misses are valid observations. Retain any earlier attempts. The freeze is exclusive and cannot be overwritten. Development may remain provisional for delayed consistency; this does not put a 48-hour wait on main acquisition.

## 6. Main Q on the H100, then main slices on CPU

Transfer the accepted freeze and exact current source version to the VM. In the same Q environment used for development:

```bash
set -euo pipefail
python -m evidence_experiment query --split main 2>&1 | tee work/rq1-v2/main/query-command.log
python -m rq1.setup status --split main
```

Exactly 24 primary inputs are expected. Return/download/verify the complete main directory and stop the VM. On the laptop, in the accepted CPU environment:

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment slice --split main
.venv/bin/python -m evidence_experiment packets --split main
.venv/bin/python -m rq1.assess prepare --split main
```

Return the actual evidence for the assistant's reasoned initial/matching/final passes, as in development. Do not replace cases, change flow type, shorten inputs or tune the selector because a slice is large or insufficient.

## 7. Provisional report and delayed consistency

After initial and final assessments and U mechanism correspondence are complete:

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment analyze --split main
.venv/bin/python -m rq1.assess reassessment-plan --split main
```

The plan freezes a seeded 25% of unique shown U/F packets, rounded up. Return the selected packets **at or after each `not_before_utc`**, at least 48 hours after its actual initial assessment. The assistant performs a second excerpt-only pass using the same honest identity, detailed reasons and actual timestamps. Preserve `assessments.initial.jsonl` and write `assessments.second.jsonl`; never backdate a rating. With no shown packets the delayed check is explicitly not applicable.

## 8. Final report and reproducibility archive

Once the delayed pass is returned:

```bash
set -euo pipefail
.venv/bin/python -m rq1.assess consistency --split main
.venv/bin/python -m evidence_experiment finalize --split main
```

`finalize` refuses incomplete/short-delay checks. Read `rq1_report.md`; use `rq1_cases.csv` for case explanations and `rq1_element_visibility.csv` for descriptive role visibility. `analysis.json` holds denominators, bounds, provenance and consistency. Archive Git commit, corpus/references, config, freeze, tokenizer/capability receipts, full query/session/slice/attempt/worker logs, stage runtime requirements, packet order, all rating passes and reports to D:. Preserve failed attempts as well as successful ones.

The result answers only the bounded RQ1 adequacy question for these 12 source-selected blocks. A visible role line is not an adequacy judgment. Identification bounds are not confidence intervals. AI-assisted single-assessor judgments do not establish independent validation or general prevalence.
