"""Finite RPC/case budgets without altering the pinned Joern client."""
from __future__ import annotations

import signal
import time


class BoundedJoern:
    def __init__(self, inner, rpc_seconds: float, case_seconds: float):
        if rpc_seconds <= 0 or case_seconds <= 0:
            raise ValueError("Joern timeout budgets must be positive")
        self.inner = inner
        self.rpc_seconds, self.case_seconds = rpc_seconds, case_seconds
        self.deadline = None

    def begin_case(self):
        self.deadline = time.monotonic() + self.case_seconds

    def _call(self, fn, *args, cleanup=False, **kwargs):
        from llmxcpg.joern.client import JoernError
        remaining = (self.deadline - time.monotonic()
                     if self.deadline is not None and not cleanup else self.rpc_seconds)
        budget = min(self.rpc_seconds, remaining)
        if budget <= 0:
            raise JoernError("RPC timeout: case budget exhausted")
        def expired(signum, frame):
            raise TimeoutError(f"RPC timeout: exceeded {budget:.1f}s")
        previous = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, budget)
        try:
            return fn(*args, **kwargs)
        except TimeoutError as exc:
            raise JoernError(str(exc)) from exc
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)

    def import_code(self, source, project_name="snippet"):
        return self._call(self.inner.import_code, source, project_name=project_name)

    def run(self, query):
        return self._call(self.inner.run, query)

    def reset(self):
        return self._call(self.inner.reset, cleanup=True)

    def close(self):
        if hasattr(self.inner, "close"):
            return self._call(self.inner.close, cleanup=True)
