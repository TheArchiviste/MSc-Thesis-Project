# Four-case Juliet pilot: corpus and mechanism referent

This is a **small source-defined pilot**, not a result for RQ1–RQ3. It includes
four vulnerable C functions from Juliet 1.3 and one relevant fixed function per
case. The upstream mirror is pinned at
`arichardson/juliet-test-suite-c@f88433e3443648a17671398797a04ea1f8e1a274`.
The original path, Git blob SHA, and SHA-256 of the LF-normalized copy are in
`spec.json`. The copied Juliet sources and support files are public domain
under the notice in `upstream/LICENSE`.

Run from the repository root:

```bash
python juliet_pilot/prepare.py
python juliet_pilot/witness.py
python -m evidence_experiment verify --manifest juliet_pilot/generated/cases.jsonl --work /tmp/juliet-pilot-check
```

`prepare.py` extracts only the pinned functions, strips Juliet comments and
identifying function names, keeps required includes and macros, adds a tiny
driver, and emits one line map per generated file. The map array's position
is the 1-based generated line; its value is the 1-based upstream line, or
`null` for driver lines. The source copy is retained separately for audit.
`cases.jsonl` contains U-only baseline records usable by
`evidence_experiment`; controls and witnesses are separate. No Q, Joern, or
D output is read to select cases or define the referent.

| Case | Source mechanism | Trigger | Fixed control | Expected ASan |
| --- | --- | --- | --- | --- |
| J121-size-01 | 10-byte stack allocation, 40-byte copy on this platform | none | correct allocation size | dynamic-stack-buffer-overflow |
| J121-index-01 | unchecked upper bound of input index into 10-int array | stdin `11\n` | bound checked | stack-buffer-overflow |
| J122-nul-01 | 11-byte C string copied into 10-byte heap allocation | none | terminator space allocated | heap-buffer-overflow |
| J416-free-01 | string read through freed pointer | none | no free before read | heap-use-after-free |

The index case also has a benign input (`5\n`) that must run without an
ASan finding. The witness script compiles U and the fixed control separately
with GCC `-std=gnu11 -O0 -g -fsanitize=address -fno-pie -no-pie`, checks the
specific sanitizer class, and writes `generated/witnesses.jsonl`. It disables
leak reporting because Juliet's goodG2B UAF control intentionally leaves its
object live. These are observed finite executions, not proofs for all inputs
or all compilers. The compiler and flags appear in the witness output.

## Source-first adequacy rubric

The proposed referent was derived from the original vulnerable function,
Juliet's source annotations and good variant, and the executable witness
before viewing any Q/Joern/D output. `spec.json` records the mechanism
elements, directed relationships, source line numbers, and aligned control
lines; `generated/cases.jsonl` adds U coordinates through the line map.
This is one initial annotation and still needs an independent second human
review before treating it as adjudicated ground truth.

For a blinded evidence slice, record:

1. **Adequate** only if the excerpt itself supports the required capacity,
   range, or lifetime facts, the violating operation, and the causal relation
   listed for that case. Cite visible lines and explicitly state the relation
   and any execution assumption. Equivalent evidence may use a different
   route through the source; matching the target line list is not mandatory.
2. **Inadequate** when the excerpt positively lacks a necessary fact or
   supports only a flaw label, a CWE name, a sink call, or an ASan class without
   the causal relation.
3. **Uncertain** when reachability, aliases, external helper behavior, a
   relevant bound, or the relation cannot be resolved from the excerpt.
   Do not infer missing source from case knowledge. For the UAF case, a call
   to `printLine(data)` requires the helper's string-read semantics; the
   retained `io.c` gives that definition.

After the blinded decision, a separate adjudicator checks that the cited
relationship actually matches this source-first referent. For the index case,
the input to `atoi`, one-sided guard, array extent and indexed write must
jointly explain why 11 reaches an invalid index. For the size case, account
for the number of bytes allocated and copied. For the NUL case, include the
terminator in `strcpy`'s extent. For UAF, identify the same allocation,
release, and later read. The control lines are a cross-check on the mechanism,
not evidence shown to the blinded assessor.

The sample has one baseline flow variant per chosen flaw and no paired TM/TN
perturbations. It was selected by mechanism diversity and reproducible ASan
witnesses, not randomly sampled. It does not yet establish Q miss rates,
evidence adequacy rates, paired loss, or diagnostic attribution. For a real
baseline run, freeze calibration before running all four U cases through
Q → Joern → D, retaining misses and abstentions. Independent human review
is needed before claiming adequacy results. Construct and validate matched
target/control transforms for the later paired analysis.

## Pipeline integration smoke run without human ratings

```bash
python juliet_pilot/prepare.py
python juliet_pilot/smoke.py --work /tmp/juliet-pilot-smoke
```

This invokes the pinned pipeline's **dummy Q mode**, then the experiment's
query, slice, reconstruction, detector, packet, and analysis stages for all
four U cases, three repeats each. A simulated Joern interface returns the
entire source instead of evaluating CPGQL, and a simulated D interface emits
a fixed score. The raw stage traces and report are written to the work
directory. Rerunning the same command resumes without duplicating runs.
`smoke_summary.json` records the local execution.

The analysis receives empty assessment and adjudication files, so all four
baseline adequacy decisions remain **uncertain**. The fixed verdicts are test
values, not detector misses. This smoke run checks wiring, source handling,
line reconstruction, output bookkeeping, and unresolved-review behavior.
It does not test Q's query quality, Joern's graph semantics, D's predictions,
threshold calibration, or the research questions. Run the actual Q/Joern/D
configuration on suitable hardware to test those stages; human review can
remain pending while preserving the raw stage outputs.
