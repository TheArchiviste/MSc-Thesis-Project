"""Bounded executable witness checks for curated source interventions.

These checks corroborate a documented flaw under specified inputs. They do not
prove semantic equivalence over all inputs or correctness of a mechanism map.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .schema import Case, append_jsonl, digest, read_jsonl


def _run(argv: list[str], *, cwd: Path, input_text: str = "", timeout: int = 20,
         env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        result = subprocess.run(argv, cwd=cwd, input=input_text, text=True,
                                capture_output=True,
                                timeout=timeout, check=False, env=env)
        return {"status": "ok", "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"status": "indeterminate", "error": str(exc)}


def _build_and_run(case: Case, arm: str, plan: dict[str, Any], base: Path,
                   workspace: Path) -> dict[str, Any]:
    source = (base / case.source_paths[arm]).resolve()
    binary = workspace / f"{arm}.bin"
    argv = [word.format(source=str(source), binary=str(binary)) for word in plan["build_argv"]]
    compile_result = _run(argv, cwd=base, timeout=plan.get("compile_timeout", 60))
    if compile_result["status"] != "ok":
        return {"compile": "indeterminate", "build": compile_result}
    if compile_result["exit_code"] != 0:
        return {"compile": "fail", "build": compile_result}
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:abort_on_error=1")
    benign = [_run([str(binary)], cwd=base, input_text=value,
                   timeout=plan.get("run_timeout", 10), env=env)
              for value in plan["benign_inputs"]]
    trigger = _run([str(binary)], cwd=base, input_text=plan["trigger_input"],
                   timeout=plan.get("run_timeout", 10), env=env)
    return {"compile": "pass", "build": compile_result,
            "benign": benign, "trigger": trigger}


def validate_witnesses(cases: list[Case], manifest: Path, plan_path: Path,
                       output: Path) -> list[dict[str, Any]]:
    plans = {row["case_id"]: row for row in read_jsonl(plan_path)}
    if len(plans) != len(read_jsonl(plan_path)):
        raise ValueError("Duplicate case_id in witness plan")
    results = []
    for case in cases:
        if not case.paired:
            if case.case_id in plans and plans[case.case_id].get("mode") == "baseline":
                row = validate_baseline(case, plans[case.case_id], manifest.parent)
                append_jsonl(output, row)
                results.append(row)
            continue
        if case.case_id not in plans:
            raise ValueError(f"Missing witness plan for paired case {case.case_id}")
        plan = plans[case.case_id]
        if (not plan.get("build_argv") or not isinstance(plan.get("benign_inputs"), list) or
                "trigger_input" not in plan or not plan.get("asan_class")):
            raise ValueError(f"Incomplete witness plan for {case.case_id}")
        if not plan["benign_inputs"] and not plan.get("benign_reason"):
            raise ValueError(f"Document why {case.case_id} has no benign execution")
        with tempfile.TemporaryDirectory(prefix="evidence-witness-") as temp:
            work = Path(temp)
            runs = {arm: _build_and_run(case, arm, plan, manifest.parent, work)
                    for arm in ("U", "TM", "TN")}
        base = runs["U"]
        checks: dict[str, str] = {}
        checks["compile"] = ("pass" if all(run["compile"] == "pass" for run in runs.values())
                             else "indeterminate" if any(run["compile"] == "indeterminate"
                                                         for run in runs.values()) else "fail")
        if checks["compile"] == "pass":
            expected = plan["asan_class"]
            def triggered(run, expected_class=expected):
                t = run["trigger"]
                return (t["status"] == "ok" and t["exit_code"] != 0 and
                        re.search(r"ERROR: AddressSanitizer:\s*" + re.escape(expected_class),
                                  t["stderr"]) is not None)

            checks["trigger"] = ("pass" if all(triggered(r) for r in runs.values())
                                 else "indeterminate" if any(r["trigger"]["status"] != "ok"
                                                             for r in runs.values()) else "fail")
            if not plan["benign_inputs"]:
                checks["benign_behavior"] = "not_applicable"
            elif any(b["status"] != "ok" for r in runs.values() for b in r["benign"]):
                checks["benign_behavior"] = "indeterminate"
            elif any("ERROR: AddressSanitizer:" in b["stderr"]
                     for r in runs.values() for b in r["benign"]):
                checks["benign_behavior"] = "fail"
            else:
                def signature(b):
                    # Runtime metadata may vary; preserve the diagnostic text.
                    stderr = re.sub(r"==\d+==", "==PID==", b["stderr"])
                    stderr = re.sub(r"\b0x[0-9a-fA-F]+\b", "0xADDR", stderr)
                    return b["stdout"], stderr, b["exit_code"]
                checks["benign_behavior"] = (
                    "pass" if all([signature(b) for b in r["benign"]] ==
                                  [signature(b) for b in base["benign"]]
                                  for r in (runs["TM"], runs["TN"])) else "fail")
        else:
            checks.update(trigger="indeterminate", benign_behavior="indeterminate")
        row = {"case_id": case.case_id, "checks": checks, "runs": runs,
               "benign_reason": plan.get("benign_reason"),
               "source_sha256": {arm: digest(case.sources[arm]) for arm in ("U", "TM", "TN")},
               "limits": "Finite input witnesses; source mapping and control matching need adjudication."}
        append_jsonl(output, row)
        results.append(row)
    return results


def validate_baseline(case: Case, plan: dict, base: Path) -> dict:
    """Real U/F witnesses; a clean fixed run is not a proof over all inputs."""
    if (not plan.get("build_argv") or not isinstance(plan.get("benign_inputs"), list)
            or "trigger_input" not in plan or not plan.get("asan_class")
            or not plan["benign_inputs"] and not plan.get("benign_reason")):
        raise ValueError(f"Incomplete baseline witness plan for {case.case_id}")
    with tempfile.TemporaryDirectory(prefix="rq1-witness-") as temp:
        runs = {arm: _build_and_run(case, arm, plan, base, Path(temp))
                for arm in case.sources if arm in ("U", "F")}
    compiled = all(r["compile"] == "pass" for r in runs.values())
    trigger = runs["U"].get("trigger", {})
    triggered = (trigger.get("status") == "ok" and trigger.get("exit_code", 0) != 0
                 and re.search(r"ERROR: AddressSanitizer:\s*" + re.escape(plan["asan_class"]),
                               trigger.get("stderr", "")) is not None)
    fixed = runs.get("F", {}).get("trigger", {})
    clean = (fixed.get("status") == "ok" and fixed.get("exit_code") == 0
             and "AddressSanitizer" not in fixed.get("stderr", "")
             and all(r.get("status") == "ok" and r.get("exit_code") == 0 and
                     "AddressSanitizer" not in r.get("stderr", "")
                     for r in runs.get("F", {}).get("benign", [])))
    benign = runs["U"].get("benign", [])
    return {"case_id": case.case_id, "mode": "baseline", "runs": runs,
            "witness_plan_sha256": digest(json.dumps(plan, sort_keys=True)),
            "build_argv": plan["build_argv"],
            "compiler": _run([plan["build_argv"][0], "--version"], cwd=base),
            "platform": platform.platform(), "asan_options": "detect_leaks=0:abort_on_error=1",
            "checks": {"compile": "pass" if compiled else "fail",
                       "trigger": "pass" if triggered else "fail",
                       "fixed": "pass" if clean else "not_applicable" if "F" not in runs else "fail",
                       "benign_behavior": ("pass" if all(r.get("status") == "ok" and r.get("exit_code") == 0 and
                          "AddressSanitizer" not in r.get("stderr", "") for r in benign)
                          else "fail") if benign else "not_applicable"},
            "source_sha256": {arm: digest(code) for arm, code in case.sources.items()},
            "expected_asan": plan["asan_class"],
            "limits": "Finite witness and source-based repair judgement, not independent validation or a general safety proof."}
