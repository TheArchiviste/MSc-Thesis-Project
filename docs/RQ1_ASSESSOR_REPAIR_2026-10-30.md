# First assessor calibration: failed instrument and versioned repair

The H100 session at commit 6f02208769d2aeee6711dc04f7f3453237576fba loaded the pinned BF16 assessor and returned twelve nontruncated responses. Startup did not time out. The archive/member hashes, exact public requests, response associations, model identity and fixed settings were verified. Original Q has not run.

Calibration is **failed**. Ten responses parse as JSON; all twelve use uppercase labels where the importer requires lowercase; several cite strings instead of integer line numbers; and all relationship lists are empty. Two contain bare L-prefixed tokens and are invalid JSON. Zero valid assessments were imported. Even informally reading the declared labels gives five matches to the key and seven disagreements. This is diagnostic reading of development anchors, not accepted grades or population accuracy. No raw response was repaired.

The [complete twelve-row audit](audits/2026-10-30-assessor-v1/evaluation.json) records each expected/declared label, visible source citations, reasoning, format status and the archive/raw-response hashes. Examples include D01 F: forty bytes copied into forty bytes is not overflowing merely because no extra check appears; D02 U: the initialization loop bound does not constrain the separate input-indexed write; D03 incomplete: the missing alias-selection assignment cannot be invented.

The old task interface contributed to format failures. It named decisions in uppercase while accepting only lowercase, presented an unassessed template instead of an explicit typed schema, and did not clearly specify integer citations or required relationship explanations. These defects must be fixed alongside the reasoning instructions. The model's substantive mistakes remain failures.

The old shutdown warning masked the original import error, reproduced as ValueError: Assessment is missing or not terminal. Its process-group existence check could include dead/zombie entries and did not wait for workers after the launcher exited. The saved logs contain no process-state snapshot, so the actual live-worker state cannot be established retrospectively. The operational fix waits for live owned workers and preserves the primary error alongside cleanup diagnostics. The VM itself still needs the console Stop action.

## Predeclared revision

Implementation rq1-v6 uses public task rq1-excerpt-v2. It supplies an explicit lowercase verdict enum, integer citation arrays, permitted premise categories, packet identity and nonempty adequate relationship explanations. Missing facts belong in missing_context/limitations, rather than fabricated uncited premise rows. General instructions clarify actual capacity/access comparison, a possible input permitted by visible acquisition/guards, and the prohibition on choosing an omitted guard or alias alternative.

No case-specific worked answer, private source key, sibling packet or prior response enters the grader. Q, its settings/prompt, selector, renderer, corpus, referents and witness plans are unchanged. The assessor checkpoint/settings and all-twelve-labels-plus-source-proofs threshold are unchanged. Plan **one v2 calibration attempt** on the same development-anchor construction before any Q/main output. If it fails, preserve it and pause for a separate instrument/design decision; no automatic further prompt/model search. Report the development history and limits of reusing calibration anchors.

## Current CPU command

**Historical procedure:** the fresh v6 CPU checkpoint and VM inspection subsequently passed, followed by the one predeclared v2 GPU attempt. That calibration failed. See [the result](RQ1_ASSESSOR_V2_RESULT_2026-10-30.md). Keep the VM stopped and do not repeat the commands in this record. The account above preserves what was declared before the v2 responses were observed.

The sealed content contract includes the changed assessor code/protocol. V5 receipts cannot be relabelled as v6. Run fresh witnesses, tokenizer and actual Joern conformance into work/rq1-v6, preserving work/rq1-v5 and the cached VM weights. Historical v4-to-v5 recovery is not a v6 migration route.

Keep the VM stopped. In D-backed Ubuntu-24.04:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
bash rq1/local_acceptance.sh
```

Return its new local-attempt ZIP from D:\Dissertation-RQ1\exports and pause. This uses laptop CPU, Docker and cached tokenizers; no model weights or paid inference are needed. After acceptance: prepare the v6 transfer, inspect the VM, run the predeclared v2 calibration once and audit its actual responses before Q. Retain cached assessor weights to avoid an unnecessary download.
