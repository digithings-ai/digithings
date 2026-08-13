"""Circuit breaker coverage on the vertical_orchestrator hub connectors -- the actual
hot path every LLM tool call to digisearch/digiquant/digivault goes through
(ARCHITECTURE.md ยง5.4). Previously only a legacy helper (tools/digisearch.py) had one."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_all_hub_breakers():
    """Each hub's CircuitBreaker is a module-level singleton shared across the whole
    test session -- reset state before AND after every test in this file so test order
    can't leak an OPEN circuit into an unrelated test."""
    from digigraph.vertical_orchestrator import digiquant_hub, digisearch_hub, digivault_hub

    def _reset():
        for mod in (digisearch_hub, digiquant_hub, digivault_hub):
            mod._cb._state = mod._cb._CLOSED
            mod._cb._failures = 0
            mod._cb._opened_at = None

    _reset()
    yield
    _reset()


def _failing_client(status: int = 503):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "unavailable"})

    def fake_sync_client(**kwargs: object) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return fake_sync_client


@pytest.mark.parametrize(
    "hub_module_path,invoke_name,invoke_kwargs,service_label",
    [
        (
            "digigraph.vertical_orchestrator.digisearch_hub",
            "invoke_digisearch_tool",
            {"default_index_name": "default"},
            "digisearch",
        ),
        (
            "digigraph.vertical_orchestrator.digiquant_hub",
            "invoke_digiquant_tool",
            {},
            "digiquant",
        ),
        (
            "digigraph.vertical_orchestrator.digivault_hub",
            "invoke_digivault_tool",
            {},
            "digivault",
        ),
    ],
)
def test_circuit_opens_after_five_failures_and_fails_fast(
    hub_module_path: str, invoke_name: str, invoke_kwargs: dict, service_label: str
) -> None:
    import importlib

    hub = importlib.import_module(hub_module_path)
    invoke = getattr(hub, invoke_name)

    with patch.object(hub, "sync_client", _failing_client()):
        for _ in range(5):
            result = invoke(
                "http://svc:9000",
                "some_tool",
                {},
                bearer_token=None,
                request_id="rid",
                **invoke_kwargs,
            )
            assert result["ok"] is False

    # Circuit must now be OPEN: the 6th call must fail fast WITHOUT calling sync_client
    # at all (a real outage should not pay the full timeout on every single request).
    with patch.object(
        hub,
        "sync_client",
        side_effect=AssertionError("must not call sync_client when circuit is open"),
    ):
        result = invoke(
            "http://svc:9000", "some_tool", {}, bearer_token=None, request_id="rid", **invoke_kwargs
        )
    assert result["ok"] is False
    assert "circuit open" in result["error"]
    assert service_label in result["error"]
