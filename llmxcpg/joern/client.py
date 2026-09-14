"""Wrapper around `cpgqls-client` for talking to a Joern server.

The Joern server is launched with `joern --server --server-host 0.0.0.0`. It
exposes a WebSocket endpoint on port 8080 that accepts CPGQL queries as Scala
expressions and returns JSON-serialised results.

This module hides the protocol details and provides:

- `JoernClient.import_code(path_or_str)` — load source into a fresh CPG.
- `JoernClient.run(query)` — execute a CPGQL query, return `QueryResult`.
- `JoernClient.run_many(queries)` — sequenced queries sharing scope, which is
  what slice construction needs (`val source = ...; val sink = ...; ...`).

The implementation is intentionally synchronous. Joern serialises queries per
session, so parallelism requires separately configured Joern workers and one
client per worker.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    from cpgqls_client import CPGQLSClient, import_code_query
except ImportError:  # pragma: no cover - handled at construction for light imports
    CPGQLSClient = None
    import_code_query = None


logger = logging.getLogger(__name__)


class JoernError(RuntimeError):
    """Raised on protocol-level Joern errors (timeouts, invalid syntax, etc.)."""


@dataclass(frozen=True)
class QueryResult:
    """Result of a single CPGQL query.

    Joern returns a stdout-style string with the inferred Scala type, plus the
    raw value it produced. We expose both because slice-construction needs the
    structured value, while the bootstrap loop's error feedback uses stdout.
    """
    stdout: str
    value: Any
    success: bool

    @property
    def is_empty(self) -> bool:
        """Heuristic: did the query return zero hits?"""
        if isinstance(self.value, list):
            return len(self.value) == 0
        if self.value is None:
            return True
        # Joern textual reps that mean "no result"
        if isinstance(self.stdout, str):
            txt = self.stdout.strip()
            if txt.endswith("List()") or txt.endswith("Iterator()"):
                return True
        return False


class JoernClient:
    """Synchronous Joern WebSocket client.

    Usage:
        with JoernClient(host="localhost", port=8080) as joern:
            joern.import_code("/path/to/file.c")
            res = joern.run('cpg.method.name("main").l')
            print(res.value)
    """

    def __init__(
        self,
        endpoint: str | None = None,
        host: str = "localhost",
        port: int = 8080,
        auth_user: str | None = None,
        auth_pass: str | None = None,
        local_input_dir: str | Path | None = None,
        server_input_dir: str | None = None,
    ) -> None:
        if CPGQLSClient is None:
            raise ImportError(
                "cpgqls-client is required. Install the project with `pip install -e .`."
            )
        if bool(auth_user) != bool(auth_pass):
            raise ValueError("auth_user and auth_pass must be provided together.")
        self.endpoint = endpoint or f"{host}:{port}"
        creds = (auth_user, auth_pass) if auth_user and auth_pass else None
        self._client = CPGQLSClient(self.endpoint, auth_credentials=creds)
        self._project_loaded: str | None = None
        self.local_input_dir = Path(local_input_dir).resolve() if local_input_dir else None
        self.server_input_dir = server_input_dir
        self._staging_dirs: list[Path] = []
        if self.local_input_dir:
            self.local_input_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Core query execution
    # ------------------------------------------------------------------ #
    def run(self, query: str) -> QueryResult:
        """Execute a single CPGQL query."""
        try:
            raw = self._client.execute(query)
        except Exception as exc:
            logger.exception("Joern transport failure for query: %s", query[:120])
            raise JoernError(str(exc)) from exc

        stdout = raw.get("stdout", "") or ""
        stderr = raw.get("stderr", "") or ""
        success = raw.get("success", False) and not stderr

        # Joern wraps results in `valX: T = ...`. Extract the RHS as best we can.
        value = self._extract_value(stdout) if success else None

        if stderr:
            stdout = f"{stdout}\nSTDERR: {stderr}"

        return QueryResult(stdout=stdout, value=value, success=success)

    def run_many(self, queries: Iterable[str]) -> list[QueryResult]:
        """Execute queries in sequence on the same Joern session.

        Earlier `val` bindings stay in scope for later queries — this is exactly
        the behaviour slice construction needs (Listings 1–3 in the paper).
        """
        results: list[QueryResult] = []
        for q in queries:
            res = self.run(q)
            results.append(res)
            if not res.success:
                # Surface failure early so the bootstrap loop can capture it.
                break
        return results

    # ------------------------------------------------------------------ #
    # Code loading
    # ------------------------------------------------------------------ #
    def import_code(self, code_or_path: str, project_name: str = "snippet") -> None:
        """Load source code into a fresh CPG.

        `code_or_path` may be:
          - a path to an existing file or directory, or
          - a string of source code (we materialise it to a temp file).
        """
        # Drop the prior CPG and its staged input before creating the next one.
        if self._project_loaded:
            self.reset()

        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", project_name).strip("._") or "snippet"
        unique_project = f"{safe_name}_{uuid.uuid4().hex[:12]}"
        staging = Path(tempfile.mkdtemp(
            prefix="llmxcpg_",
            dir=str(self.local_input_dir) if self.local_input_dir else None,
        ))
        self._staging_dirs.append(staging)

        source_path = self._existing_path(code_or_path)
        if source_path is not None:
            target = staging / source_path.name
            if source_path.is_dir():
                shutil.copytree(source_path, target)
            else:
                shutil.copy2(source_path, target)
        else:
            target = staging / f"{safe_name}{self._guess_extension(code_or_path)}"
            target.write_text(code_or_path, encoding="utf-8")

        target_path = self._server_path(target)

        query = import_code_query(target_path, unique_project)
        result = self.run(query)
        if not result.success:
            self._cleanup_staging()
            raise JoernError(f"Failed to import code: {result.stdout}")
        self._project_loaded = unique_project

    def reset(self) -> None:
        """Clear the current CPG. Cheaper than reconnecting."""
        if self._project_loaded:
            # Current Joern exposes project deletion as a top-level command.
            result = self.run(f"delete({json.dumps(self._project_loaded)})")
            if not result.success:
                raise JoernError(
                    f"Failed to delete Joern project {self._project_loaded}: {result.stdout}"
                )
            self._project_loaded = None
        self._cleanup_staging()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _guess_extension(code: str) -> str:
        # Cheap heuristic; Joern's importer infers the language anyway.
        if "#include" in code or "->" in code or "struct " in code:
            return ".c"
        if "namespace " in code or "::" in code:
            return ".cpp"
        return ".c"

    @staticmethod
    def _existing_path(value: str) -> Path | None:
        """Return an existing path without treating long source text as one."""
        try:
            candidate = Path(value).expanduser()
            return candidate.resolve() if candidate.exists() else None
        except (OSError, ValueError):
            return None

    def _server_path(self, target: Path) -> str:
        if self.server_input_dir and self.local_input_dir:
            relative = target.relative_to(self.local_input_dir)
            return str(PurePosixPath(self.server_input_dir) / PurePosixPath(relative.as_posix()))
        return str(target.resolve())

    def _cleanup_staging(self) -> None:
        while self._staging_dirs:
            staging = self._staging_dirs.pop()
            try:
                shutil.rmtree(staging)
            except OSError as exc:
                logger.warning("Could not remove staged Joern input %s: %s", staging, exc)

    @staticmethod
    def _extract_value(stdout: str) -> Any:
        """Best-effort: extract the RHS of `valX: T = <value>` from Joern stdout.

        For complex objects this returns the textual form; downstream code
        treats it as opaque. For numeric/list outputs we attempt to parse.
        """
        if not stdout:
            return None
        # Pattern: `val42: List[Int] = List(1, 2, 3)`
        m = re.match(r"^val\d+:\s*[^=]+=\s*(.*)$", stdout.strip(), re.DOTALL)
        rhs = m.group(1) if m else stdout.strip()

        # Try JSON first (Joern can emit it with `.toJson`).
        try:
            return json.loads(rhs)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fall back to the raw string.
        return rhs

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #
    def __enter__(self) -> "JoernClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.reset()
        except Exception:
            pass
