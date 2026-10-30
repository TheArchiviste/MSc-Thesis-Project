> Historical procedure, superseded by [the v3 amendment](RQ1_V3_AMENDMENT_2026-10-30.md) and [active runbook](../rq1/RUNBOOK.md). Do not execute these older assessor/VM commands.

> Optional Token Factory route. The current continuation uses the [existing VM](RQ1_VM_ONLY_CHECKPOINTS.md), without a Token Factory account or API key.

# CPU accepted; next checkpoint is assessor access

The returned `local-attempt-20261030T134928Z-PIK59P.zip` passes the complete CPU technical gate: clean e2b1c3f source, exact v5 contract, 30 source witnesses, 30 verified graph results, both real selector fixtures, the fresh diagnostic-return probe, tokenizer audit and 12 correct ungraded calibration tasks. Evidence summaries are in [the acceptance record](audits/2026-10-30-cpu-accepted/checks.json). `ready: false` correctly means assessor calibration is pending. No Q outputs or evidence grades have been collected.

The accepted scientific core, work directory and Python dependencies are unchanged. This checkpoint adds only an operations helper, tests and documentation outside the frozen core contract. Do not rerun the CPU scan or modify the accepted environment.

## Selected assessor

Use **Nebius Token Factory** with **Qwen/Qwen3-235B-A22B-Instruct-2507**. This is a separate instruction checkpoint for excerpt grading, not the evaluated fine-tuned Q. It supports the existing chat-completions interface and avoids another rented VM. The dated instruction variant gives a concrete model ID and ordinary text/JSON generation. Capability is still determined by the predeclared 12-anchor calibration and later source-proof audits; model size or provider descriptions do not establish judgment validity. Model familiarity, shared training material and AI-assisted reference/support audits remain limitations.

The official catalog checked on 30 October lists this model as active, with rates of $0.20 per million input tokens and $0.60 per million output tokens. The small calibration should cost well under $1 at those rates; that is an estimate, not a spending cap. This checkpoint itself sends only a model-list request, with no chat completion or generated tokens.

Token Factory documentation requires billing setup with a bank card during onboarding. Whether the existing $25 cloud balance applies to this service has not been verified. Check the balance and billing details shown in Token Factory; do not assume an account's GPU balance pays these API charges. No new deposit, card operation or inference purchase is performed by this helper.

Official sources:

- [Quickstart and API endpoint](https://docs.tokenfactory.nebius.com/quickstart).
- [API-key creation](https://docs.tokenfactory.nebius.com/api-reference/introduction).
- [Current model catalog](https://tokenfactory.nebius.com/api/public/models_info).
- [Billing and consumption](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new).

## Current step: API key and read-only preflight

1. Open [Nebius Token Factory](https://tokenfactory.nebius.com/) and inspect its billing/access state. It is a different interface from the VM console.
2. In **API keys**, select **Create API key** and name it `rq1-assessor`. Keep the value private; the command below asks for it with hidden input. A VM SSH key or cloud service-account token is not this API key.
3. Keep the H100 stopped. In the existing D-backed Ubuntu terminal, run:

```bash
set -euo pipefail
cd ~/projects/MSc-Thesis-Project
git fetch origin
git switch main
git pull --ff-only origin main
.venv/bin/python ops/rq1_assessor_preflight.py
```

The helper rechecks the accepted CPU receipts, requests `/v1/models`, verifies the exact selected model is listed, and prepares `work/rq1-v5/assessor.json`. It does not save the API key, send calibration excerpts, consult the private answer key, generate model output, alter Python dependencies or start a VM. Existing differing profiles are preserved. Catalog access does not establish inference permission, available credit or billing entitlement.

Return the `assessor-preflight-*.zip` created in `D:\Dissertation-RQ1\exports`, then pause. On an HTTP/model-list failure, return that same diagnostic ZIP. If Token Factory onboarding or billing prevents obtaining a key, report that screen/state; there is no need to rerun the CPU checkpoint.

## Later step: calibration, after preflight inspection

Use the prepared profile with the existing `rq1.judge run/import` commands for the 12 public calibration tasks. Those requests contain only one excerpt and the public rubric; never provide the diagnostic ZIP or private key to the grader. The assistant audits each actual returned proof against the source answer key, supplies detailed reasons and records acceptance only if every predeclared label and proof check passes. Raw responses are immutable. No main inference follows until that instrument check and the separate GPU readiness checkpoint pass.
