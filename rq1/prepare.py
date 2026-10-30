"""Reproduce the bounded, explicitly reviewed two-function Juliet corpus."""
from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import random
import re
from pathlib import Path

from .references import reference
from .source_tools import _function, _strip_comment, template_cluster

ROOT = Path(__file__).resolve().parent
EXCLUDED = {
    "sizeof": "On the evaluated LP64 ABI sizeof(pointer)==sizeof(int64_t)==8; this source does not establish the claimed overflow.",
    "sizeof-double": "On the evaluated LP64 ABI sizeof(pointer)==sizeof(double)==8; do not manufacture a 32-bit execution to retain it.",
}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def verify_selection(selection, root=ROOT):
    """Reproduce block order and source representatives from the retained census."""
    frame = (root / "frame_paths.txt").read_bytes()
    if hashlib.sha256(frame).hexdigest() != selection["frame_sha256"]:
        raise ValueError("Pinned source frame changed")
    blocks = {}
    families = set()
    for path in frame.decode().splitlines():
        family = template_cluster(path)
        families.add(family)
        block = family.removeprefix("CWE121-").removeprefix("CWE122-c-").removeprefix("CWE122-")
        cwe = "CWE121" if family.startswith("CWE121-") else "CWE122"
        blocks.setdefault(block, {}).setdefault(cwe, []).append(path)
    if len(blocks) != 20 or len(families) != 38:
        raise ValueError("Source frame must reproduce 38 families in 20 blocks")
    development = ["CWE131-copy", "CWE129", "CWE193-copy"]
    main = sorted(set(blocks) - set(development))
    random.Random(selection["seed"]).shuffle(main)
    for index, (block, row) in enumerate(zip(development + main, selection["cases"], strict=True)):
        members = {cwe: min(paths) for cwe, paths in blocks[block].items()}
        preferred = "CWE121" if index % 2 == 0 else "CWE122"
        cwe = preferred if preferred in members else next(iter(members))
        path = members[cwe]
        if block == "CWE129":
            path = next(p for p in sorted(blocks[block][cwe]) if "_fgets_41.c" in p)
        if (row["block"], row["cwe"], row["path"], row["members"], row["family_id"]) != (
                block, cwe, path, members, template_cluster(path)):
            raise ValueError(f"Selection is not reproducible: {row['case_id']}")
    return {"paths": len(frame.decode().splitlines()), "families": len(families), "blocks": len(blocks)}


def render(source, arm, control):
    lines = source.splitlines()
    names = re.findall(r"(?m)^(?:static\s+)?void\s+([^\s(]+)\s*\(", source)
    entry = next(n for n in names if n.endswith("_bad")) if arm == "U" else control
    sink = next(n for n in names if n.endswith("badSink")) if arm == "U" else next(
        n for n in names if n.endswith(control + "Sink"))
    prefix_end = next(i for i, line in enumerate(lines) if line == "#ifndef OMITBAD")
    selected = [(line, i + 1) for i, line in enumerate(lines[:prefix_end])]
    selected += _function(lines, sink) + _function(lines, entry)
    # Token replacements are limited to identifiers outside quoted literals.
    renames = {entry: "case_entry", sink: "case_sink"}
    for token in re.findall(r"\b\w+\b", "\n".join(line for line, _ in selected)):
        if re.search(r"bad|good|CWE\d", token, re.IGNORECASE) and token not in renames:
            renames[token] = f"buffer_{len(renames)}"
    output, mapping = [], []
    in_block = False
    for line, original in selected:
        clean, in_block = _strip_comment(line, in_block)
        parts = re.split(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''', clean)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: renames.get(m[0], m[0]), parts[i])
        clean = "".join(parts).rstrip()
        if not clean.strip():
            continue
        if re.search(r"\b(?:bad\w*|good\w*|CWE\d\w*)\b", clean, re.IGNORECASE):
            raise ValueError("Ground-truth label remains in source")
        if re.match(r"static\s+void\s+case_entry", clean):
            clean = clean.replace("static void", "void", 1)
        output.append(clean)
        mapping.append(original)
    return "\n".join(output) + "\n", mapping, renames




def reference_guide(manifests):
    """Render the same granular source reference used by machine-readable manifests."""
    text = ['# Source-grounded mechanism references', '',
            'Prepared before Q/Joern inference. AI-assisted source reasoning is supported by pinned Juliet sources, exact maps and finite witnesses; it is not independent human annotation or an excerpt-adequacy result.', '',
            'Each fact is separate from the relationships that must be justified. A visible fact line is descriptive evidence, not proof of sufficiency. Source-only mechanism and repair explanations must never enter the stateless grader request.', '']
    for split, cases in manifests.items():
        for case in cases:
            ref, cid = case['referent'], case['case_id']
            provenance = case['provenance']
            url = f"https://github.com/{provenance['repository']}/blob/{provenance['commit']}/{provenance['path']}"
            text += [f"## {cid} — {split}, {case['cluster_id']}", '', ref['mechanism'], '',
                     'Repair: ' + ref['repair'], '',
                     f"Actual overflowing object: **{ref['observed_storage_kind']}**. Upstream family: `{provenance['family_id']}`.",
                     f"[Prepared U]({case['sources']['U']}) · [Fixed F]({case['sources']['F']}) · [Pinned upstream]({url})", '',
                     '| Fact / role | U lines | Meaning |', '|---|---|---|']
            for fact in ref['elements']:
                text.append(f"| {fact['id']} / {fact['role']} | {', '.join(map(str, fact['lines']))} | {fact['meaning']} |")
            text += ['', '| Required relationship | Explanation |', '|---|---|']
            for relation in ref['relations']:
                text.append(f"| {relation['id']} | {relation['explanation']} |")
            text.append('')
    (ROOT / 'SOURCE_REFERENTS.md').write_text('\n'.join(text).rstrip() + '\n')


def prepare():
    if (ctypes.sizeof(ctypes.c_void_p), ctypes.sizeof(ctypes.c_int),
            ctypes.sizeof(ctypes.c_long)) != (8, 4, 8):
        raise ValueError("This corpus requires the documented LP64 ABI; use 64-bit Linux/WSL2")
    selection = json.loads((ROOT / "selection.json").read_text())
    verify_selection(selection)
    generated = ROOT / "generated"
    support = ROOT / "support"
    generated.mkdir(exist_ok=True)
    support.mkdir(exist_ok=True)
    for name in ("std_testcase.h", "std_testcase_io.h", "io.c", "LICENSE"):
        original = support / name
        if hashlib.sha256(original.read_bytes()).hexdigest() != selection["support_sha256"][name]:
            raise ValueError(f"Pinned support source changed: {name}")
    (generated / "driver.c").write_text("void case_entry(void);\nint main(void) { case_entry(); return 0; }\n")
    manifests = {"development": [], "main": [], "assessor_holdout": []}
    plans, ledger = [], []
    for row in selection["cases"]:
        source = (ROOT / "upstream" / (row["case_id"] + ".c")).read_text()
        if sha(source) != row["normalized_sha256"]:
            raise ValueError(f"Pinned LF-normalized upstream source changed: {row['case_id']}")
        item = {**row, "normalized_sha256": sha(source)}
        if row["block"] in EXCLUDED:
            ledger.append({**item, "status": "excluded_before_inference", "reason": EXCLUDED[row["block"]]})
            continue
        split = "development" if row["split"] == "development" else "main"
        if split == "main" and len(manifests[split]) == 12:
            if row['case_id'] in {'R15', 'R17'}:
                split = 'assessor_holdout'
            else:
                ledger.append({**item, "status": "reserve_not_enrolled"})
                continue
        control = "goodB2G" if row["block"] == "CWE129" else "goodG2B"
        paths, maps = {}, {}
        for arm in ("U", "F"):
            code, mapping, renames = render(source, arm, control)
            path = generated / f"{row['case_id']}_{arm}.c"
            path.write_text(code)
            maps[arm] = {"upstream_line_for_generated_line": mapping, "identifier_map": renames,
                         "source_sha256_lf": sha(source), "generated_sha256": sha(code)}
            (path.with_suffix(".map.json")).write_text(json.dumps(maps[arm], indent=2) + "\n")
            paths[arm] = "generated/" + path.name
        ref = reference(row, (ROOT / paths["U"]).read_text())
        ref["rq1_witness_required"] = True
        ref["counterpart"] = control
        ref["upstream_cwe"] = row["cwe"]
        case = {"case_id": row["case_id"], "cluster_id": "juliet-buffer-" + row["block"],
                "cwe": row["cwe"], "sources": paths, "referent": ref,
                "provenance": {"repository": "arichardson/juliet-test-suite-c", "commit": selection["upstream_commit"],
                               "family_id": row["family_id"],
                               "path": row["path"], "upstream_blob_sha": row["upstream_blob_sha"], "normalized_sha256": sha(source)},
                "line_maps": {a: paths[a].replace(".c", ".map.json") for a in paths},
                "rq1_witness_required": True}
        manifests[split].append(case)
        kind = ref["observed_storage_kind"]
        expected = ("heap-buffer-overflow" if kind == "heap" else
                    "dynamic-stack-buffer-overflow" if row["block"] in ("CWE131-copy", "CWE193-copy", "CWE193-loop") or not (row["block"].startswith("CWE806") or row["block"].startswith("src-")) else "stack-buffer-overflow")
        plans.append({"case_id": row["case_id"], "mode": "baseline",
                      "build_argv": ["gcc", "-std=gnu11", "-O0", "-g", "-fno-omit-frame-pointer", "-fsanitize=address", "-fno-builtin-memcpy", "-fno-pie", "-no-pie", "-I", "support", "{source}", "generated/driver.c", "support/io.c", "-o", "{binary}"],
                      "trigger_input": "11\n" if row["block"] == "CWE129" else "",
                      "benign_inputs": ["5\n"] if row["block"] == "CWE129" else [],
                      "benign_reason": "Unconditional documented invalid access; fixed counterpart is the clean execution check.",
                      "asan_class": expected})
        ref["witness_plan_sha256"] = sha(json.dumps(plans[-1], sort_keys=True))
        ref["rq1_benign_required"] = bool(plans[-1]["benign_inputs"])
        ledger.append({**item, "status": split + "_prepared", "claim": ref["review_claim"],
                       "reason": ref["mechanism"], "counterpart": control})
    for split, cases in manifests.items():
        (ROOT / (split + ".jsonl")).write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in cases))
    for name, records in (("witness_plan.jsonl", plans), ("selection_ledger.jsonl", ledger)):
        (ROOT / name).write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in records))
    references = [{"case_id": case["case_id"], "split": split,
                   "block": case["cluster_id"], "referent": case["referent"],
                   "provenance": case["provenance"], "line_maps": case["line_maps"]}
                  for split, cases in manifests.items() for case in cases]
    (ROOT / "referents.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in references))
    with (ROOT / "enrollment.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "block", "cwe", "status", "reason"],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in writer.fieldnames} for r in ledger)
    reference_guide(manifests)
    return manifests


if __name__ == "__main__":
    data = prepare()
    print("Source preparation only — no Q, Joern or adequacy results.")
    for split, cases in data.items():
        print(f"{split}: {len(cases)} cases, {sum(len(c['sources']) for c in cases)} U/F inputs")
