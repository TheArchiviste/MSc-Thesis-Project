# Execution readiness — 28 October 2026

**Source preparation is complete. Real Q generation, real Joern extraction and excerpt-adequacy assessment have not run.**

| Checkpoint | Actual status |
|---|---|
| Core frame | 176 retained C `_41` paths; 38 families in 20 related blocks; selection reproduced from seed 20261027 |
| Development | 3 disjoint blocks; 3 U + 3 F prepared and validated |
| Main | 12 disjoint blocks; 12 U + 12 F prepared and validated |
| Source exclusions | 2 LP64 `sizeof` blocks, excluded before inference |
| Reserves | 3 ordered blocks, not enrolled or inferred |
| Real compilation and ASan | All 30 sources compile; all 15 U trigger their expected ASan class; all 15 F execute cleanly |
| Additional benign check | D02 U/F run cleanly for input 5; U crashes for 11; F rejects 11 |
| Software checks | 93 tests pass; Ruff passes for experiment code, RQ1 tooling and new tests |
| Laptop runtime | Screenshots confirm WSL2, working Ubuntu/Docker integration, 15.8 GiB RAM, Python 3.14.4 and 14.6 GiB free on C:; D: has 849 GB free by user report |
| Bulk storage and Python | `D:\Dissertation-RQ1` selected; dedicated Ubuntu 24.04/Python 3.12 and Docker data placement on D: await user execution/verification |
| Prompt-token audit | Implemented; the pinned tokenizer has not been downloaded/run here |
| Joern | Configuration and bounded real-CPG probe ready; laptop Docker works, but the Joern image/import/memory test has not run |
| Original Q | Pinned config and GPU preflight ready; no weights downloaded or inference performed |
| Assessment | Explicit AI-assisted mode, initial/final forms, matching and delayed consistency tools ready; no excerpt judgements yet |
| Main freeze | Not issued; main acquisition is blocked pending real development and its assessment |

These compiler checks used this workspace CPU, not the user's laptop or university resources. Raw logs, build flags, compiler versions and platform metadata are in [validation/](validation/). They support the specified executions and do not prove F safe for all possible inputs. No GPU has been rented and no paid service or university allocation has been started.

## Decisions and reasoning

1. **Run RQ1 only.** D and training add no evidence to this baseline adequacy question. They remain outside the execution; the RQ1 CLI blocks `all`/`detect` for these manifests.
2. **Use one case per generator block.** Allocation twins do not become independent cases. Entire development blocks are reserved, preventing their siblings from entering main analysis.
3. **Exclude `sizeof` and `sizeof-double` on LP64.** The chosen pointer and int64/double sizes are eight bytes, so those selected sources do not establish the advertised under-allocation on this ABI. A manufactured 32-bit execution would change the evaluated setup rather than validate the intended Linux run.
4. **Use `fgets` instead of a socket for development CWE129.** The stdin variant retains the missing upper-bound mechanism and gives reproducible, bounded witnesses: 11 is invalid and 5 is benign. This source-only choice precedes all model outputs.
5. **Keep `-fno-builtin-memcpy` in witness compilation.** R13's compiler-expanded copy initially produced ASan's generic `unknown-crash`, with a 100-byte write against a 50-byte heap object. This flag preserves the operation while letting the ASan interceptor report `heap-buffer-overflow` directly. The source supplied to Q/Joern is unchanged.
6. **Report actual storage separately from upstream CWE.** Several CWE122 generators allocate the source on the heap but overflow a local stack destination. Main has ten stack-write and two heap-write mechanisms; it is not a balanced storage comparison.
7. **Label delegated assessment honestly.** The assistant prepares source references and will judge actual excerpts with detailed reasons under `assessment-mode assistant`. This is AI-assisted single-assessor evaluation. Label concealment and a later consistency check do not establish independent human validation.
8. **Use the laptop for CPU work first.** Preparation, token auditing, Joern and reporting are CPU tasks. The unchanged original Q checkpoint needs a separate GPU acceptance check. A cluster is a fallback requiring another checkpoint, not a prerequisite for the next local check.

## Per-case source validation

| Split | Case | Block | Actual overflow | U ASan class | F witness |
|---|---|---|---|---|---|
| Development | D01 | CWE131-copy | Stack | dynamic-stack-buffer-overflow: pass | pass |
| Development | D02 | CWE129 | Heap | heap-buffer-overflow: pass | pass |
| Development | D03 | CWE193-copy | Stack | dynamic-stack-buffer-overflow: pass | pass |
| Main | R02 | CWE805-ncat | Stack | dynamic-stack-buffer-overflow: pass | pass |
| Main | R03 | CWE806-loop | Stack | stack-buffer-overflow: pass | pass |
| Main | R04 | src-copy | Stack | stack-buffer-overflow: pass | pass |
| Main | R05 | CWE806-copy | Stack | stack-buffer-overflow: pass | pass |
| Main | R06 | dest-cat | Stack | dynamic-stack-buffer-overflow: pass | pass |
| Main | R07 | CWE131-loop | Heap | heap-buffer-overflow: pass | pass |
| Main | R08 | CWE806-snprintf | Stack | stack-buffer-overflow: pass | pass |
| Main | R09 | src-cat | Stack | stack-buffer-overflow: pass | pass |
| Main | R10 | CWE805-snprintf | Stack | dynamic-stack-buffer-overflow: pass | pass |
| Main | R12 | CWE806-ncat | Stack | stack-buffer-overflow: pass | pass |
| Main | R13 | CWE805-copy | Heap | heap-buffer-overflow: pass | pass |
| Main | R14 | CWE193-loop | Stack | dynamic-stack-buffer-overflow: pass | pass |

The reasoned mechanism and repair for every case are in [SOURCE_REFERENTS.md](SOURCE_REFERENTS.md), with original/prepared line coordinates and source links. [referents.jsonl](referents.jsonl) is the machine-readable oracle; [enrollment.csv](enrollment.csv) records every block decision.

Next: complete [D_DRIVE_SETUP.md](D_DRIVE_SETUP.md), return the registered WSL path, Python/memory/Docker outputs and Docker's disk-image location, and pause before repository installation or Joern pulls. Corpus validation, token auditing, Joern and reporting will use the local CPU. No adequacy proportion can be reported until actual Q/Joern outputs have been assessed. The final pipeline emits a Markdown report plus case and element CSV tables, alongside raw JSONL/provenance.
