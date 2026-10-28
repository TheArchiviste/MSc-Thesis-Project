"""Local protocol simulators test startup gates; they are never Joern observations."""
from __future__ import annotations

import asyncio
from http import HTTPStatus

import pytest
from websockets.asyncio.server import serve

from rq1.joern_readiness import wait_for_protocol


def silent(*args, **kwargs):
    pass


@pytest.mark.asyncio
async def test_open_port_is_not_ready_until_real_websocket_greeting():
    connections = 0

    async def starting(connection, request):
        nonlocal connections
        connections += 1
        if connections <= 2:
            return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, "Starting\n")

    async def ready(connection):
        await connection.send("connected")
        await connection.wait_closed()

    async with serve(ready, "127.0.0.1", 0, process_request=starting) as server:
        port = server.sockets[0].getsockname()[1]
        result = await wait_for_protocol("127.0.0.1", port, seconds=2, interval=.01,
                                         check_running=lambda: True, report=silent)
    assert result["protocol_ready"]
    assert [a["ok"] for a in result["attempts"]] == [False, False, True]
    assert "real CPG import/query must still pass" in result["meaning"]


@pytest.mark.asyncio
async def test_accepting_tcp_without_http_response_is_never_ready():
    async def not_ready(reader, writer):
        writer.close()
        await writer.wait_closed()

    async with await asyncio.start_server(not_ready, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        result = await wait_for_protocol("127.0.0.1", port, seconds=.08, interval=.01,
                                         check_running=lambda: True, report=silent)
    assert not result["protocol_ready"]
    assert result["attempts"]
    assert not any(a["ok"] for a in result["attempts"])


@pytest.mark.asyncio
async def test_unrelated_websocket_greeting_is_rejected():
    async def wrong(connection):
        await connection.send("other-service")
        await connection.wait_closed()

    async with serve(wrong, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        result = await wait_for_protocol("127.0.0.1", port, seconds=.08, interval=.01,
                                         check_running=lambda: True, report=silent)
    assert not result["protocol_ready"]
    assert any("Unexpected Joern" in a["detail"] for a in result["attempts"])
    assert not any(a["ok"] for a in result["attempts"])


@pytest.mark.asyncio
async def test_silent_websocket_has_a_finite_greeting_timeout():
    async def silent_server(connection):
        await connection.wait_closed()

    async with serve(silent_server, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        result = await wait_for_protocol("127.0.0.1", port, seconds=.08, interval=.01,
                                         attempt_seconds=.02,
                                         check_running=lambda: True, report=silent)
    assert not result["protocol_ready"]
    assert any("TimeoutError" in a["detail"] for a in result["attempts"])
    assert result["elapsed_seconds"] < 1


@pytest.mark.asyncio
async def test_stopped_container_is_reported_without_waiting_for_startup_budget():
    result = await wait_for_protocol("127.0.0.1", 1, check_running=lambda: False, report=silent)
    assert not result["protocol_ready"]
    assert not result["attempts"]
    assert "container stopped" in result["detail"]
