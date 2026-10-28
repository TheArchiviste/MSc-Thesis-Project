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
| Laptop runtime | Ubuntu-24.04/WSL2 and Python 3.12.3 verified; latest screenshot shows 7.8 GiB WSL RAM (6.6 GiB available), 4 GiB swap; physical RAM is 15.8 GiB |
| Bulk storage and Python | Registered Ubuntu-24.04 base path on `D:\Dissertation-RQ1\wsl\Ubuntu-24.04` verified; user confirms Docker bulk storage is on D: |
| CPU preparation | User log at commit `272b82e` confirms all 3 development and 12 main current U/F witness pairs pass on the laptop; Q/slice records remain zero |
| Prompt-token audit | Implemented; the pinned tokenizer has not been downloaded/run here |
| Joern | Missing v4.0.0 image tag replaced with a verified official digest; bounded startup/import helper ready; actual laptop import/memory acceptance pending |
| Original Q | Pinned config and GPU preflight ready; no weights downloaded or inference performed |
| Assessment | Explicit AI-assisted mode, initial/final forms, matching and delayed consistency tools ready; no excerpt judgements yet |
| Main freeze | Not issued; main acquisition is blocked pending real development and its assessment |

Checked-in raw compiler logs in [validation/](validation/) are from the workspace CPU. The separately returned laptop `local-prepare.log` confirms the same 15 current U/F checks pass on the user's CPU. These are finite witnesses, not a proof that F is safe for all possible inputs. No GPU has been rented and no paid service or university allocation has been started.

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

Next: run `bash rq1/local_joern.sh` on the updated branch in Ubuntu-24.04, return its D: export ZIP and pause. Joern, token auditing and reporting use the local CPU. No adequacy proportion can be reported until actual Q/Joern outputs have been assessed. The final pipeline emits a Markdown report plus case and element CSV tables, alongside raw JSONL/provenance.
