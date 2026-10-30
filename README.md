# RQ1 evidence adequacy audit

This repository now contains only the dissertation's RQ1 experiment: the released **LLMxCPG-Q** generates CPGQL, **Joern** retrieves a source excerpt, and an explicitly labelled **AI-assisted single assessor** evaluates whether that excerpt justifies the documented flaw. The executable detector, calibration, training, transformation experiments and their old commands have been removed. Earlier versions remain in Git history.

The corpus contains **3 development blocks and 12 main blocks**, with one vulnerable U and one repaired F input per block. There is one primary run per input: 6 development and 24 main Q/slice runs. Fixed controls are reported separately from the 12 main U cases.

Start with [execution steps](rq1/RUNBOOK.md), [protocol](rq1/PROTOCOL.md), [implementation contract](rq1/REFERENCE_CONTRACT.md) and [current readiness](rq1/READINESS.md). The source-grounded reference is explained in [SOURCE_REFERENTS.md](rq1/SOURCE_REFERENTS.md).

## Next checkpoint: laptop CPU

Keep the rented GPU VM stopped. In the D-backed **Ubuntu-24.04** terminal:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh
```

Return the generated ZIP under `D:\Dissertation-RQ1\exports` before continuing. The script checks all 30 compiler/sanitizer witnesses, downloads only the small pinned tokenizer, and exercises the complete selector on a synthetic fixture using CPU Docker. It does not download Q weights or generate experiment queries. A failure still produces a diagnostic ZIP. Existing `work/rq1` data are preserved; this implementation uses `work/rq1-v2`.

## Developer checks

From a Linux source checkout with Python 3.11 or 3.12:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m rq1.setup verify
```

Tests use explicitly isolated simulations. They establish software behavior, not real GPU/Joern experiment success. No adequacy results have been collected. A main run is blocked until real development inference, assessed excerpts, current CPU receipts and a pre-main freeze pass.

The query prompt follows the [QCRI release](https://github.com/qcri/llmxcpg); the selector and context reconstruction are an explicitly documented adaptation, not a claim of bit-for-bit reproduction. GPL-3.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
