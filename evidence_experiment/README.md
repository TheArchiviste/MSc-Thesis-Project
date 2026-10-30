# RQ1 acquisition and reporting

Only `query`, `slice`, `packets`, `analyze` and `finalize` are supported. Both
`python -m evidence_experiment` and `llmxcpg` use this interface. See the
[runbook](../rq1/RUNBOOK.md) for the ordered checkpoint commands.

Each input has one immutable primary run ID derived from implementation,
case, U/F arm and source hash. Queries and slices resume pending IDs only.
Source/witness/policy locks, complete per-stage Python environments, linked
real Q sessions and file-hash receipts protect downstream analysis. Semantic
misses are retained; infrastructure retries are capped at three and pause.

Packet construction rejects inconsistent source coordinates. Initial and
final assessments require an honest AI identity, actual timestamp, visible
citations, reasons and explicit context/limitations fields. Each shown U
also needs a supported yes/no/uncertain mechanism correspondence decision.

Reports retain all enrolled U cases in the denominator. Failed mapping and
unresolved infrastructure remain uncertain; terminal semantic retrieval
failures are inadequate. F controls, initial false adequacy, source-line
visibility and uncertainty bounds remain separate. `analyze` can write a
provisional report. `finalize` additionally requires the frozen 25% delayed
assessment after at least 48 hours. Neither command invents judgments.
