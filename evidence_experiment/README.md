# RQ1 acquisition and reporting CLI

Follow the [active runbook](../rq1/RUNBOOK.md) and [v3 amendment](../docs/RQ1_V3_AMENDMENT_2026-10-30.md). The current implementation is rq1-v7, public assessor task rq1-excerpt-v3. Earlier commands and transformed/classifier experiments are outside this route.

Q/Joern acquisition requires `--sealed`, an independent acquisition freeze and the correct actual stage environment. The Q host additionally requires its inspection receipt. Use `ops.rq1_collect` for safe progress and unopened archive export. Return summaries/hashes while assessment is pending; do not upload raw sealed output to develop the instrument.

`release` binds accepted calibration to sealed acquisition. Main release also requires the completed development assessment freeze. `packets`, `analyze` and `finalize` require that release. `visibility --sealed` computes structural line/prerequisite tables without implying semantic support or opening results for instrument development.

All empirical inputs have one U and one F primary run. Main has twelve U cases and twelve separate controls. The stateless first grade, source-support confirmation, uncertainty and later consistency/corrections remain distinct. Unit simulations never populate empirical outputs.
