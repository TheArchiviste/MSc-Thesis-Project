# LLMxCPG

A reference implementation of **LLMxCPG: Context-Aware Vulnerability Detection
Through Code Property Graph-Guided Large Language Models** (Lekssays et al.,
USENIX Security 2025).

The pipeline has two fine-tuned LLMs sandwiching a static-analysis backend:

```
Code → LLMxCPG-Q → CPGQL query → Joern → execution path
                                            ↓
                                      find interacters
                                            ↓
                                     backward slicing
                                            ↓
                                     concise slice → LLMxCPG-D → Vulnerable / Safe
```

This repository implements every stage end-to-end:

- `llmxcpg/joern/` — async client that talks to a Joern WebSocket server.
- `llmxcpg/slicing/` — execution-path extraction, interacter discovery, backward
  slicing, and code reconstruction from line numbers.
- `llmxcpg/inference/` — vLLM-backed LLMxCPG-Q and a reduced-LM-head classifier
  for LLMxCPG-D (the "Yes/No"-only logits trick from §4.2 of the paper).
- `llmxcpg/data/` — DeepSeek-v3 bootstrap loop that iteratively repairs invalid
  CPGQL queries against a Joern server, plus dataset preparation for FormAI-v2,
  PrimeVul, SVEN, ReposVul.
- `llmxcpg/training/` — LoRA configurations and entry points for fine-tuning
  Q (Qwen2.5-Coder-32B-Instruct base) and D (QwQ-32B-Preview base).
- `llmxcpg/calibration/` — per-dataset threshold γ search.
- `llmxcpg/evaluation/` — metrics and the query-quality audit harness.

## Quickstart

```bash
# 1. Bring up a Joern cluster (4 workers by default)
docker compose -f docker/docker-compose.yml up -d

# 2. Install
pip install -e .

# 3. End-to-end inference on a single C file
python scripts/run_pipeline.py \
    --code examples/cve_2011_3359.c \
    --query-model qcri/llmxcpg-q \
    --detector-model qcri/llmxcpg-d \
    --threshold 0.594
```

## Reproducing training

```bash
# Bootstrap CPGQL training data via DeepSeek-v3 with iterative correction
python scripts/bootstrap_queries.py \
    --dataset primevul \
    --out data/q_train.jsonl \
    --max-retries 3

# Fine-tune the query generator (32K context, LoRA r=8 alpha=4 lr=1e-4)
llamafactory-cli train configs/llamafactory/train_q.yaml

# Generate slices on the labelled training set, then fine-tune the detector
python scripts/build_d_training_set.py \
    --q-model checkpoints/llmxcpg-q \
    --out data/d_train.jsonl
llamafactory-cli train configs/llamafactory/train_d.yaml
```

## Hardware

The paper used a single A100-80GB. LoRA on a 32B base will not fit on
consumer-grade GPUs; for smaller setups, swap the base in `configs/` to
`Qwen/Qwen2.5-Coder-7B-Instruct` (Q) and `Qwen/QwQ-7B` (D) — Appendix B of the
paper shows scale-quality trade-offs.

## Caveats from the literature review

These are limits the design embraces, not bugs:

1. **Memory-safety only.** CWEs 119/120/121/122/125/190/415/416/787 are in
   scope. Race conditions, logic flaws, and authentication bugs are not, because
   static CPG analysis cannot model their preconditions.
2. **Two-stage error propagation.** A wrong query yields a misleading slice that
   the detector will confidently mislabel. The audit harness in
   `llmxcpg/evaluation/audit.py` measures this directly — run it before
   trusting headline metrics.
3. **Threshold portability.** γ varies dramatically across datasets
   (0.193 ReposVul → 0.594 PrimeVul). A small calibration set (~20 labelled
   samples) is essential when deploying to a new domain.
