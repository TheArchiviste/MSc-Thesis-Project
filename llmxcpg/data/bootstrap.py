"""Bootstrap CPGQL training data via DeepSeek-v3 with iterative correction.

This implements the procedure in §4.2 (Figure 5) of the paper:

    1. Prompt DeepSeek-v3 with a code sample + vulnerability metadata.
    2. Execute the proposed query on a Joern server.
    3. If invalid (syntax error or empty path on a known-vulnerable sample),
       feed the error back and retry.
    4. After `max_retries` retries, discard the sample.
    5. Successful (code, valid_query) pairs become the training set for
       LLMxCPG-Q (Qwen2.5-Coder-32B-Instruct base).

The iteration is the entire point — without it, DeepSeek's CPGQL is unreliable
(see Table 2 of the paper: 132/1278 valid queries unaided). With it, valid
yield should approach 100% on training samples we keep.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from llmxcpg.joern.client import JoernClient, JoernError
from llmxcpg.joern.queries import validate_generated_query

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# DeepSeek query proposer
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are an expert in static program analysis using Joern's CPGQL query language.
Your task is to write CPGQL queries that capture the taint flow for a known
vulnerability in a C/C++ code snippet. Output strictly a JSON object of the form:
{"queries": ["query 1", "query 2", "...", "final reachableByFlows query"]}

Constraints:
  - Use Scala syntax. CPGQL is a Scala DSL.
  - Last query must use `.reachableByFlows(...)` and bind to a `val`.
  - Bind intermediate values to `val` so they remain in scope across queries.
  - Do not include explanations or markdown. JSON only.
"""


USER_PROMPT_TEMPLATE = """\
The following C/C++ snippet contains a {cwe} vulnerability.{location_hint}

Write CPGQL queries that:
  1. identify the source(s) of the vulnerability,
  2. identify the sink(s),
  3. compute the execution paths from source to sink via reachableByFlows.

Code:
```c
{code}
```
"""


REPAIR_PROMPT_TEMPLATE = """\
Your previous CPGQL queries failed. Joern returned:

{error}

Failed queries:
{queries}

Produce a corrected JSON object {{"queries": [...]}}. Do not repeat the same mistake.
"""


@dataclass
class DeepSeekQueryProposer:
    """Thin wrapper over the DeepSeek API."""
    api_key: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY", ""))
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    max_tokens: int = 1024
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not self.api_key:
            raise OSError(
                "DEEPSEEK_API_KEY is not set. Bootstrap requires API access."
            )
        # Lazy import; openai is an optional dep.
        from openai import OpenAI
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def propose(
        self,
        code: str,
        cwe: str,
        location_hint: str = "",
        previous_failure: tuple[list[str], str] | None = None,
    ) -> list[str]:
        """Single-turn proposal. Returns the parsed `queries` list."""
        if previous_failure is None:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(
                        cwe=cwe, location_hint=location_hint, code=code,
                    ),
                },
            ]
        else:
            failed_queries, error = previous_failure
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(
                        cwe=cwe, location_hint=location_hint, code=code,
                    ),
                },
                {
                    "role": "user",
                    "content": REPAIR_PROMPT_TEMPLATE.format(
                        error=error,
                        queries="\n".join(f"  - {q}" for q in failed_queries),
                    ),
                },
            ]

        # Retry the API call itself on transient errors.
        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_object"},
                )
                text = resp.choices[0].message.content or ""
                payload = json.loads(text)
                queries = payload.get("queries", [])
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    return queries
                return []
            # The OpenAI-compatible SDK can surface transport, timeout, HTTP,
            # and response-validation failures through different exception
            # hierarchies. Retrying all of them is intentional here.
            except Exception as e:  # noqa: BLE001  # pragma: no cover
                logger.warning("DeepSeek API attempt %d failed: %s", attempt + 1, e)
                time.sleep(2 ** attempt)
        return []


# --------------------------------------------------------------------------- #
# Bootstrap loop
# --------------------------------------------------------------------------- #
@dataclass
class BootstrapResult:
    code: str
    cwe: str
    queries: list[str]
    attempts: int
    succeeded: bool
    last_error: str = ""


def _validate_queries(
    joern: JoernClient,
    code: str,
    queries: list[str],
    require_non_empty_path: bool,
) -> tuple[bool, str]:
    """Run the queries against a fresh Joern session.

    Returns (ok, error_message). Empty paths on *vulnerable* samples count as
    failure because we want the model to learn queries that actually trigger.
    On safe samples, empty paths are acceptable.
    """
    try:
        joern.import_code(code, project_name="bootstrap")
    except JoernError as e:
        return False, f"import failed: {e}"

    last_result = None
    for q in queries:
        try:
            validate_generated_query(q)
        except ValueError as exc:
            return False, str(exc)
        last_result = joern.run(q)
        if not last_result.success:
            return False, f"query failed:\n  {q}\n  {last_result.stdout}"

    if require_non_empty_path and last_result is not None and last_result.is_empty:
        return False, "final reachableByFlows query returned empty result on a known-vulnerable sample"

    return True, ""


def bootstrap_query_dataset(
    samples: Iterable[dict],
    joern: JoernClient,
    proposer: DeepSeekQueryProposer,
    *,
    output_path: str | Path,
    max_retries: int = 3,
    require_non_empty_path: bool = True,
) -> dict:
    """Run the iterative-correction bootstrap over a dataset.

    `samples` is an iterable of dicts with keys:
      - `code` (str): source code
      - `cwe` (str): e.g. "CWE-416"
      - `is_vulnerable` (bool, optional): default True
      - `location_hint` (str, optional): e.g. "vulnerability is at line 42"
      - `id` (str, optional): for the output JSONL

    Writes successful (code, queries) pairs to `output_path` as JSONL and
    returns a summary dict.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_total = 0
    n_success = 0
    n_first_try = 0

    with output_path.open("w") as f:
        for i, sample in enumerate(samples):
            n_total += 1
            sample_id = sample.get("id", f"sample_{i}")
            code = sample["code"]
            cwe = sample["cwe"]
            is_vuln = sample.get("is_vulnerable", True)
            location_hint = sample.get("location_hint", "")
            location_hint = f" {location_hint}" if location_hint else ""

            queries: list[str] = []
            last_error = ""
            attempts = 0
            success = False

            for attempt in range(max_retries + 1):
                attempts = attempt + 1
                if attempt == 0:
                    queries = proposer.propose(
                        code=code, cwe=cwe, location_hint=location_hint,
                    )
                else:
                    queries = proposer.propose(
                        code=code, cwe=cwe, location_hint=location_hint,
                        previous_failure=(queries, last_error),
                    )

                if not queries:
                    last_error = "DeepSeek returned no queries"
                    continue

                ok, err = _validate_queries(
                    joern, code, queries,
                    require_non_empty_path=require_non_empty_path and is_vuln,
                )
                if ok:
                    success = True
                    if attempt == 0:
                        n_first_try += 1
                    break
                last_error = err

            if success:
                n_success += 1
                record = {
                    "id": sample_id,
                    "code": code,
                    "cwe": cwe,
                    "is_vulnerable": is_vuln,
                    "queries": queries,
                    "attempts": attempts,
                }
                f.write(json.dumps(record) + "\n")
                f.flush()
            else:
                logger.info(
                    "Discarded %s after %d attempts: %s",
                    sample_id, attempts, last_error[:200],
                )

    return {
        "total_samples": n_total,
        "successful_samples": n_success,
        "first_try_successes": n_first_try,
        "yield_rate": n_success / n_total if n_total else 0.0,
        "first_try_rate": n_first_try / n_total if n_total else 0.0,
        "output_path": str(output_path),
    }
