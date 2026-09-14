# A guided tour of the LLMxCPG implementation

This is a step-by-step walkthrough of the repository. It assumes you have the paper (Lekssays et al., USENIX Security 2025) and the literature review to hand, and that you want to understand not just *what* each file does but *why* it was written that way and how the pieces fit together at runtime.

The guide is organised by data flow rather than by alphabetical file listing. We start with a 30-second overview, then trace a single piece of code from raw C input to the user-facing vulnerable/safe verdict, touching each module as we go. Training, calibration, and evaluation come after, because they're things you do once to *produce* the artefacts that inference consumes.

---

## 1. The big picture

LLMxCPG is a two-model pipeline with a static-analysis stage wedged between the two models. Concretely:

```
Source code
    │
    ▼
LLMxCPG-Q  (fine-tuned Qwen2.5-Coder-32B-Instruct)
    │
    │  emits a JSON object: {"queries": ["val source = …", "val sink = …", "val execution_path = sink.reachableByFlows(source).l"]}
    ▼
Joern (running as a WebSocket server)
    │
    │  executes the queries, then runs two more we build automatically:
    │   – the "interacters" query: every identifier on a line touched by the execution path
    │   – the "backward slice" query: every node reachable to (path ∪ interacters) via PDG flows
    │  returns a sorted list of line numbers
    ▼
Slice reconstruction
    │
    │  rebuilds a concise C snippet from those line numbers, including
    │  enclosing function headers/braces so the result is still parseable
    ▼
LLMxCPG-D  (fine-tuned QwQ-32B-Preview, with a reduced LM head)
    │
    │  one forward pass through a two-output [No, Yes] head,
    │  softmax over those two values, threshold against γ
    ▼
Verdict + probability + the full audit trail
```

The two design choices that drive everything else in the code base are:

1. **The two-model split is architectural and never fused.** Q's output is a discrete artefact (a JSON object of CPGQL queries). The slice is a discrete artefact (a sorted list of line numbers, then a reconstructed snippet). D's input is the snippet. At every boundary you can stop, inspect, and disagree with what the previous stage produced. This is the property that makes the system auditable; if you fuse them you lose it.

2. **Failure is explicit, not silent.** Q can produce malformed JSON. Joern can reject a query. The backward slice can come back empty. Every one of these is a different failure mode and each is recorded as such on the result object. A naive implementation would catch all of them and silently fall back to "SAFE", which would look fine in aggregate metrics and be catastrophic in deployment.

Both ideas show up repeatedly below.

---

## 2. The data flow, in code

Let's trace a single call. You write:

```python
pipeline.detect(open("examples/cve_2011_3359.c").read(), threshold=0.594)
```

Here is what happens, step by step, with the file responsible for each step:

| # | What happens | File |
|---|---|---|
| 1 | Detection prompt template loaded | `llmxcpg/prompts.py` |
| 2 | Q-prompt rendered with the source code | `llmxcpg/prompts.py` |
| 3 | Q-model called via vLLM, returns text | `llmxcpg/inference/query_generator.py` |
| 4 | Text parsed strictly as JSON; failures are recorded | `llmxcpg/inference/query_generator.py` |
| 5 | Code loaded into a fresh Joern CPG over WebSocket | `llmxcpg/joern/client.py` |
| 6 | Q's queries executed in order on that session | `llmxcpg/joern/client.py` |
| 7 | "execution_path" binding normalised | `llmxcpg/slicing/extractor.py` |
| 8 | Interacters query built and executed | `llmxcpg/joern/queries.py` |
| 9 | Backward slice query built and executed | `llmxcpg/joern/queries.py` |
| 10 | Line numbers parsed out of Joern's textual output | `llmxcpg/slicing/extractor.py` |
| 11 | Snippet reconstructed with structural anchors | `llmxcpg/slicing/reconstruction.py` |
| 12 | Detection prompt rendered with the snippet | `llmxcpg/prompts.py` |
| 13 | Tokeniser maps No/Yes to single token IDs and installs a two-row head | `llmxcpg/inference/classifier.py` |
| 14 | One forward pass through D; last-position logits captured | `llmxcpg/inference/classifier.py` |
| 15 | The two logits softmaxed; probability thresholded | `llmxcpg/inference/classifier.py` |
| 16 | `ClassificationResult` returned with stage outputs attached | `llmxcpg/inference/pipeline.py` |

We'll cover each of these now, in order.

---

## 3. Foundations: `config.py` and `prompts.py`

### `llmxcpg/config.py`

Everything in the system that is parametric flows through one of three dataclasses:

- `JoernConfig` — where the Joern server lives (`host`, `port`, optional auth).
- `ModelConfig` — paths to the Q and D weights, their context windows, the two class-label tokens, the inference dtype.
- `TrainingConfig` — the LoRA hyperparameters (rank=8, alpha=4, lr=1e-4) and trainer knobs.

These are gathered into a top-level `Config` dataclass that the pipeline accepts via `from_config`. The reason for the layering is mundane but important: in unit tests you can substitute a `JoernConfig(host="localhost", port=18080)` without rebuilding the model object, and in production you can point at different fine-tuned checkpoints without rewriting the config schema.

The module also exports `DEFAULT_THRESHOLDS` — a frozen mapping from dataset name to the γ value the paper calibrated:

```python
DEFAULT_THRESHOLDS = {
    "primevul": 0.594,
    "formai":   0.547,
    "sven":     0.334,
    "reposvul": 0.193,
}
```

I want you to look at that table for a moment, because it is the design rationale for two whole modules later in the code base. **A model whose optimal threshold ranges from 0.193 to 0.594 across four datasets is not "calibrated by training" — it's calibrated by a small validation set, every time you deploy it.** That fact drives `llmxcpg/calibration/threshold.py` (which gives you the calibration tool) and the explicit warnings in `pipeline.py` when no per-dataset threshold is supplied.

The other constant worth understanding here is `SUPPORTED_CWES`: nine memory-safety CWEs (119, 120, 121, 122, 125, 190, 415, 416, 787). The bootstrap loop refuses to write training samples for CWEs outside this list, because the paper's CPGQL templates are tuned for memory-safety taint flows; logic bugs and authentication flaws would need a different query vocabulary.

### `llmxcpg/prompts.py`

Two string constants, both pulled verbatim from Appendix E of the paper:

- `QUERY_GENERATION_PROMPT` (Figure 8) is what Q is fine-tuned against. It tells the model that its job is to output a JSON object whose `queries` field is a sequence of CPGQL expressions ending in a `reachableByFlows` call.
- `DETECTION_PROMPT` reproduces the released implementation's system text and `## Instruction/## Input/## Response` serialization. The instruction retains upstream's VULNERABLE/BENIGN wording, while the training targets and reduced head are `Yes`/`No`; this odd mismatch is part of the released contract.

Both prompts contain a `<CODE>` placeholder; the helpers `render_query_prompt(code)` and `render_detection_prompt(slice)` substitute it.

This module deliberately has almost no logic. Its responsibility is to prevent prompt drift. The released model and calibrated thresholds depend on the exact `Yes`/`No` tokens and section markers; changing either requires retraining or recalibration.

---

## 4. Stage 1: talking to Joern

Joern is a Java-based static-analysis platform written in Scala. It has a server mode that exposes a WebSocket endpoint accepting CPGQL queries (CPGQL is a Scala-embedded DSL for traversing the code property graph). The Python ecosystem talks to it via the `cpgqls-client` package.

### `llmxcpg/joern/client.py`

`JoernClient` is a thin synchronous wrapper around `cpgqls-client`. Three things it does that the raw client doesn't:

**1. Code import.** Joern needs source files on disk in its own filesystem. The `import_code` method accepts either a path or literal source, copies it to `work/joern-inputs`, and passes the corresponding `/analysis/inputs` path to Dockerized Joern. Every CPG gets a collision-resistant project name and is removed with Joern's top-level `delete(...)` command.

**2. Output parsing.** Joern returns results as a stdout string like `val42: List[Int] = List(12, 14, 15, 18)`. The client's `_extract_value` method regex-matches the `valN: T = ` prefix, attempts to JSON-decode the RHS, and falls back to the raw string if that fails. Why isn't this more clever? Because Joern's output format is technically unstable across versions and the queries we run are restricted enough that we can parse what we need (line numbers, list lengths) deterministically downstream.

**3. Sequenced queries.** `run_many(queries)` executes a list against a single session. This matters because the slicing algorithm relies on earlier `val` bindings staying in scope: query 1 binds `source`, query 2 binds `sink`, query 3 uses both to build `execution_path`. If you ran them in separate sessions, query 2 would die with `error: not found: value source`.

The class is a context manager. On `__exit__` it calls `self.reset()` to drop the current project, which means a `with JoernClient(...) as joern:` block leaves the server clean for the next caller.

### `llmxcpg/joern/queries.py`

This module is mostly two Python f-strings holding the CPGQL templates from Listings 2 and 3 of the paper, plus tiny constructor helpers.

**The interacters query** finds every `Identifier` node whose line number coincides with a node on the execution path. Why interacters? Because an execution path through the PDG can skip lines that are necessary to *understand* the path. If the path goes `source = x; ... ; sink = strcpy(buf, source);` and the line that initialises `x` happens to not be on the path, the slice will look like nonsense. Interacters re-include all identifiers on touched lines, so the slice carries the variables the path actually mentions.

**The backward slice query** is one line of Scala:

```scala
val slice = all_path_nodes.reachableByFlows(cpg.all).l
```

Read it backwards: "find every node in the entire CPG that has a flow to any node in `all_path_nodes`". The "flow" here is PDG-based, so it captures data and control dependencies. The result is a set of CPG nodes; we extract their line numbers, sort, and return.

The `build_interacters_query` helper has one runtime check: it refuses to compose if your `execution_path_binding` argument doesn't contain the literal substring `execution_path`. That's a brittle check by design — if Q starts emitting queries that don't define `execution_path`, you want to find out at slice-construction time, not when the backward slice mysteriously runs on an empty input.

There's also `scope_to_method(query, method_name)` as a defensive helper: if a Q-generated query forgets to constrain itself with `.method.name("foo")`, slicing can explode. We don't use it in the main path (the prompt strongly biases Q toward scoped queries) but it's there if you find yourself dealing with a noisy fine-tune.

---

## 5. Stage 2: slicing

The two files in `llmxcpg/slicing/` turn "Q's queries + a Joern session" into "a code snippet". They are the most algorithmically involved part of the system.

### `llmxcpg/slicing/extractor.py` — `SliceExtractor.extract()`

This is a five-step orchestration:

1. **Import the source into Joern.** One call; raises `SliceFailure` if Joern can't parse it.
2. **Run Q's queries in order.** If any of them fails (syntax error, type mismatch), we stop immediately and raise `SliceFailure` with the offending query and Joern's error message. This is the failure that the bootstrap loop catches and feeds back to DeepSeek as a repair signal.
3. **Normalise the `execution_path` binding.** Q's prompt says the last query should bind a value called `execution_path`, but in practice fine-tuned models drift. The extractor's `_normalise_execution_path` handles three cases:
   - Q already wrote `val execution_path = ...` somewhere — we do nothing.
   - Q wrote some other `val NAME = ...` and ended with it — we alias: `val execution_path = NAME`.
   - Q's last query is an expression, not a binding — we wrap it: `val execution_path = <expr>`.

   This adapter is what makes the system robust against minor prompt-template drift.
4. **Build and run the interacters + backward-slice queries.** The interacters query is built with a special sentinel binding (`// execution_path already bound`) because we've already established it in step 3. Both run on the same session.
5. **Parse the line list.** Joern returns something like `List(12, 14, 15, 18)`. The `_parse_line_list` helper handles three serialisation formats (native Python list, Joern's `List(...)` textual form, stdout-only fallback) because Joern's output schema isn't quite stable.

The output is a `Slice` dataclass with the reconstructed code *and* the full provenance: every query that ran, every raw Joern result, the original source, line counts, interacter count, and a computed `reduction_ratio` property. The paper claims 67-91% reduction across datasets; if your numbers are wildly outside that band, something is wrong upstream.

A subtle point: when Q's last query returns an empty list, we *don't* raise. An empty execution path on a labelled-safe sample is legitimate — there's no taint flow because there's no vulnerability. The bootstrap loop, on the other hand, *does* treat empty paths on labelled-vulnerable samples as failure, because there we expect a finding. The asymmetry is enforced in `bootstrap.py`'s `require_non_empty_path` parameter.

### `llmxcpg/slicing/reconstruction.py` — `reconstruct_code_from_lines()`

The slice is a set of line numbers. If you just `''.join(source.splitlines()[i] for i in slice_lines)`, the result is grammatically broken: function headers get dropped, braces don't match, and the detector model has to do a lot of work to even understand the snippet is C.

The reconstruction algorithm has two stages:

1. **Find anchor lines.** For each selected line, walk upward in the source to find the most recent function header (matched by a forgiving regex on the form `[modifiers] return_type name(...)`). Then walk forward from that header counting braces to find the matching close-brace. Add both the header and close-brace lines to the selected set. This means every fragment that appears in the output has the function it lives in clearly delimited around it.

2. **Emit lines in order.** Walk through the selected set in source order. For consecutive lines, emit them adjacently. For gaps, emit a single blank line. We *don't* emit `// ...` comments because the detection prompt already tells the model that the snippet "might not be complete, but it has all the important context"; that prompt was used during fine-tuning, so D is trained to tolerate gaps without a marker.

The function-header regex (`_FUNC_HEADER_RE`) is intentionally permissive. It will match too eagerly on macros that look like function signatures, but the only consequence is including a couple of extra lines that don't hurt. False *negatives* (failing to anchor a function) are recoverable: we just don't add anchors, and reconstruction degrades to "emit selected lines verbatim". That's strictly worse than anchoring but doesn't break the pipeline.

I'd flag this as the one place where there's room for a meaningful improvement. A tree-sitter-based reconstruction would be exact rather than heuristic, and the dependency is already in `pyproject.toml` (we just don't use it yet).

---

## 6. Stage 3: query generation

### `llmxcpg/inference/query_generator.py`

`QueryGenerator` wraps a vLLM `LLM` engine. The paper specifies vLLM specifically for Q (and Unsloth for D), and we follow that. Three things this module does:

**1. Init.** Loads the fine-tuned Q checkpoint via vLLM with the configured context window (32K) and a temperature of 0. Determinism matters here: the slice extractor depends on Q producing the same queries for the same input, especially during training-data generation.

**2. Generation.** `generate(code)` and `generate_batch(codes)`. Batching is meaningful because vLLM is much faster on batches than on sequential single calls. The pipeline class uses `generate_batch` when given a list of inputs.

**3. Strict parsing.** The model returns text. We:
   - Strip markdown code fences if the model wraps the JSON in them (it sometimes does despite fine-tuning).
   - Find the outermost `{...}` block.
   - JSON-decode it.
   - Validate that `queries` is a non-empty list of strings.

Any failure produces a `QueryGenerationOutput` with `parsed_ok=False` and an `error` field describing exactly why. The pipeline class will then record `failure_stage="query_parse"` on the result, and the bootstrap loop will treat the failure as a signal to retry with feedback.

There's also a `dummy` engine mode that returns a fixed JSON payload without loading any weights. This is what `tests/test_unit.py` uses to exercise the parsing logic without a GPU.

---

## 7. Stage 4: classification — the reduced LM head

This is the surgical core of the paper. `llmxcpg/inference/classifier.py` deserves the most careful reading.

### The standard approach (which we're not using)

If you wanted to use a fine-tuned LLM as a binary classifier, the obvious approach is to generate `Yes` or `No` and parse it. That is wasteful and fragile because a generative model can emit whitespace or extra prose.

### What we do instead

We never call `generate()`. At model load, the full vocabulary projection is replaced with two copied rows ordered `[No, Yes]`. A forward pass therefore produces only two logits per token. We take the last position, softmax the pair, and threshold the `Yes` probability.

In code:

```python
# At init time:
safe_id = tokenizer.encode("No", add_special_tokens=False)[0]
vuln_id = tokenizer.encode("Yes", add_special_tokens=False)[0]
reduced_head.weight = original_head.weight[[safe_id, vuln_id]]

# At inference time:
out = model(input_ids)               # one forward pass, KV cache disabled
safe_logit, vuln_logit = out.logits[0, -1, :]
p_safe, p_vuln = softmax([safe_logit, vuln_logit])
is_vulnerable = p_vuln >= gamma
```

This is mathematically equivalent to computing the model's probability of saying `No` vs `Yes` as its first token, conditioned on those two options. It also avoids allocating full-vocabulary logits.

### The token-resolution subtlety

The above assumes `No` and `Yes` are each single tokens in the tokeniser. BPE behaviour can vary based on whether there is a leading space, so both spellings are tried and incompatible tokenisers fail loudly.

`_resolve_token_ids` handles this by trying both `"VULNERABLE"` and `" VULNERABLE"` and picking the first one that encodes to a single token. If neither works it raises a clear error rather than silently using a multi-token sequence (which would give meaningless logits at that position). This is the one place where I would want to be loud rather than graceful — a multi-token label silently working would be the kind of bug that costs you a month of trust.

### Batch padding direction

For `classify_batch`, we temporarily flip the tokeniser's `padding_side` to `"left"`. That's because we want "the last position" to mean "the last real token", not "the last padding token". Left-padding pushes the padding to the start, leaving real content at the right edge. After the batch we restore the original padding side so we don't pollute caller state.

### The pipeline contract

`ClassificationOutput` carries the verdict, the two probabilities, the threshold used, *and* the two raw logits. That last field is the audit hook: if you want to investigate why the model classifies something a particular way, the raw logits tell you whether one label dominated overwhelmingly or whether it was a near-tie that the threshold tipped one way.

---

## 8. The pipeline class

### `llmxcpg/inference/pipeline.py`

`LLMxCPGPipeline` is the only class most callers ever instantiate. It holds:

- A `QueryGenerator` (Q-model wrapper)
- A lazily loaded `VulnerabilityClassifier` (D-model wrapper)
- A `JoernClient`
- A default threshold

Its public methods are `detect(source_code)` and `detect_batch(source_codes)`. Both return `ClassificationResult` objects whose fields tell you, for each sample:

```
source_code              # input
is_vulnerable            # bool, or None on failure
probability_vulnerable   # float, or None
probability_safe         # float, or None
threshold                # float used for the decision
query_output             # QueryGenerationOutput from stage 1
slice                    # Slice from stage 2
classification           # ClassificationOutput from stage 3
failure_stage            # "query_parse" | "slice" | None
failure_reason           # string explaining the failure
```

The `is_vulnerable is None when failure_stage is not None` invariant is what makes audit reporting straightforward. Evaluation excludes these abstentions by default and reports both coverage and abstention count. Explicit `safe`, `vulnerable`, and `error` policies are available for sensitivity analyses.

The `detect_batch` method batches Q-model inference up front and D-model inference at the end. In the default single-GPU layout, Q is released before D is lazily loaded, so dataset callers must use this method rather than loop over `detect`. Joern remains sequential because each sample needs its own CPG in this client session.

### Why not async?

Joern serialises queries within a session, so async does not help this client. Parallel deployments must explicitly provision multiple isolated Joern workers and shard inputs across separate pipeline instances; the supplied compose file intentionally starts one worker because the library does not contain an endpoint pool.

---

## 9. Training data: the bootstrap loop

To fine-tune Q, you need pairs of (source code, valid CPGQL queries). No such dataset exists. The paper builds one by asking DeepSeek-v3 to propose queries, executing them against Joern, and iterating with error feedback when they fail. Table 2 of the paper reports that raw DeepSeek gets only 132/1278 queries valid on a single pass; with the iterative correction loop, the yield approaches 100%.

### `llmxcpg/data/bootstrap.py`

Two main objects:

**`DeepSeekQueryProposer`** is a thin OpenAI-compatible client. It takes a code sample and a CWE label, builds a system + user prompt, and asks DeepSeek for a JSON response. The repair path is interesting: when the previous attempt failed, we *don't* just retry with higher temperature. We construct a `REPAIR_PROMPT_TEMPLATE` that contains the failed queries and the Joern error message, and we send the full history (initial user prompt + failed attempt + repair instruction). DeepSeek then has both the original task and the specific error to fix. This is closer to a debugging conversation than a retry loop.

**`bootstrap_query_dataset`** is the loop:

```
for sample in samples:
    for attempt in range(max_retries + 1):
        if attempt == 0:
            queries = proposer.propose(sample)
        else:
            queries = proposer.propose(sample, previous_failure=(queries, error))

        ok, error = validate_queries(joern, sample, queries, require_non_empty_path)
        if ok:
            write_to_output(sample, queries)
            break
    # else: discard sample after max_retries failures
```

The validity check (`_validate_queries`) does two things: it ensures every query executes without Joern raising, and on labelled-vulnerable samples it requires the final query to return a non-empty flow list. On labelled-safe samples it accepts empty results, because that's what "no vulnerability" looks like.

The output is a JSONL file with one record per successfully bootstrapped sample. The summary dict the function returns lets you measure your yield: how many samples did we get queries for, how many on the first try, what was the average attempts-to-success. These numbers matter — if your first-try rate is below ~10% you're paying a lot in API calls, and if your final yield is below ~80% something about your samples is hostile to the prompt.

### `llmxcpg/data/esbmc_cwe_mapping.py`

FormAI-v2 is a special case because it doesn't ship CWE labels. It ships ESBMC verdicts — bounded model checker assertion failures — and you have to map those to CWEs by hand. The paper does this in §4.1 but doesn't publish the table. This module reconstructs it from the ESBMC manual and the FormAI-v2 paper:

```python
ESBMC_TO_CWE = {
    "dereference failure: array bounds violated": "CWE-119",
    "arithmetic overflow on add":                  "CWE-190",
    "double free":                                  "CWE-415",
    "use after free":                               "CWE-416",
    # ...
}
```

The mapping is substring-matched case-insensitively against the ESBMC verdict text. The order in the dict matters — more specific patterns first — so e.g. "dereference failure: invalidated dynamic object" maps to UAF before falling through to the generic dereference rule.

### `llmxcpg/data/loaders.py`

One generator per dataset: `load_formai_v2`, `load_primevul`, `load_sven`, `load_reposvul`. Each yields dicts with the schema the bootstrap loop expects: `{id, code, cwe, is_vulnerable, location_hint}`. The loaders are intentionally minimal — they iterate, they don't sample, they don't balance. The bootstrap script does balancing itself, because the right ratio of vulnerable/safe samples depends on your downstream model.

### `llmxcpg/data/prepare.py`

After bootstrapping you have (code, queries) pairs. After running those queries through Q + Joern on the *training* set, you have (code, slice, label) triples. This module converts both into the alpaca-format JSONL that LLaMA-Factory consumes:

```json
{"instruction": "<rendered prompt>", "input": "", "output": "<expected response>"}
```

For Q the output is `{"queries": [...]}`; for D it is the literal word `Yes` or `No`. The functions are `build_q_training_set(bootstrap_jsonl, output_path)` and `build_d_training_set(sliced_samples, output_path)`.

---

## 10. Training

### `configs/llamafactory/`

The reference path is LLaMA-Factory. The two YAML files (`train_q.yaml`, `train_d.yaml`) encode the configured hyperparameters:

- LoRA rank=8, alpha=4, dropout=0
- Learning rate 1e-4 with cosine schedule, 5% warmup
- 3 epochs
- BF16, gradient checkpointing on
- Context: 32K for Q, 8K for D training, and 16K for released D inference

`dataset_info.json` is LLaMA-Factory's registry file — it tells the framework where the JSONL lives and how to map alpaca columns to its internal schema.

### `llmxcpg/training/train_q.py` and `train_d.py`

These are stand-alone PEFT-based training scripts as a fallback if you don't want to install LLaMA-Factory. Q applies the tokenizer's Qwen chat template; D uses the released raw section-marker format. Both mask prompt tokens so training loss is computed only on the expected response.

`train_d.py` is a thin wrapper over `train_q.py` that changes the base model, context length, and prompt template. Re-implementing the entire training loop twice would invite drift.

### `llmxcpg/training/lora_config.py`

A one-function module that returns a `peft.LoraConfig` matching the paper's spec. Target modules are all linear layers of the transformer block (attention + FFN). The reason this is its own module rather than inlined is so the standalone scripts and any future custom training code share exactly the same LoRA configuration.

---

## 11. Calibration

### `llmxcpg/calibration/threshold.py`

The function `calibrate_threshold(probabilities, labels)` runs a sweep over γ ∈ [0, 1] in 101 evenly-spaced steps. For each γ it computes accuracy and F1 on the validation sample, and returns a `CalibrationResult` containing:

- `best_threshold`, `best_accuracy`, `best_f1`
- `sweep` — the full list of `(γ, accuracy, F1)` tuples
- `n_samples`, `n_positive`, `n_negative`
- `is_balanced` (a property that fires if the minority class is below 30%)

You can ask the function to optimise for either accuracy (the paper's default) or F1 — the latter matters when your validation set is imbalanced and accuracy is dominated by the majority class.

The function warns (via the standard `logging` module) when called with fewer than 20 samples. The paper recommends ~20 minimum; below that, your threshold estimate has too much variance to deploy.

The function returns the *full sweep* rather than just the best point because the shape of the curve is diagnostic. A sharp peak says you've nailed the threshold. A flat plateau says the model is bimodal and many thresholds would work. A bumpy curve suggests your validation set is too small. Just returning the maximum throws all that away.

The companion CLI is `scripts/calibrate_threshold.py`, which:
1. Loads a validation JSONL.
2. Shuffles deterministically with a configurable seed.
3. Takes the first N (default 20).
4. Runs each sample through the pipeline with γ=0.5 just to get probabilities.
5. Calls `calibrate_threshold` on the resulting (prob, label) pairs.
6. Writes the result to a JSON file and prints the headline number.

---

## 12. Evaluation and auditing

### `llmxcpg/evaluation/metrics.py`

`classification_metrics(predictions, labels)` returns accuracy, precision, recall, F1, support, the confusion matrix, total inputs, abstentions, and coverage. `None` predictions are excluded by default; choose an explicit failure policy when reproducing a different reporting convention.

`metrics_by_cwe(predictions, labels, cwes)` groups by CWE for the per-CWE breakdowns the paper reports in Tables 4 and 8.

`reduction_ratio_stats(original_lengths, slice_lengths)` reports mean, median, and quartile reductions for the slicing stage — the paper claims 67-91% across datasets, so this is how you check your fine-tune is producing slices of the right shape.

`scripts/evaluate.py` ties these together. It runs the full pipeline over a labelled test set, accumulates predictions and per-sample metadata, computes all three metric groups, tracks failure-stage counts, and writes a JSON report.

### `llmxcpg/evaluation/audit.py`

This is the module that addresses the literature review's strongest critique head-on. The critique: two-stage pipelines hide where errors come from. If Q produces a wrong query, the slice is garbage, and D will confidently mislabel the garbage. From outside the pipeline you just see "D was wrong"; you don't see that D was wrong *because Q was wrong*.

The audit module measures three things per sample:

1. **Validity**: did Joern accept all of Q's queries? (Cheap, fully automated.)
2. **Path coverage**: did the final query return a non-empty execution path? (Cheap, fully automated.)
3. **CWE alignment**: do the queries mention the API surface you'd expect for the labelled CWE? (Heuristic, semi-automated.)

The heuristic is a coarse map from CWE → expected-API-substrings. For CWE-122 (heap overflow) we expect to see strings like `malloc`, `calloc`, `memcpy`. For CWE-415 (double free) we expect `free`, `double`. We score what fraction of those expected substrings appear in the query blob, lowercased.

This is *not* a definitive oracle. It will produce false positives (a query mentioning `free` for legitimate reasons in a CWE-119 context will look misaligned) and false negatives (a clever query for CWE-122 that doesn't lexically mention `malloc`). What it is, is a *flag*. A sample with an alignment score of 0.05 is one a human auditor should look at; a sample with 0.7 is probably fine to trust.

The `fleiss_kappa` function lets you measure inter-rater agreement when multiple humans audit the same sample. The paper reports κ ≈ 0.64 across three reviewers on 25 samples. If you replicate the audit and your κ is much lower, your reviewers aren't aligned on what they're looking for; if it's much higher, you may be priming them too much.

`summarise_audit(audits)` aggregates a list of audit records into a dict with the same shape the paper reports: validity rate, non-empty-path rate, mean CWE alignment, most common failure notes. That's the structure of §4.3.1 in the paper.

---

## 13. Deployment

### `docker/docker-compose.yml`

Four Joern containers on ports 8080-8083. Each runs `joern --server --server-host 0.0.0.0 --server-port 8080` and gets its own named volume for workspace persistence. The reason for four (rather than one or sixteen) is that Joern is heavy enough that you don't want hundreds of replicas on a single machine, and one is too few for any meaningful parallelism. Four is a pragmatic default for an A100-class development box.

To use more, just duplicate the service block. To use one, comment out the others. The pipeline class talks to a single endpoint; parallelism comes from running multiple pipeline instances pointed at different ports.

### Scripts under `scripts/`

Five CLIs:

- **`run_pipeline.py`** — single-sample inference. Takes a code file, model paths, threshold, and prints either a human-readable report or JSON.
- **`bootstrap_queries.py`** — kicks off the DeepSeek-driven bootstrap. Picks dataset, points at Joern, writes the (code, queries) JSONL.
- **`build_d_training_set.py`** — sweeps a labelled training corpus through Q + Joern to produce slices, then pairs them with labels for D fine-tuning.
- **`calibrate_threshold.py`** — runs the per-dataset γ calibration. Saves the full sweep so you can inspect the curve later.
- **`evaluate.py`** — paper-style evaluation on a labelled test set. Produces overall metrics, per-CWE breakdowns, reduction-ratio stats, and a failure-stage count.

Each script is a thin orchestration over the library; the real logic lives in `llmxcpg/`.

### `pyproject.toml`

Standard PEP 621 metadata. Dependencies are grouped: Joern integration (cpgqls-client, websocket-client), LLM inference (vllm, transformers, torch, accelerate, peft, unsloth), training (datasets, bitsandbytes), bootstrap (openai), parsing (tree-sitter and friends), misc (numpy, scikit-learn, click, pyyaml). The `dev` extra brings in `pytest` and `ruff`.

---

## 14. Tests and the lazy-import scheme

### The lazy imports

The package's top-level `__init__.py` does *not* eagerly import `LLMxCPGPipeline` (which would transitively pull in `torch`, `transformers`, and `vllm`). It uses PEP 562's module-level `__getattr__` so that `llmxcpg.LLMxCPGPipeline` triggers the import only on first access:

```python
def __getattr__(name: str):
    if name == "LLMxCPGPipeline":
        from llmxcpg.inference.pipeline import LLMxCPGPipeline
        return LLMxCPGPipeline
    # ...
```

The same pattern is applied to every subpackage that has both light and heavy modules: `joern/` (light queries, heavy client), `slicing/` (light reconstruction, heavy extractor), `inference/` (everything is heavy, but each piece is loaded independently), `data/` (light ESBMC mapping, heavy bootstrap).

The practical upshot: you can write a script that imports `llmxcpg.calibration` and `llmxcpg.evaluation` and run it without `torch` installed at all. This makes the threshold-search and audit code usable on CPU-only machines, in CI, and inside the test runner — without compromising the one-import-line ergonomics of the main use case (`from llmxcpg import LLMxCPGPipeline`).

### `tests/test_unit.py`

Twenty-one tests covering everything that doesn't require a Joern server or a GPU:

- **Reconstruction**: function anchoring, empty slice, out-of-range lines, line ordering.
- **Calibration**: perfect separation, full-sweep return, length-mismatch rejection, F1-vs-accuracy optimisation.
- **ESBMC mapping**: known patterns, unknown verdicts.
- **Prompts**: code substitution, label presence.
- **CPGQL queries**: rejecting invalid bindings, accepting valid ones.
- **Metrics**: basic confusion matrix, None-as-safe handling, per-CWE grouping.
- **Audit**: alignment scoring, flagging invalid queries, Fleiss' κ perfect-agreement, input validation, chance-level behaviour.

All twenty-one pass in well under a second. The tests are deliberately not comprehensive — they're a smoke screen. They tell you within ~half a second whether you've broken anything in the pure-Python pieces, so you can iterate fast on those without spinning up Joern or a model.

---

## 15. Where the design pushes back on the paper's blind spots

There are three places where the implementation goes further than the paper, in response to the literature review's critiques:

**1. Failure stages are first-class.** Every `ClassificationResult` has a `failure_stage` field that takes one of three values: `None` (success), `"query_parse"`, or `"slice"`. This means the evaluation script can report a failure breakdown alongside the headline metrics, which the paper doesn't. If 40% of your "SAFE" predictions are actually pipeline failures masquerading as confident negatives, that's the kind of fact you want to know.

**2. The calibration sweep is the deliverable.** The paper reports per-dataset thresholds as four numbers. The calibration module returns the entire 101-point curve. If you find your calibrated γ is unstable across re-runs with different seeds, the curve will show you whether the optimum is sharply defined or whether you've just picked a noisy peak on a plateau.

**3. The audit harness exists.** The paper has §4.3.1 ("Error Analysis") but doesn't ship the tools to run it. The `audit_queries` function and the `EXPECTED_APIS` heuristic let you produce the same kind of analysis on your own deployment. You won't get a definitive verdict — these things require human judgement — but you'll get a sorted list of "samples worth a human's attention", which is much more actionable than a P-R curve.

---

## 16. End-to-end: a worked example

Suppose you have the `examples/cve_2011_3359.c` file from the project. Here's what happens when you run:

```bash
python scripts/run_pipeline.py \
    --code examples/cve_2011_3359.c \
    --query-model QCRI/LLMxCPG-Q \
    --detector-model QCRI/LLMxCPG-D \
    --dataset primevul
```

1. `run_pipeline.py` reads the code from disk and uses `DEFAULT_THRESHOLDS["primevul"] = 0.594` since `--dataset primevul` was supplied.
2. It builds a `Config` and calls `LLMxCPGPipeline.from_config(cfg, dataset_threshold_key="primevul")`. This kicks off loading the vLLM engine (a few minutes) and the detector (more minutes). KV cache is disabled on the detector.
3. `pipeline.detect(source_code)` is invoked.
4. The Q-prompt is rendered with the source code substituted in. The vLLM engine generates output deterministically at temperature 0. Output text looks like `{"queries": ["val source = cpg.call.name(\"nla_get_u32\").l", "val sink = cpg.call.name(\"memcpy\").l", "val execution_path = sink.reachableByFlows(source).l"]}`.
5. The parser strips any markdown fences, finds the outermost `{...}`, JSON-decodes it, and validates the schema. `query_output.parsed_ok` is True.
6. `SliceExtractor.extract` is called. It opens a Joern session, imports the C file (Joern parses it with its C/C++ frontend, builds AST + CFG + PDG = CPG), and runs Q's three queries in order. The first two bind `source` and `sink`; the third computes flows.
7. The extractor normalises the binding (`execution_path` is already defined by Q, so nothing changes), then runs the interacters and backward-slice queries. The backward slice returns something like `List(15, 17, 18, 20, 21, 22)`.
8. Reconstruction takes those line numbers plus the function header (line 17, `void process_beacon(...)`) and close-brace (line 26), emits them in order with blank lines for gaps. The result is a ~10-line snippet showing the read of `len` from attacker-controlled data, the `nla_data` call, and the bounds-check-free `memcpy`.
9. The D-prompt is rendered with that snippet. The detector tokenises it, does one forward pass, and reads the `[No, Yes]` logits at the last position.
10. Suppose those logits are 4.1 and -1.3. Softmax gives p_vuln ≈ 0.996, p_safe ≈ 0.004. Against γ=0.594 this is decisively VULNERABLE.
11. The result object carries every artefact from every stage. The CLI prints:

```
======================================================================
LLMxCPG verdict
======================================================================
  Verdict:       VULNERABLE
  P(vulnerable): 0.9956
  Threshold γ:   0.5940
  Slice reduction: 64.3%

--- Generated CPGQL queries ---
  • val source = cpg.call.name("nla_get_u32").l
  • val sink = cpg.call.name("memcpy").l
  • val execution_path = sink.reachableByFlows(source).l

--- Reconstructed slice ---
void process_beacon(struct nlattr *attr, struct cmd_ds_802_11_beacon_set *cmd)
    unsigned int len;
    len = nla_get_u32(attr);
    src = nla_data(attr);
    memcpy(cmd->beacon, src, len);
}
```

That's the full system in 11 steps. Every intermediate value above is on the `ClassificationResult` and could be inspected, dumped to a debug log, or fed to the audit harness.

---

## Closing thought

The reason the code is structured the way it is — lazy imports, explicit failure stages, returned-sweep calibration, audit harness — is the same reason the paper's architecture has two models in the first place. **Inspectability is the property the design exists to provide, and any implementation choice that erodes it would betray the whole point of using a CPG in the first place.** A monolithic "code in, verdict out" black box is easier to build, but you'd lose every advantage that distinguishes this approach from feeding raw source to a generalist LLM. The whole reason to do the static-analysis dance is that you want to be able to argue with the model — and to argue, you need to see the pieces.

That principle is what every design decision in this code base traces back to.
