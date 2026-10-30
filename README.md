# RQ1 evidence adequacy audit

Original pretrained **LLMxCPG-Q** generates CPGQL, **Joern** retrieves excerpts, and a separate stateless AI assessor evaluates visible justification. A later source-informed AI audit checks support. This is an **RQ1-only**, claim-conditioned case study. No independent human annotation, detector D, training, transformation experiment or population accuracy is claimed.

The active implementation is **rq1-v7**, with public assessor task **rq1-excerpt-v3** and new outputs in `work/rq1-v7`. Preserve all v5/v6 evidence. Three development blocks and twelve main blocks remain enrolled, each with U/F sources: six development and twenty-four main primary Q/slice runs. Two unused blocks, R15 and R17, now supply assessor-only source anchors; they do not enter the main denominator or Q census.

## Current action: fresh laptop CPU checkpoint

V1 and v2 assessor calibration failed. [The v3 amendment](docs/RQ1_V3_AMENDMENT_2026-10-30.md) repairs the interface and anchor design, declares one GPT-6 Astra API candidate, and separates sealed acquisition from grading. The original Q checkpoint/settings and all thirty experiment C inputs are unchanged. Source dependency references were improved before any Q output. New stage-scoped receipts must be collected; do not relabel v6 receipts.

Keep Nebius stopped. Run only this checkpoint in your existing D-backed Ubuntu-24.04 terminal:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh
```

Return the new `local-attempt-*.zip` from **D:\Dissertation-RQ1\exports**, then pause. This checks 34 source witnesses, thirty Q prompt lengths, both real selector fixtures and thirty experiment source graphs; it prepares twenty ungraded assessor requests and freezes acquisition. It needs no API key, paid inference or running VM. Large caches and exports use D:. The existing D-backed WSL environment holds the project and compiler outputs.

## Subsequent checkpoints

After CPU acceptance, API access preparation and sealed Q acquisition can proceed independently. API billing is separate from Nebius. One fixed assessor attempt contains twelve reused-development anchors and eight fresh held-out response checks; all twenty labels and later proof audits must pass, with cohorts reported separately. The candidate has not been shown to pass. No automatic candidate search, answer repair or preferred-response retry is allowed.

Q/Joern outputs remain unopened until release. Seals are hash inventories, not access control. Public progress summaries show counts and archive hashes; raw queries, slices and worker logs stay inside unopened archives. Full main assessment additionally requires the completed development audit and assessment freeze.

Read [RUNBOOK.md](rq1/RUNBOOK.md), [PROTOCOL.md](rq1/PROTOCOL.md), [ASSESSMENT.md](rq1/ASSESSMENT.md), [READINESS.md](rq1/READINESS.md), and [source references](rq1/SOURCE_REFERENTS.md). Historical v1/v2 records remain in `docs/`; their old commands are superseded.

## Developer verification

Python 3.11 or 3.12, Linux LP64:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m rq1.setup verify
```

Tests use explicitly labelled synthetic records in temporary directories. They are not calibration or experiment observations. Reports distinguish selected/context/absent reference lines, semantic relationship support, initial judgments, confirmed adequacy, repaired controls and uncertainty. Structural line visibility does not establish semantic sufficiency.

Original pipeline reference: [QCRI LLMxCPG](https://github.com/qcri/llmxcpg). Selector/reconstruction adaptations are documented. GPL-3.0; see LICENSE and NOTICE.
