"""End-to-end slice construction.

This module ties together:
  - the LLMxCPG-Q-generated CPGQL query that defines the execution path,
  - the interacters query (Listing 2),
  - the backward-slice query (Listing 3),
  - and code reconstruction from the resulting line numbers.

The intermediate artefacts (raw queries, returned line sets) are kept on the
`Slice` object so an analyst can inspect them — the inspectability the paper
trades end-to-end convenience for.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from llmxcpg.joern.client import JoernClient, QueryResult
from llmxcpg.joern.queries import (
    build_backward_slice_query,
    build_interacters_query,
    validate_generated_query,
)
from llmxcpg.slicing.reconstruction import reconstruct_code_from_lines


logger = logging.getLogger(__name__)


class SliceFailure(RuntimeError):
    """Raised when slice construction cannot proceed.

    The bootstrap loop catches this and feeds the message back to DeepSeek-v3.
    """


@dataclass
class Slice:
    """Output of slice construction. Keep this rich for auditability."""
    code: str                                  # reconstructed snippet
    line_numbers: list[int]                    # 1-indexed lines pulled from CPG
    original_source: str                       # raw input
    cpgql_queries: list[str] = field(default_factory=list)  # queries actually run
    raw_results: list[QueryResult] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)  # reduction ratio, etc.

    @property
    def reduction_ratio(self) -> float:
        """Fraction of the original removed. Compare to paper's 67-91% range."""
        orig_lines = max(1, len(self.original_source.splitlines()))
        slice_lines = max(1, len(self.code.splitlines()))
        return 1.0 - (slice_lines / orig_lines)


# A line of the form `val NAME = <CPGQL traversal>`. The bootstrap loop and
# the slice extractor both need to find which `val` introduces the
# `execution_path` so we can append our own queries to the same session.
_VAL_BINDING_RE = re.compile(r"^\s*val\s+(\w+)\s*=", re.MULTILINE)


class SliceExtractor:
    """Run a Q-generated query bundle through Joern and produce a Slice."""

    def __init__(self, joern: JoernClient) -> None:
        self.joern = joern

    def extract(
        self,
        source: str,
        cpgql_queries: Sequence[str],
        *,
        project_name: str = "snippet",
    ) -> Slice:
        """Construct a slice for `source` given the list of queries from Q.

        The contract from the prompt (Figure 8) is that the *last* query ends
        in `.reachableByFlows(...)` and the binding called `execution_path`
        captures it. We tolerate slight deviations (different binding names)
        by inferring the last `val NAME = ...` line and aliasing it.
        """
        if not cpgql_queries:
            raise SliceFailure("No CPGQL queries provided.")
        if "reachableByFlows" not in cpgql_queries[-1]:
            raise SliceFailure("The final generated query must use reachableByFlows.")
        try:
            for query in cpgql_queries:
                validate_generated_query(query)
        except ValueError as exc:
            raise SliceFailure(str(exc)) from exc

        # 1. Load source into Joern.
        self.joern.import_code(source, project_name=project_name)

        # 2. Run the user-provided queries verbatim, in order. Earlier `val`
        #    bindings remain in scope for the queries we add ourselves.
        ran: list[QueryResult] = []
        for q in cpgql_queries:
            res = self.joern.run(q)
            ran.append(res)
            if not res.success:
                raise SliceFailure(
                    f"Q-generated CPGQL failed:\n  query: {q}\n  err: {res.stdout}"
                )

        # 3. Identify which binding holds the execution path and alias it.
        path_binding = self._normalise_execution_path(cpgql_queries)
        norm_res = self.joern.run(path_binding)
        if not norm_res.success:
            raise SliceFailure(
                f"Could not bind `execution_path`:\n  binding: {path_binding}\n"
                f"  err: {norm_res.stdout}"
            )

        # 4. Interacters (Listing 2). The `execution_path_binding` argument is
        #    *empty* here because we already aliased it in step 3.
        interacters_q = build_interacters_query(
            execution_path_binding="// execution_path already bound"
        )
        inter_res = self.joern.run(interacters_q)
        if not inter_res.success:
            raise SliceFailure(f"Interacters query failed: {inter_res.stdout}")

        # 5. Backward slice (Listing 3). Returns a sorted list of line numbers.
        slice_q = build_backward_slice_query()
        slice_res = self.joern.run(slice_q)
        if not slice_res.success:
            raise SliceFailure(f"Backward slice query failed: {slice_res.stdout}")

        line_numbers = self._parse_line_list(slice_res.value, slice_res.stdout)
        if not line_numbers:
            raise SliceFailure("Backward slice produced no lines.")

        # 6. Rebuild a code snippet anchored on its enclosing functions.
        snippet = reconstruct_code_from_lines(source, line_numbers, add_function_anchors=True)

        return Slice(
            code=snippet,
            line_numbers=line_numbers,
            original_source=source,
            cpgql_queries=list(cpgql_queries) + [path_binding, interacters_q, slice_q],
            raw_results=ran + [norm_res, inter_res, slice_res],
            metrics={
                "interacter_count": _count_list_items(inter_res.stdout),
                "slice_line_count": len(line_numbers),
                "original_line_count": len(source.splitlines()),
            },
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise_execution_path(queries: Sequence[str]) -> str:
        """Produce a `val execution_path = ...` binding from whatever Q wrote.

        Strategy:
          - If any query already binds `val execution_path = ...`, we're done.
          - Else, find the last `val NAME = ...` and alias it:
            `val execution_path = NAME`.
          - Else, treat the very last query as an expression and bind it:
            `val execution_path = <last query>`.
        """
        joined = "\n".join(queries)
        if re.search(r"\bval\s+execution_path\s*=", joined):
            return "// execution_path defined upstream"

        names = _VAL_BINDING_RE.findall(joined)
        if names:
            return f"val execution_path = {names[-1]}"

        last = queries[-1].strip().rstrip(";")
        return f"val execution_path = {last}"

    @staticmethod
    def _parse_line_list(value, stdout: str) -> list[int]:
        """Pull a `List[Int]` out of Joern output."""
        if isinstance(value, list):
            return [int(x) for x in value if isinstance(x, (int, str)) and str(x).isdigit()]

        # Joern often returns text like "List(12, 14, 15, 18)".
        if isinstance(value, str):
            m = re.search(r"List\(([^)]*)\)", value)
            if m:
                return [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]

        # Last resort: scan stdout.
        m = re.search(r"List\(([^)]*)\)", stdout)
        if m:
            return [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]
        return []


def _count_list_items(stdout: str) -> int:
    """Best-effort count of how many items a Joern `.l` query returned."""
    m = re.search(r"List\(([^)]*)\)", stdout)
    if not m:
        return 0
    body = m.group(1).strip()
    if not body:
        return 0
    # crude: count top-level commas + 1
    depth = 0
    count = 1
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count
