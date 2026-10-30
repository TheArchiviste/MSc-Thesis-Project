# RQ1 assessment procedure

The assistant performs the delegated source reasoning and proof audits. No human reviewers are required. The first excerpt grade uses a **separate stateless request**, because an assistant that has already read a referent cannot honestly claim to have forgotten it.

`assessment_protocol.py` contains the public rubric, assumptions and response schema. `judge.py` sends exactly two messages: a fixed system task and one numbered excerpt/claim. There is no conversation history, private reference, arm label, case ID, witness result or sibling excerpt. The same service can still recognize familiar code; stateless requests cannot remove pretraining knowledge. Do not describe this as independent human validation.

## First checkpoint: prepare, without inference

`rq1/local_acceptance.sh` creates 12 packets under `work/rq1-v3/calibration/public` and the source answer key under `private`. The diagnostic ZIP includes private material for the assistant's source audit. **Never send that whole ZIP, the private key, or the repository to the excerpt grader.** The CPU checkpoint does not contact an assessor endpoint.

## Next checkpoint: configure and calibrate the real assessor

After the CPU ZIP is inspected, configure a real OpenAI-compatible chat-completions service in an ignored work file, using `rq1/assessor.example.json` as its schema. Record the actual provider/model and available revision; use `not_exposed` if a service does not expose it. Do not invent identity metadata or use the evaluated query model as the evidence assessor. Keep API credentials in the named environment variable, never a committed file. Endpoint/access and any associated resource cost must be established at that checkpoint; no service or free access is assumed by this repository.

The later commands, after the profile is configured, are:

```bash
.venv/bin/python -m rq1.judge run \
  --profile work/rq1-v3/assessor.json \
  --requests work/rq1-v3/calibration/public/requests.jsonl \
  --responses work/rq1-v3/calibration/responses.jsonl
.venv/bin/python -m rq1.judge import \
  --requests work/rq1-v3/calibration/public/requests.jsonl \
  --responses work/rq1-v3/calibration/responses.jsonl \
  --output work/rq1-v3/calibration/assessments.initial.jsonl
```

Return raw responses, imported grades and `source_audit.template.jsonl`. The assistant compares each actual response's reasoning against the source answer key, cites visible lines and records a detailed yes/no/uncertain proof audit in `source_audit.jsonl`. An expected label alone cannot pass. Then:

```bash
.venv/bin/python -m rq1.calibration accept
```

All 12 labels and proof audits must pass. No automatic content retries, JSON repairs, best-of-N choices or outcome-based removal are allowed. A failed/truncated response is retained. Transport errors may be diagnosed and resumed without changing completed responses. A failed instrument requires a recorded development-only protocol/assessor revision and fresh versioned calibration, with previous records preserved. Q acquisition remains blocked meanwhile.

## Real development and main excerpts

Once actual slices and packets exist, `rq1.assess prepare --split development` (or `main`) exports `assessment_requests.initial.jsonl`. Use the same configured profile and `rq1.judge run/import` pattern, with responses under that split and output `assessments.initial.jsonl`. Provenance binds request text, raw response, model/settings, timestamp and grade. An edited/orphan grade file is rejected.

Return actual grades, public packets, traces and `adjudications.template.jsonl`. The assistant uses the source referent to fill `adjudications.jsonl`: mechanism match, real audit time, and every required relationship's support, visible citations, allowed assumptions and explanation. The primary label is the first grade, conservatively confirmed by that audit; hidden facts cannot promote it.

Optional `assessments.final.jsonl` corrections have context `reference_informed`, a later timestamp, actual assessor identity, visible citations and `revision_reason`. They are reported separately and never substituted into primary results. They are not needed to manufacture agreement.

## Delayed consistency

`rq1.assess reassessment-plan` freezes the subset and exports `assessment_requests.second.jsonl` with per-packet deadlines. After each deadline, use the same profile to run/import responses into `assessments.second.jsonl`. Run `rq1.assess consistency`, then `evidence_experiment finalize`. Execution and import reject early responses; model/settings must match calibration. Second responses remain separate from the primary grade. A real 48-hour wait cannot be simulated by changing timestamps.
