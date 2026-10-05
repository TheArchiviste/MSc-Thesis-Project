"""Build a pinned, line-mapped Juliet pilot without using graph output.

This intentionally supports only the four reviewed single-file cases in spec.json.
Unexpected upstream edits fail closed instead of silently changing the cohort.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "spec.json"
OUTPUT = ROOT / "generated"
LEAKS = re.compile(r"CWE\d+|(?:^|\W)(?:bad|good|FLAW|FIX)(?:\W|$)", re.IGNORECASE)


def _strip_comment(line: str, in_block: bool) -> tuple[str, bool]:
    """Remove comments in the reviewed C subset, retaining source line identity."""
    out = []
    i = 0
    quoted = None
    while i < len(line):
        if in_block:
            end = line.find("*/", i)
            if end == -1:
                return "".join(out), True
            i = end + 2
            in_block = False
        elif quoted:
            out.append(line[i])
            if line[i] == "\\" and i + 1 < len(line):
                i += 1
                out.append(line[i])
            elif line[i] == quoted:
                quoted = None
            i += 1
        elif line.startswith("/*", i):
            in_block = True
            i += 2
        elif line.startswith("//", i):
            break
        else:
            if line[i] in ("'", '"'):
                quoted = line[i]
            out.append(line[i])
            i += 1
    return "".join(out), in_block


def _function(lines: list[str], name: str) -> list[tuple[str, int]]:
    start = next((i for i, line in enumerate(lines)
                  if re.match(r"^(?:static\s+)?void\s+" + re.escape(name) + r"\s*\(", line)), None)
    if start is None:
        raise ValueError(f"Missing reviewed function {name}")
    depth = 0
    opened = False
    result = []
    for i in range(start, len(lines)):
        line = lines[i]
        result.append((line, i + 1))
        depth += line.count("{") - line.count("}")
        opened |= "{" in line
        if opened and depth == 0:
            return result
    raise ValueError(f"Unclosed reviewed function {name}")


def _render(source: str, control: str, arm: str) -> tuple[str, list[int | None]]:
    lines = source.splitlines()
    prefix = lines[:next(i for i, line in enumerate(lines) if line == "#ifndef OMITBAD")]
    directives = [(line, i + 1) for i, line in enumerate(prefix)
                  if line.startswith(("#include ", "#define "))]
    bad_name = next(re.search(r"^void\s+([^ (]+)\(", line).group(1)
                    for line in lines if re.search(r"^void\s+[^ (]+_bad\(", line))
    selected = bad_name if arm == "U" else control
    body = _function(lines, selected)
    body[0] = (re.sub(r"^(?:static\s+)?void\s+[^ (]+\s*\(\s*\)",
                      "void case_entry(void)", body[0][0]), body[0][1])
    result: list[str] = []
    mapping: list[int | None] = []
    in_block = False
    for line, upstream_line in directives + body:
        clean, in_block = _strip_comment(line, in_block)
        if clean.strip():
            result.append(clean.rstrip())
            mapping.append(upstream_line)
    if in_block:
        raise ValueError("Unclosed comment")
    for line in ("", "int main(void)", "{", "    case_entry();", "    return 0;", "}"):
        result.append(line)
        mapping.append(None)
    generated = "\n".join(result) + "\n"
    if LEAKS.search(generated):
        raise ValueError(f"Label leakage in generated {arm} source")
    return generated, mapping


def prepare() -> list[dict]:
    specification = json.loads(SPEC.read_text(encoding="utf-8"))
    for name, expected in specification["support_sha256_lf"].items():
        actual = hashlib.sha256((ROOT / "upstream" / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Pinned support changed: {name}")
    OUTPUT.mkdir(exist_ok=True)
    manifest = []
    for case in specification["cases"]:
        source = (ROOT / "upstream" / case["source_file"]).read_text(encoding="utf-8")
        source_lines = source.splitlines()
        # Hash raw LF-normalized text as a second, portable integrity check.
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source_hash != case["upstream_sha256_lf"]:
            raise ValueError(f"Pinned source changed: {case['source_file']}")
        rendered = {}
        maps = {}
        for arm in ("U", "control"):
            code, mapping = _render(source, case["control"], arm)
            path = OUTPUT / f"{case['case_id']}_{arm}.c"
            path.write_text(code, encoding="utf-8")
            (OUTPUT / f"{case['case_id']}_{arm}.map.json").write_text(
                json.dumps({"source_file": case["source_file"],
                            "source_sha256": source_hash, "upstream_line_for_generated_line": mapping},
                           indent=2) + "\n", encoding="utf-8")
            rendered[arm] = path.name
            maps[arm] = mapping
        referent = {"elements": [], "relations": case["relations"],
                    "mechanism": case["mechanism"], "reference_basis": "source_and_control",
                    "control_upstream_lines": case["control_upstream_lines"]}
        for element in case["elements"]:
            upstream = element["upstream_lines"]
            if not all(1 <= line <= len(source_lines) for line in upstream):
                raise ValueError(f"Bad source lines in {case['case_id']}: {upstream}")
            mapped = [i + 1 for i, original in enumerate(maps["U"]) if original in upstream]
            if len(mapped) != len(upstream):
                raise ValueError(f"Unmapped mechanism lines in {case['case_id']}: {upstream}")
            referent["elements"].append({**element, "lines": mapped})
        manifest.append({
            "case_id": case["case_id"], "cluster_id": case["cluster_id"], "cwe": case["cwe"],
            "sources": {"U": rendered["U"]}, "referent": referent,
            "provenance": {"repository": specification["upstream_repository"],
                           "commit": specification["upstream_commit"],
                           "path": case["upstream_path"],
                           "blob_sha": case["upstream_blob_sha"],
                           "local_sha256": source_hash},
            "control_source": rendered["control"],
            "line_maps": {arm: f"{case['case_id']}_{arm}.map.json"
                          for arm in ("U", "control")},
            "witness": {"expected_asan": case["expected_asan"],
                        "stdin": case["stdin"], "benign_stdin": case.get("benign_stdin")}
        })
    (OUTPUT / "cases.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in manifest),
        encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(f"Prepared {len(prepare())} baseline cases")
