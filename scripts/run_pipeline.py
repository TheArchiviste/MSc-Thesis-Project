"""Compatibility wrapper for the installed ``llmxcpg`` command."""

from llmxcpg.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
