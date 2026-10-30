"""Retained RQ1 Joern client and generated-query guard regressions."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from llmxcpg.joern.queries import build_interacters_query, validate_generated_query


def test_interacters_query_requires_execution_path_var():
    # Builder should reject a binding that doesn't define `execution_path`.
    with pytest.raises(ValueError):
        build_interacters_query("val foo = cpg.method.l")

def test_interacters_query_accepts_valid_binding():
    q = build_interacters_query("val execution_path = sink.reachableByFlows(source).l")
    assert "execution_path" in q
    assert "interacters" in q

def test_generated_query_guard_rejects_process_execution():
    with pytest.raises(ValueError):
        validate_generated_query('Runtime.getRuntime().exec("id")')
    with pytest.raises(ValueError):
        validate_generated_query('System.getProperty("user.home")')

def test_generated_query_guard_accepts_cpg_traversal():
    validate_generated_query('val execution_path = sink.reachableByFlows(source).l')

def test_joern_client_stages_container_path_and_cleans_up():
    import llmxcpg.joern.client as client_module

    calls = []

    class FakeClient:
        def __init__(self, endpoint, auth_credentials=None):
            self.endpoint = endpoint

        def execute(self, query):
            calls.append(query)
            return {"stdout": "val1: String = ok", "stderr": "", "success": True}

    original_client = client_module.CPGQLSClient
    original_import = client_module.import_code_query
    client_module.CPGQLSClient = FakeClient
    client_module.import_code_query = lambda path, project: f"importCode({path!r}, {project!r})"
    try:
        with tempfile.TemporaryDirectory() as directory:
            client = client_module.JoernClient(
                local_input_dir=directory, server_input_dir="/analysis/inputs",
            )
            client.import_code("int main(void) { return 0; }", project_name="unsafe name")
            assert "/analysis/inputs/llmxcpg_" in calls[-1]
            staged = list(Path(directory).iterdir())
            assert len(staged) == 1
            assert (staged[0] / "unsafe_name.c").exists()
            loaded = client._project_loaded
            client.reset()
            assert calls[-1] == f'delete("{loaded}")'
            assert list(Path(directory).iterdir()) == []
    finally:
        client_module.CPGQLSClient = original_client
        client_module.import_code_query = original_import
