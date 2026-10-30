> Historical v4 type/client repair. Both repaired selector fixtures subsequently passed. Current diagnostics and the verified recovery route are documented in [the v5 recovery record](RQ1_CPU_RECOVERY_2026-10-30.md).

# Joern compatibility repair — rq1-v4

The returned laptop archive `local-attempt-20261030T130250Z-b0Nzl9.zip` reports a failed v3 CPU apparatus checkpoint. Its code/corpus hashes match the published v3 contract. All 15 witness pairs (30 U/F sources) passed with matching source/witness hashes, all 30 tokenizer records fit, and 12 calibration packets were prepared without grading.

Joern started and imported the local capability fixture. Its source, sink, flow and interacters queries succeeded. The backward helper failed to compile because the union of `Path.elements` and identifiers had static type `List[AstNode]`, while the pinned data-flow extension accepts CFG sink nodes. This is an apparatus failure, not an inadequate main excerpt. No main graph checks, Q queries or actual grades were collected.

The server returned `success=true` while putting a structured Scala E008 diagnostic on stdout. The old client therefore tried to parse that compiler text as line coordinates, misclassifying the failure as mapping error. The retained [raw fixture trace](audits/2026-10-30-joern-fix/observed-fixture-failure.json) records both defects.

## Repair

- Narrow the sink union using a typed `collect` to `io.shiftleft.codepropertygraph.generated.nodes.CfgNode`, then run the backward data-flow call. Keep `cpg.all` as the unrestricted source argument; the pinned API accepts a generic source traversal.
- Recognize structured Scala compiler and runtime diagnostics on stdout even when the envelope reports success. Preserve raw stdout, including ANSI color codes, for evidence. Strip color only for diagnostic recognition and simple value parsing. Ordinary values containing words such as ERROR and normal warnings remain valid.
- Replay the real failed response in regression tests: it now fails at `slice_exec`, before line parsing. This is a software replay, not a new real Joern execution.
- Issue a new `rq1-v4` contract and fresh `work/rq1-v4`; preserve failed v3 receipts and all original source files. Scientific selection, references, rubric, assessor requirements, Q weights/settings and corpus C/maps/witness plans remain unchanged.

The type repair was checked against the exact Joern v4.0.667 source:

- [language/package.scala](https://github.com/joernio/joern/blob/v4.0.667/dataflowengineoss/src/main/scala/io/joern/dataflowengineoss/language/package.scala), blob `7101c872177faca4448e5771f139de4fb7bfb184`: CFG-constrained extension conversion.
- [language/ExtendedCfgNode.scala](https://github.com/joernio/joern/blob/v4.0.667/dataflowengineoss/src/main/scala/io/joern/dataflowengineoss/language/ExtendedCfgNode.scala), blob `c38214b69c2e5e8d814c6ebfee18c479f685ba9a`: CFG sink iterator and generic source argument.

A real v4 laptop Joern rerun is still required. Workspace tests do not establish that this fixed helper executes successfully on the user's Docker engine. The checkpoint remains blocked until local and interprocedural fixtures and all 30 structural imports pass. Do not relax these gates or start paid inference to bypass the failure.

## Next checkpoint

In the D-backed Ubuntu terminal, update clean `main` and run `bash rq1/local_acceptance.sh` following [RUNBOOK.md](../rq1/RUNBOOK.md). The script creates fresh v4 work, uses CPU, stops Joern and emits a diagnostic ZIP on D: even on failure. Return that ZIP and pause. Keep Nebius stopped; calibration grading and Q acquisition remain pending.
