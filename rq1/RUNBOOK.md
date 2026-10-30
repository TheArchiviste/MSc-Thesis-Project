# RQ1 execution checkpoints — active v7 route

Run only the current checkpoint, return its specified output and pause. The assistant performs source/proof judgments with detailed reasons. Historical guides do not override this route. Preserve v5/v6 outputs and cached model weights.

## 1. Laptop CPU checkpoint — accepted 30 October 2026

The v7 archive `local-attempt-20261030T202535Z-4iVZhD.zip` passed the separate receipt audit. See [the acceptance record](../docs/RQ1_V7_CPU_CHECKPOINT_2026-10-30.md). Continue at checkpoint 2 on that same laptop environment; preserve the frozen receipts. The commands below document the completed checkpoint, not an instruction to repeat it.

Keep Nebius stopped. In D-backed Ubuntu-24.04:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh
```

Expected: 34 U/F source witnesses (30 experiment plus 4 assessor-only), 30 fitting Q prompts, 2 actual full-selector fixtures and 30 source graphs. Twenty ungraded calibration anchors and the independent acquisition freeze are prepared. `technical_ready` and calibration acceptance are separate. Return the new `local-attempt-*.zip` from **D:\Dissertation-RQ1\exports** and pause. This uses CPU/Docker and the small cached Q tokenizer only, with no API key, model weights or VM.

V7 uses new stage-scoped receipts. Do not use `--recover-v4`, relabel v6 files, or repeat this checkpoint after Q acquisition begins. The collector refuses that situation to avoid exposing sealed data. The project is in the verified D-backed WSL distribution; HF caches and exports explicitly use D:.

## 2. Two independent preparations — accepted 30 October 2026

The Astra model lookup returned HTTP 200 at 20:51:34 UTC, with the frozen profile hash and zero inference requests. The exact 167-file Q handoff archive and all payload hashes also passed. See [the access/handoff record](../docs/audits/2026-10-30-v7-access-handoff-accepted/checks.json). These commands document the completed preparations; no repeat is needed. Funding and GPU-host inspection remain unverified.

**Assessor:** prepare the OpenAI API account/access and separate budget. The assistant supplies a private-terminal-key command for `ops.rq1_api_calibration access`, a GET-only model check. Return its receipt; pause before paid inference. The offline inspection reports the conservative twenty-request estimate. API funding is separate from Nebius.

Run this in the existing Ubuntu terminal. The key is read privately, passed only to the child process, and is not written into the command or receipt. This is a model lookup, not inference or proof of available funding:

```bash
cd ~/projects/MSc-Thesis-Project
.venv/bin/python - <<'PY'
import getpass
import os
import subprocess
import sys
env = os.environ.copy()
env['OPENAI_API_KEY'] = getpass.getpass('OpenAI API key (hidden): ')
raise SystemExit(subprocess.call(
    [sys.executable, '-m', 'ops.rq1_api_calibration', 'access'], env=env))
PY
```

Return its printed JSON (also saved in `work/rq1-v7/calibration/api-access.json`). Do not paste the API key into the conversation.

**Q host:** on the accepted laptop run `ops.rq1_q_handoff prepare` and return its summary. It packages only configuration, acquisition freeze, witness records, tokenizer and complete Joern capability proofs. No assessor key, private answer key or weights are transferred. After that summary is checked, the assistant supplies exact checksum/SCP/extraction commands using the current console IP and confirmed filename. Restart the existing H100 only for its accepted checkpoint. Use `~/rq1-project`, the existing `.venv-q` and `HF_HOME=$HOME/rq1-storage/huggingface`; retain the established packages. Run `ops.rq1_q_handoff inspect`, return its technical receipt and pause before Q weights load.

```bash
cd ~/projects/MSc-Thesis-Project
.venv/bin/python -m ops.rq1_q_handoff prepare
```

Return only the printed summary. Keep the transfer archive on D: for the later mechanical VM handoff. Do not rerun the completed CPU checkpoint or change the accepted Python/packages.

## 3. Assessor calibration — accepted; install the receipt

API funding was checked privately before the declared attempt. It acquired and strictly imported twenty real responses from 21:01:19 to 21:09:17 UTC. All twenty labels and subsequent source-proof audits pass, with development 12/12 and held-out 8/8 separately reported. [Detailed audit and limits](../docs/RQ1_ASSESSOR_V3_RESULT_2026-10-30.md). No repeat paid command is needed.

On the existing laptop, install only the three new audit/acceptance files. The original requests, bank, profile and raw responses stay in place. Any conflicting existing audit file is preserved and blocks this command; the final status check verifies every bound artifact:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git pull --ff-only origin main
.venv/bin/python - <<'PY'
from pathlib import Path
source = Path('docs/audits/2026-10-30-assessor-v3-accepted')
target = Path('work/rq1-v7/calibration')
names = ('source_audit.jsonl', 'evaluation.json', 'acceptance.json')
data = {name: (source / name).read_bytes() for name in names}
for name, content in data.items():
    path = target / name
    if path.exists() and path.read_bytes() != content:
        raise SystemExit(f'Preserving conflicting existing file: {path}')
for name, content in data.items():
    path = target / name
    if not path.exists():
        path.write_bytes(content)
print('Accepted audit and receipt installed; original responses preserved.')
PY
.venv/bin/python -m rq1.calibration status
```

The original acquisition procedure below is retained as history. It has already been executed once; do not rerun it.

After access and funding are checked, use the provided exact command for `ops.rq1_api_calibration run`. It acquires the twenty fixed stateless requests once, preserving errors and raw output. Return its D: ZIP and pause for the assistant's source-proof audit. All labels/proofs must pass; no automatic repairs, candidate search or threshold relaxation. See ASSESSMENT.md. A failure does not authorize opening already sealed main outcomes for instrument tuning.

## 4. Sealed development acquisition — next: Q-host technical inspection

The first technical-wrapper attempt returned exit 255 because its initial SSH connection to port 22 timed out. It did not transfer inputs or execute remote commands; the archive contains no GPU inspection receipt. Preserve that failed archive. Verify the existing VM is Running and use the current public IP shown by the console. Check connectivity before retrying the same technical wrapper. This failure does not justify changing the frozen corpus, Q, selector or assessor. [Redacted failure record](../docs/audits/2026-10-30-q-host-connection-blocked/checks.json).

The exact Q-input bundle is accepted, the assessor has passed, and the user returned screenshots confirming its local acceptance receipt verifies (`accepted: true`, `n: 20`, both cohorts pass). Keep the current VM address and account balance private. The Nebius resource estimate and balance are checked in its console separately from API credits.

Start the existing H100 in Nebius only for this technical checkpoint and wait for Running. Check the current console address; if it has changed, use that address in the command. On the existing laptop's Ubuntu terminal:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git pull --ff-only origin main
bash ops/rq1_q_vm_inspect.sh CURRENT_VM_PUBLIC_IP
```

This wrapper checks the exact accepted archive/checksum locally and remotely, transfers it using the existing `~/.ssh/nebius_rq1` key, updates the existing VM checkout, preserves any conflicting v7 inputs, and invokes only `ops.rq1_q_handoff inspect` in the existing `.venv-q`. It retains installed packages and cached weights. It checks the GPU, disk headroom, source contracts, tokenizer audit and CPU capability proofs without loading original Q or sending an assessor request. Available receipts and logs are returned even when inspection blocks; no input or model retry is performed.

After it returns, **Stop the VM in the Nebius console and verify Stopped**, then return `rq1-q-vm-inspection-*.zip` from **D:\Dissertation-RQ1\exports**. If it errors before an export is created, return the error and stop the VM. The wrapper does not control the console's VM power state. Return the GPU-host inspection before the query command below.

The Q host intentionally has no assessor calibration directory: its doctor's `ready: false` may reflect that absent assessment receipt. For this separated checkpoint, the required result is technical readiness, including the top-level `q-vm-inspection.json`. Calibration stays on the laptop, and its accepted result does not replace the GPU inspection.

Only after the Q host inspection is accepted, run the supplied command for:

```text
ops.rq1_collect query --split development --exports work/rq1-v7/sealed-exports
```

This uses original Q once on the six U/F inputs, with private native/Python logs and safe progress counts. Return **only its summary**, not the sealed archive. Mechanically checksum/transfer the full unopened development archive to the laptop, then stop the VM in the Nebius console. The assistant provides exact commands at the handoff; do not open generated queries.

On the accepted laptop, run the supplied command for:

```text
ops.rq1_collect slice --split development --exports /mnt/d/Dissertation-RQ1/exports
```

Return its safe summary only. Each input uses a fresh Docker/Scala worker. Infrastructure failures pause and retain attempts; three total infrastructure attempts are allowed. Semantic misses are not retried for a preferred result. Any necessary diagnostic exposure must be declared, preserving the original logs and its blinding consequences.

## 5. Sealed main acquisition — after development apparatus checks

The acquisition freeze and exact stage environments remain fixed. Main Q requires the complete receipted development Q stage. Main slicing additionally requires completed development slicing without unresolved infrastructure/mapping failures. These gates do not require a favourable adequacy result.

Collect twenty-four main Q inputs on the inspected H100 through `ops.rq1_collect query --split main`, transfer its full unopened archive to the laptop, stop the VM, then run `ops.rq1_collect slice --split main` locally. Return only safe summaries/hashes while assessment is pending. No case replacement, output-based source/selector tuning or repeated Q attempts for a better answer. Raw archives remain outside this conversation until the release checkpoint.

A standalone `evidence_experiment visibility --split main --sealed` can compute structural tables into sealed storage without a grader. It does not establish semantic relationships or adequacy and should not be inspected during instrument development.

## 6. Release and assess development; freeze assessment

After accepted calibration, release development, issue packets, and prepare the stateless assessment requests. Run the same fixed API profile, import the immutable first grades and return the released artifacts. The assistant audits visible source correspondence and each required relationship, explaining every conclusion.

Analyze development and run `rq1.setup freeze`. Resolve apparatus/mapping failures; no minimum adequate count is required. The freeze binds current judging code/profile, calibration and actual development reports/environments. Return it before main release. The main Q/slice files may already exist sealed; this does not allow inspecting them early.

## 7. Release and assess main

Release main against the assessment freeze, issue its exact rendered packets, and grade using the same stateless profile. Return released artifacts for the assistant's U source-support audit. The main denominator remains twelve U cases; twelve repaired F controls are separate. Identical excerpts share one first judgment. Main observations do not change the frozen rubric, candidate, source population or selector.

## 8. Provisional report and actual delayed reassessment

Analyze main and freeze `rq1.assess reassessment-plan --split main`. Reassess the seeded 25% unique-packet subset, rounded up to at most six, at least 48 real hours after each initial grade. Use the same model/settings and keep primary grades unchanged. Then run consistency and finalize. No Q rerun is needed. If no packets were shown, report the delayed check as not applicable.

## 9. Report and archive

Read `rq1_report.md`, `analysis.json` and the four `rq1_*.csv` tables. Structural tables separately distinguish partial reference-line groups from complete groups and mark semantic support unassessed until audited. Report exact counts, retrieval yield A/12, conditional adequacy A/R, source/relationship findings, F outcomes and unresolved-case identification bounds. Those bounds are not confidence intervals.

Archive exact sources/maps, Git commit, both freezes, seals, stage environments, calibration history, all raw queries/slices/attempts, requests/responses, source audits and delayed records on D:. Exclude API credentials and SSH private keys. State the small synthetic sample, reused anchors, remaining operation gaps, limited blinding, hosted-model drift and AI-only validation limits.
