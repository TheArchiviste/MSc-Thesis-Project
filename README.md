# LLMxCPG

An auditable reimplementation of **LLMxCPG: Context-Aware Vulnerability
Detection Through Code Property Graph-Guided Large Language Models**
(Lekssays et al., USENIX Security 2025).

The implementation follows the released
[QCRI pipeline](https://github.com/qcri/llmxcpg): LLMxCPG-Q generates Joern
CPGQL, Joern constructs a program slice, and LLMxCPG-D scores the slice with a
two-class `[No, Yes]` output head.

## What is implemented

- `llmxcpg/joern/`: synchronous Joern client, Docker-safe source staging,
  project lifecycle management, and conservative validation of generated Scala.
- `llmxcpg/slicing/`: execution paths, interacters, backward slicing, and
  source reconstruction.
- `llmxcpg/inference/`: vLLM or OpenAI-compatible Q inference and a genuinely
  reduced two-output detector head.
- `llmxcpg/data/`: dataset loaders, DeepSeek bootstrap/repair loop, and
  Q/D training-set preparation.
- `llmxcpg/calibration/` and `llmxcpg/evaluation/`: threshold search,
  coverage-aware metrics, slice statistics, and query auditing.

## Quickstart

Start Joern from the repository root. The compose mount is paired with
`Config.work_dir/joern-inputs`, allowing the container to read source staged
by the Python client.

```bash
docker compose -f docker/docker-compose.yml up -d

# Lightweight analysis/data utilities
pip install -e .

# GPU inference dependencies
pip install -e '.[inference]'

llmxcpg \
  --code examples/cve_2011_3359.c \
  --query-model QCRI/LLMxCPG-Q \
  --detector-model QCRI/LLMxCPG-D \
  --dataset primevul
```

The legacy `python scripts/run_pipeline.py ...` entry point calls the same CLI.
A failed Q or Joern stage exits with status 2 and produces an abstention, never
a silent SAFE verdict.

## GPU layouts

The two released models are each 32B. With the default local vLLM engine, Q is
released after query generation and D is loaded lazily, which supports a
single-GPU, single-call workflow. For a dataset, call `detect_batch` (the
evaluation script does this) so every query is generated before Q is released.

For repeated online requests, serve Q on a separate GPU/process:

```bash
vllm serve QCRI/LLMxCPG-Q --port 8000

llmxcpg \
  --code examples/cve_2011_3359.c \
  --query-engine openai \
  --query-base-url http://localhost:8000/v1 \
  --query-model QCRI/LLMxCPG-Q \
  --detector-model QCRI/LLMxCPG-D
```

Use `--retain-query-model` only when the machine has enough aggregate GPU
memory for Q and D simultaneously.

## Detector compatibility and thresholds

The released detector is prompted using the upstream
`## Instruction/## Input/## Response` serialization. The reduced head is
ordered `[No, Yes]`; `P(vulnerable)` is therefore class 1. The paper's
calibrated thresholds are:

| Dataset | Threshold |
|---|---:|
| PrimeVul | 0.594 |
| FormAI | 0.547 |
| SVEN | 0.334 |
| ReposVul | 0.193 |

These values are only meaningful with the published model/prompt/class
contract. Recalibrate after fine-tuning or domain changes.

Evaluation excludes pipeline abstentions from classification metrics by
default and reports `coverage` and `abstentions`. Use
`--failure-policy safe` only for an explicit sensitivity analysis.

## Training

```bash
# Query data bootstrap (requires DEEPSEEK_API_KEY)
python scripts/bootstrap_queries.py \
  --dataset primevul \
  --out data/q_train.jsonl \
  --max-retries 3

llamafactory-cli train configs/llamafactory/train_q.yaml

# Build detector slices without loading a detector model
python scripts/build_d_training_set.py \
  --q-model checkpoints/llmxcpg-q \
  --dataset primevul \
  --input path/to/primevul.jsonl \
  --out data/d_train.jsonl

llamafactory-cli train configs/llamafactory/train_d.yaml
```

The D dataset emits `Yes`/`No`, and its LLaMA-Factory configuration uses
the raw/empty template so training and inference share the same wire format.
The standalone PEFT trainer masks prompt tokens and computes loss on the
response only.

## Security and reproducibility

Joern evaluates CPGQL as Scala. The supplied compose service binds only to
`127.0.0.1`, mounts staged source read-only, and the client rejects common
filesystem/process/network APIs in generated queries. This guard is
defense-in-depth, not a complete Scala sandbox; run untrusted workloads in an
isolated container/VM with no secrets or sensitive mounts.

Model names and Joern are configurable external artifacts. Record exact model
revisions, container digests, package versions, and the calibrated threshold
for reproducible experiments. The CLI accepts `--query-revision` and
`--detector-revision` for immutable Hugging Face commit IDs.

## Scope

The supported CWEs are 119, 120, 121, 122, 125, 190, 415, 416, and 787.
Errors can propagate from Q to the slice and D, so inspect the stored queries,
slice, failure stage, probabilities, and coverage rather than relying on a
verdict alone.

## Provenance and license

This repository derives from the GPL-3.0-licensed
[original LLMxCPG implementation](https://github.com/qcri/llmxcpg). See
`NOTICE` for attribution and `LICENSE` for the GPL-3.0 terms.
