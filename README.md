# RQ1 evidence adequacy audit

Original pretrained **LLMxCPG-Q** generates CPGQL, **Joern** retrieves excerpts, and a separate stateless AI assessor evaluates visible justification. A later source-informed AI audit checks support. This is an **RQ1-only**, claim-conditioned case study. No independent human annotation, detector D, training, transformation experiment or population accuracy is claimed.

The active implementation is **rq1-v7**, with public assessor task **rq1-excerpt-v3** and new outputs in `work/rq1-v7`. Preserve all v5/v6 evidence. Three development blocks and twelve main blocks remain enrolled, each with U/F sources: six development and twenty-four main primary Q/slice runs. Two unused blocks, R15 and R17, now supply assessor-only source anchors; they do not enter the main denominator or Q census.

## Current action: install accepted assessor receipt; inspect the Q host

V1 and v2 assessor calibration failed. [The v3 amendment](docs/RQ1_V3_AMENDMENT_2026-10-30.md) repairs the interface and anchor design, declares one GPT-6 Astra API candidate, and separates sealed acquisition from grading. The original Q checkpoint/settings and all thirty experiment C inputs are unchanged. Source dependency references were improved before any Q output. Fresh v7 CPU receipts and the v3 assessor calibration are now accepted; no v6 receipts were relabelled.

The fresh v7 laptop CPU checkpoint is accepted. The returned archive verifies 34 U/F source witnesses, 30 fitting Q prompts, both real selector fixtures, all 30 source graphs and the acquisition freeze. See [the checkpoint record](docs/RQ1_V7_CPU_CHECKPOINT_2026-10-30.md) and [checks](docs/audits/2026-10-30-v7-cpu-accepted/checks.json). Assessor access/calibration and Q acquisition remain pending; no experiment outcome is inferred from technical readiness.

The one declared Astra attempt completed all twenty requests and strict imports. The separate source-proof audit accepts 20/20 labels and 20/20 proofs: 12/12 reused-development and 8/8 fresh held-out response checks. See [the complete audit](docs/RQ1_ASSESSOR_V3_RESULT_2026-10-30.md) and [acceptance records](docs/audits/2026-10-30-assessor-v3-accepted/checks.json). Recorded usage estimates $1.53385 including cache writes; the provider billing dashboard is authoritative. This is a small curated instrument screen, not population accuracy or human validation.

Install the accepted audit/evaluation/receipt using [runbook checkpoint 3](rq1/RUNBOOK.md), against the unchanged local raw responses. No further API calibration request is needed. The Q-input archive `rq1-q-inputs-20261030T204312205833Z.tgz` is already verified: all 167 files match accepted CPU evidence. Keep Nebius stopped while preparing its next transfer/technical-inspection checkpoint; obtain the current console IP, status and running-cost/balance information. No Q output or experiment slice has yet been collected.

## Subsequent checkpoints

The fixed assessor screen has passed, with cohorts reported separately. API usage and Nebius resource billing remain distinct. No automatic candidate search, answer repair or preferred-response retry is allowed; all original failures and first v3 answers remain preserved. Q-host inspection, six sealed development Q inputs and local slicing are next; full main assessment still requires the development audit and assessment freeze.

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
