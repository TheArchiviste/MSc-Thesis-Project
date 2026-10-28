#!/usr/bin/env bash
# CPU-only installation and source checks. No Docker pulls or model downloads.
set -euo pipefail
ulimit -c 0
cd "$(dirname "${BASH_SOURCE[0]}")/.."

python3 - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit("Use Ubuntu-24.04 with Python 3.12 for this local preparation.")
PY

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
rq1_python="$PWD/.venv/bin/python"
"$rq1_python" - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit("Existing .venv is not Python 3.12; preserve it and report this error.")
PY
"$rq1_python" -m pip install --no-cache-dir -r rq1/requirements-local.txt
"$rq1_python" -m pip install --no-cache-dir --no-deps -e .
"$rq1_python" -m rq1.setup verify
if [[ ! -f work/rq1-config.json ]]; then
    "$rq1_python" -m rq1.setup init
fi

for rq1_split in development main; do
    if [[ ! -f "work/rq1/$rq1_split/witness_validation.jsonl" ]]; then
        "$rq1_python" -m rq1.setup validate --split "$rq1_split"
    fi
done

"$rq1_python" - <<'PY'
import json
import platform
from pathlib import Path
from evidence_experiment.locks import git_provenance, require_witnesses
from evidence_experiment.schema import load_cases
from rq1.setup import status

root = Path("work/rq1")
lines = ["# Local CPU preparation", "", f"Python: {platform.python_version()}",
         f"Platform: {platform.platform()}", f"Project commit: {git_provenance()['commit']}", "",
         "| Split | Cases/blocks | U/F sources | Current witnesses | Q records | Slice records |",
         "|---|---|---|---|---|---|"]
summaries = []
for split in ("development", "main"):
    work = root / split
    require_witnesses(work, load_cases(Path("rq1") / f"{split}.jsonl"))
    item = status(split, work)
    summaries.append(item)
    lines.append(f"| {split} | {item['cases']}/{item['blocks']} | "
                 f"{item['planned_U'] + item['planned_F']} | PASS | "
                 f"{item['queries_recorded']} | {item['slices_recorded']} |")
lines += ["", "PASS means sources compile, U produces its expected sanitizer error, F runs cleanly, "
          "and required benign checks pass. Existing witness files are preserved and checked against current sources/plans.",
          "", "This script does not download models, pull Docker images, generate Q queries, or start Joern.",
          "Compiler witnesses are preparation evidence, not excerpt-adequacy results."]
report = "\n".join(lines) + "\n"
(root / "local-preparation.md").write_text(report, encoding="utf-8")
(root / "local-preparation.json").write_text(json.dumps(summaries, indent=2) + "\n")
exports = Path("/mnt/d/Dissertation-RQ1/exports")
if exports.is_dir():
    (exports / "local-preparation.md").write_text(report, encoding="utf-8")
print(report)
PY
"$rq1_python" -m pip freeze > work/rq1/local-pip-freeze.txt
gcc --version > work/rq1/local-gcc-version.txt
