# RQ1 execution checkpoints

Use clean `main` and fresh `work/rq1-v3`. Preserve all earlier work. Execute **only the current checkpoint**, return its output, and pause. The assistant performs the delegated source/proof judgments and explains them. Empty forms and software simulations are never experiment results.

## 1. Laptop CPU checkpoint — run now

Keep Nebius stopped. In D-backed Ubuntu-24.04:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh
```

Expected: `RQ1_LOCAL_CPU_CHECKPOINT_OK`, 30 passing source witnesses, 12 **ungraded** calibration tasks, 30 tokenizer records, full selector fixtures and 30 structural Joern graph records. `readiness.json` distinguishes **technical_ready** from **ready**: full experiment readiness remains false while assessor calibration is pending. The script stops Docker and always creates a diagnostic ZIP in `D:\Dissertation-RQ1\exports`, including failures. CPU graph import can take several minutes; it prints progress. Return the ZIP and pause. No Q weights, experiment queries, grader calls or cloud resources are used.

Hugging Face files and exports explicitly use D:. The project/virtual environment are on the previously verified D-backed WSL disk. See [D_DRIVE_SETUP.md](D_DRIVE_SETUP.md).

## 2. Assessor calibration — after checkpoint 1 inspection

Follow [ASSESSMENT.md](ASSESSMENT.md). Configure an actual stateless assessor endpoint/model, retain its identity/settings and credentials privately, run the 12 dev-only tasks, and return responses. The assistant audits every proof against the source key and gives reasons. Only a successful `rq1.calibration accept` allows Q acquisition. No endpoint has been configured or assumed free. Keep the H100 stopped while preparing and checking these tasks.

This is evidence-assessor calibration, not detector calibration. Neither D nor a target classifier is used.

## 3. GPU transfer and doctor — after calibration acceptance

Package current `work/rq1-v3/config.json`, `token-audit.json`, the full `calibration` directory including response provenance, `joern-capability/readiness.json`, and development/main witness records. Include SHA256. Exact packaging/SCP commands will use the accepted files and current console IP. The previous uploaded archive is historical. Never transfer SSH private keys or API secrets. Archive paths remain relative to the repo; credentials/profile are not required by Q.

Start the H100 only at this checkpoint. Update `~/rq1-project` to current clean `main`, install the pinned GPU environment, verify the input archive checksum, extract it preserving paths, and run:

```bash
set -euo pipefail
.venv-q/bin/python -m rq1.setup verify
.venv-q/bin/python -m rq1.setup doctor --profile gpu --work work/rq1-v3/gpu-doctor
```

Return the doctor output and pause **before Q weights are downloaded/loaded**. The CPU Joern receipt is transferred; Docker is not needed on the Q host. See [Nebius handoff](../docs/NEBIUS_RQ1_GUIDE.md).

## 4. Six development Q inputs — after GPU doctor acceptance

Inside tmux on the VM:

```bash
set -euo pipefail
.venv-q/bin/python -m evidence_experiment query --split development 2>&1 | tee work/rq1-v3/development/query-command.log
.venv-q/bin/python -m rq1.setup status --split development
```

Expected: six terminal records, real Q model-session metadata and query receipt. A device/load error leaves pending inputs. Return logs on failure. Download/checksum-verify the whole development directory, runtime files and current config/CPU/calibration receipts, then stop the VM. Pause for inspection before slicing.

## 5. Development Joern, stateless grades and source audit — on CPU

Use the accepted local environment and downloaded development directory; preserve its lock.

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment slice --split development
.venv/bin/python -m evidence_experiment packets --split development
.venv/bin/python -m rq1.assess prepare --split development
```

Each input/retry starts a fresh Docker/Scala process. An infrastructure failure saves an attempt and pauses; return logs before resuming the same command. Three attempts total are allowed. Semantic misses are retained without result-seeking retries.

Grade the issued requests with the calibrated profile, import immutable initial responses, and return the actual artifacts for the assistant's source-support audit, following [ASSESSMENT.md](ASSESSMENT.md). No minimum adequate count is required. Optional later corrections are secondary.

## 6. Development report and pre-main freeze

After initial grades and U source audits are complete:

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment analyze --split development
.venv/bin/python -m rq1.setup freeze --split development
```

Freeze recomputes judgments/provenance and locks source/code, policy, calibrated assessor, CPU/GPU stage environments and receipts. Repair unresolved apparatus/mapping failures consistently, retaining old attempts. Genuine retrieval misses remain valid. Development may remain provisional for its delayed check; main need not wait 48 hours for development consistency. Return the freeze and report before main.

## 7. Main Q on H100, then laptop slices

Transfer the accepted freeze and current inputs, preserve the development Q environment and use clean `main`. On the VM, after the restart checkpoint:

```bash
set -euo pipefail
.venv-q/bin/python -m evidence_experiment query --split main 2>&1 | tee work/rq1-v3/main/query-command.log
.venv-q/bin/python -m rq1.setup status --split main
```

Expected: 24 primary U/F query records. Download and verify the whole main directory, then stop the VM. Return output and pause. On the accepted laptop environment, after inspection:

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment slice --split main
.venv/bin/python -m evidence_experiment packets --split main
.venv/bin/python -m rq1.assess prepare --split main
```

Grade via the frozen stateless assessor; return responses and source audit forms. The assistant provides source correspondence/support judgments with detailed reasoning. No case replacement, flow change, source truncation or selector tuning based on main outputs is allowed.

## 8. Provisional report and real delayed consistency

```bash
set -euo pipefail
.venv/bin/python -m evidence_experiment analyze --split main
.venv/bin/python -m rq1.assess reassessment-plan --split main
```

Return the report and frozen subset. At or after each deadline, at least 48 hours after the original response, run/import the second stateless requests using the same profile. Preserve the first grades and raw provenance. Do not backdate anything. No shown packets makes this check explicitly not applicable.

## 9. Final report and archive

After the delayed responses are imported:

```bash
set -euo pipefail
.venv/bin/python -m rq1.assess consistency --split main
.venv/bin/python -m evidence_experiment finalize --split main
```

Read `rq1_report.md`, the four `rq1_*.csv` tables and `analysis.json`. They separate enrolled/retrieved denominators, initial grades, source confirmation, acquisition/assessment uncertainty, F checks, visibility, relationships and later corrections. Identification bounds are not confidence intervals.

Archive exact Git commit, sources/maps/references, config/freeze, calibration (public/private/proofs), CPU receipts, every query/session/slice/attempt/worker log, stage package requirements, issued requests/raw responses, source audits, delayed plan/grades and reports to D:. Preserve unsuccessful attempts. Exclude credentials/private SSH keys. The dissertation must state the bounded synthetic-case scope and AI-assisted validation limits.
