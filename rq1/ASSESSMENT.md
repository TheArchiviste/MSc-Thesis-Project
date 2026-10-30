# RQ1 assessment procedure — rq1-excerpt-v3

See [the v3 amendment](../docs/RQ1_V3_AMENDMENT_2026-10-30.md) for the failed-attempt history and fixed decisions. Implementation rq1-v7 uses a separate stateless GPT-6 Astra API request for each excerpt. The assistant performs the later source-informed proof audit and explains its reasoning. No human ratings are claimed.

## Public task and response

The grader receives the rubric and permitted assumptions once, one hypothesis claim, the contract hash, and one readable numbered excerpt. Provider-native structured output supplies the schema once. No reference, expected label, case/arm/cohort label, witness result, earlier response or conversation history is sent. Requests persist and hash the evidence-before-verdict key order. Each response must provide the exact required fields and integer visible citations; unsupported conditions/uniqueness are checked locally after decoding. No format/content repair or preferred-response retry is allowed.

The API adapter omits temperature and uses high reasoning, 25,000 maximum output tokens including reasoning, Standard tier, `store=false` and no tools. The immutable raw envelope and actual token usage are preserved. These settings are unrelated to the unchanged Q settings. Account access, funding and model suitability are not assumed.

## Current checkpoint

Run only the laptop CPU checkpoint in RUNBOOK.md and return the ZIP. It creates twenty **ungraded** anchors with a frozen private source key. Keep the full diagnostic ZIP and private key away from the excerpt grader. Never paste an API key into chat or commit it.

## Later: read-only access, then one paid acquisition

After CPU acceptance, the assistant provides the exact access command. Enter the API key privately through the terminal; the value stays in `OPENAI_API_KEY`, outside files and command history. `ops.rq1_api_calibration access` performs a GET-only selected-model lookup and returns a receipt. It establishes neither paid-generation permission nor grading quality. Return that receipt and pause.

Only after that checkpoint and budget review, run `ops.rq1_api_calibration run`. It refuses a prior acquisition, requires clean committed code and matching access/profile receipts, and issues the exact twenty frozen requests once. It exports an explicit allowlist of public/private calibration artifacts, raw responses/errors, profile/provenance and a summary under D:\Dissertation-RQ1\exports. It does not package API credentials. Return that ZIP and pause. All twenty answers are acquired without inspecting/tuning between cohorts. Refusal, truncation or transport failure stops the attempt and preserves records; there is no automatic alternative candidate.

The assistant audits each actual response after its real timestamp, against the source key but citing visible support. All twenty strict labels and proofs must pass, with 12 reused-development and 8 fresh-held-out checks reported separately. An acceptance file cannot be manufactured from a ready flag. A passed screen is not an accuracy estimate; five source mechanisms and related packets remain a small, curated screen.

## Real excerpt assessment and release

The acquisition seal stays immutable. `evidence_experiment release --split development` requires accepted calibration and creates the separate assessment lock. Then `packets` and `rq1.assess prepare` issue the exact rendered excerpts, deduplicated and spaced where possible. The same API profile/settings grade the initial requests. The assistant fills later source audits for U excerpts; missing evidence cannot be supplied from its reference knowledge to promote a failed first grade. F initial outcomes are reported separately.

After real development analysis, `rq1.setup freeze` locks the assessment implementation and profile. Main release additionally requires that freeze. Later reference-informed corrections are secondary and retain separate real timestamps/reasons; they never overwrite initial responses.

## Delayed consistency

Freeze the seeded 25% subset of unique main packets, rounded up, at most six. Request a second independent stateless grade no sooner than each packet's actual initial timestamp plus 48 hours. Same identity/settings, raw provenance and unchanged first grades are required. This measures within-assessor consistency only. No repeated Q inference or invented timestamps are used.
