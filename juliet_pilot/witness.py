"""Reproduce the four source-defined flaws and clean controls with GCC ASan."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from prepare import OUTPUT, ROOT, prepare

FLAGS = ("-std=gnu11", "-O0", "-g", "-fno-omit-frame-pointer",
         "-fsanitize=address", "-fno-pie", "-no-pie")
ASAN_ERROR = re.compile(r"ERROR: AddressSanitizer: ([\w-]+)")


def _execute(binary: Path, stdin: str) -> dict:
    env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1"}
    run = subprocess.run([str(binary)], input=stdin, text=True, capture_output=True,
                         env=env, timeout=15, check=False)
    error = ASAN_ERROR.search(run.stderr)
    return {"returncode": run.returncode, "asan_error": error.group(1) if error else None}


def witness() -> list[dict]:
    cases = prepare()
    compiler = subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0]
    results = []
    with tempfile.TemporaryDirectory(prefix="juliet-pilot-") as temp:
        for case in cases:
            row = {"case_id": case["case_id"], "compiler": compiler, "flags": FLAGS,
                   "asan_options": "detect_leaks=0:abort_on_error=1", "runs": {}}
            for arm in ("U", "control"):
                binary = Path(temp) / f"{case['case_id']}_{arm}"
                source = OUTPUT / case["sources"].get(arm, case["control_source"])
                command = ["gcc", *FLAGS, "-I", str(ROOT / "upstream"),
                           str(source), str(ROOT / "upstream" / "io.c"),
                           "-o", str(binary)]
                compile_run = subprocess.run(command, capture_output=True, text=True,
                                             check=False)
                if compile_run.returncode:
                    raise RuntimeError(f"{case['case_id']} {arm}: {compile_run.stderr}")
                row["runs"][arm] = _execute(binary, case["witness"]["stdin"])
                if arm == "U" and case["witness"]["benign_stdin"] is not None:
                    row["runs"]["U_benign"] = _execute(
                        binary, case["witness"]["benign_stdin"])
            expected = case["witness"]["expected_asan"]
            if row["runs"]["U"]["asan_error"] != expected or row["runs"]["U"]["returncode"] == 0:
                raise AssertionError(f"{case['case_id']}: expected {expected}, got {row['runs']['U']}")
            for clean in ("control", "U_benign"):
                if clean in row["runs"] and row["runs"][clean] != {
                        "returncode": 0, "asan_error": None}:
                    raise AssertionError(f"{case['case_id']} {clean}: {row['runs'][clean]}")
            row["status"] = "pass"
            results.append(row)
    (OUTPUT / "witnesses.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in results),
        encoding="utf-8")
    return results


if __name__ == "__main__":
    for result in witness():
        print(result["case_id"], result["runs"], result["status"])
