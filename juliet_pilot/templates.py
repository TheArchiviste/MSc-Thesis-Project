"""Juliet flaw-template clusters and a census of what the suite can supply.

Juliet multiplies one flaw template across input sources (fgets, rand, ...),
data types (char, int, ...), allocation styles (alloca, declare) and flow
variants (_01 ... _84). Near-identical programs must share a cluster so they
cannot cross analysis/calibration splits or count as independent pairs.

    python juliet_pilot/templates.py census --root /path/to/juliet-test-suite-c
    git -C juliet ls-tree -r --name-only HEAD testcases > files.txt
    python juliet_pilot/templates.py census --file-list files.txt --json

The grouping is a heuristic over Juliet's file names. Record the version used
in the protocol; it decides the number of independent clusters available.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

FILE_NAME = re.compile(r"^(CWE\d+)_[^/]*?__(.+?)_(\d{2})([a-e]?)\.(c|cpp)$")
TYPES = ("wchar_t", "char", "unsigned_int", "int64_t", "int", "long", "short",
         "struct", "class", "twoIntsStruct")
SOURCES = ("fgets", "fscanf", "rand", "large", "connect_socket", "listen_socket",
           "max", "min", "negative", "zero", "ten")
ALLOCATION_STYLES = ("alloca", "declare")
COPY_SINKS = ("memcpy", "memmove", "ncpy", "cpy")
# CWEs in the LLMxCPG scope that Juliet C/C++ contains, and closely related
# buffer CWEs (children of CWE-787/CWE-125) that Juliet labels more specifically.
SUPPORTED = ("CWE121", "CWE122", "CWE190", "CWE415", "CWE416")
RELATED = ("CWE124", "CWE126", "CWE127")
CROSS_FUNCTION_SINGLE_FILE = (41, 42, 44, 45)


def parse(path: str) -> dict | None:
    match = FILE_NAME.match(path.strip().rsplit("/", 1)[-1])
    if not match:
        return None
    cwe, functional, flow, part, ext = match.groups()
    return {"cwe": cwe, "functional_variant": functional, "flow_variant": int(flow),
            "multi_file_part": part or None, "ext": ext}


def _strip(tokens: str, words: tuple[str, ...]) -> str:
    return re.sub(rf"(^|_)({'|'.join(map(re.escape, words))})(?=_|$)", r"\1", tokens)


def template_of(cwe: str, functional_variant: str, *, merge_copy_sinks: bool = True) -> str:
    """Collapse source, type and allocation variants into one template id."""
    t = _strip(functional_variant, TYPES)
    t = _strip(t, SOURCES)
    t = _strip(t, ALLOCATION_STYLES)
    if merge_copy_sinks:
        t = re.sub(rf"(^|_)({'|'.join(COPY_SINKS)})(?=_|$)", r"\1copy", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return "-".join([cwe, *[part for part in t.split("_") if part]])


def template_cluster(upstream_path: str, *, merge_copy_sinks: bool = True) -> str:
    """Cluster id for a Juliet test-case path, e.g. 'CWE121-CWE129'."""
    parsed = parse(upstream_path)
    if parsed is None:
        raise ValueError(f"Not a Juliet test-case file name: {upstream_path}")
    return template_of(parsed["cwe"], parsed["functional_variant"],
                       merge_copy_sinks=merge_copy_sinks)


def census(paths, *, cwes=SUPPORTED, exts=("c",), merge_copy_sinks: bool = True) -> dict:
    functional: dict[str, set[str]] = defaultdict(set)
    flows: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    multi: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        parsed = parse(path)
        if not parsed or parsed["cwe"] not in cwes or parsed["ext"] not in exts:
            continue
        cwe = parsed["cwe"]
        template = template_of(cwe, parsed["functional_variant"],
                               merge_copy_sinks=merge_copy_sinks)
        functional[cwe].add(parsed["functional_variant"])
        flows[cwe][template].add(parsed["flow_variant"])
        if parsed["multi_file_part"]:
            multi[cwe].add(template)
    by_cwe = {}
    for cwe in sorted(flows):
        templates = flows[cwe]
        by_cwe[cwe] = {
            "functional_variants": len(functional[cwe]),
            "templates": len(templates),
            "templates_with_single_file_cross_function_variants": sum(
                bool(set(v) & set(CROSS_FUNCTION_SINGLE_FILE)) for v in templates.values()),
            "templates_with_multi_file_variants": len(multi[cwe]),
            "flow_variants_available": sorted(set().union(*templates.values())),
            "template_ids": sorted(templates),
        }
    return {"settings": {"cwes": list(cwes), "extensions": list(exts),
                         "merge_copy_sinks": merge_copy_sinks},
            "total_templates": sum(row["templates"] for row in by_cwe.values()),
            "by_cwe": by_cwe}


def _paths(args) -> list[str]:
    if args.file_list:
        return Path(args.file_list).read_text(encoding="utf-8").splitlines()
    root = Path(args.root)
    return [str(p.relative_to(root)) for p in (root / "testcases").rglob("*")
            if p.suffix in (".c", ".cpp")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("census", help="count templates and flow variants per CWE")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", help="Juliet checkout containing testcases/")
    source.add_argument("--file-list", help="one Juliet path per line")
    run.add_argument("--include-related", action="store_true",
                     help=f"also count {', '.join(RELATED)}")
    run.add_argument("--include-cpp", action="store_true")
    run.add_argument("--keep-copy-sinks", action="store_true",
                     help="treat memcpy/memmove/strcpy/strncpy templates as distinct")
    run.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = census(_paths(args), cwes=SUPPORTED + (RELATED if args.include_related else ()),
                    exts=("c", "cpp") if args.include_cpp else ("c",),
                    merge_copy_sinks=not args.keep_copy_sinks)
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        print()
        return 0
    print(f"{'CWE':<8}{'variants':>9}{'templates':>10}{'41/42/44/45':>13}{'multi-file':>12}")
    for cwe, row in result["by_cwe"].items():
        print(f"{cwe:<8}{row['functional_variants']:>9}{row['templates']:>10}"
              f"{row['templates_with_single_file_cross_function_variants']:>13}"
              f"{row['templates_with_multi_file_variants']:>12}")
    print(f"total templates: {result['total_templates']}  settings: {result['settings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
