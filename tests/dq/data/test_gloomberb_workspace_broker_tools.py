"""Workspace writes + broker reads + approval-gated IBKR orders (130-coverage Task 7).

Offline: ``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher`` with
a call-counting handler. Covers the Task 4 write-route disposition (no personal
Cloud write route was verified — the 2026-09-30 source probe found only
team-scoped account APIs — so the workspace/broker tools are session-gated but
never issue Cloud write traffic), the approvals ticket lifecycle (HMAC,
single-use, 15-min TTL, ticket-hash binding), the preview-returns-ticket path,
and the disabled execute path (``upstream_error`` with zero brokerage traffic).

Write-route disposition (Task 4 probes doc has no Cloud-write-API verdicts; own
source probe of gloom-sh/gloomberb 2026-09-30, Live: unverified):
- team collections (watchlist/portfolio-kind): team-scoped
  ``GET/POST /teams/{teamId}/collections``, ``PUT/DELETE .../items``
  (``src/api-client/collections.ts``) — teamId required, account surface.
- notes ``PUT /notes`` (revision-gated), theses ``POST /theses``, team views
  ``POST /views`` (``src/api-client/{notes,theses,views}.ts``) — account
  surfaces with revision/team scope.
- alerts: only a mobile history read (``data.ts`` ``getMobileAlertHistory``).
- brokers: generic ``/brokers/{broker}{path}`` session proxy
  (``src/brokers/cloud-broker-link.ts``); IBKR orders go through the local
  gateway (``rawApi.placeOrder`` in gloom-ibkr-gateway), not Cloud REST.
No personal-symbol watchlist/portfolio/alert/note/thesis/view write route and
no fixed broker positions/order route were found, so no write tool invents one.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

pytest.importorskip("mcp.server.fastmcp")

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    TOOL_ENTITLEMENTS,
    GloomberbClient,
)
from digiquant.data.gloomberb.approvals import (  # noqa: E402
    APPROVAL_KEY_ENV,
    APPROVAL_TTL_SECONDS,
    ApprovalError,
    OrderTicket,
    issue_ticket,
    redeem_token,
)
from digiquant.mcp_server import create_mcp_server  # noqa: E402
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402

NEW_SESSION_TOOLS = {
    # Workspace writes (Phase D): session-gated, read-only posture — no
    # verified personal Cloud write route, so no request is ever made.
    "digifetch_portfolio_view",
    "digifetch_watchlist_add",
    "digifetch_watchlist_remove",
    "digifetch_portfolio_add",
    "digifetch_portfolio_remove",
    "digifetch_alert_add",
    "digifetch_alert_list",
    "digifetch_note_add",
    "digifetch_thesis_add",
    "digifetch_view_add",
    # Broker reads + approval-gated orders (Phase E).
    "digifetch_broker_positions",
    "digifetch_ibkr_preview_order",
    "digifetch_ibkr_execute_order",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)
    monkeypatch.delenv(APPROVAL_KEY_ENV, raising=False)


def make_client(handler: Any, calls: list[int], **kwargs: Any) -> GloomberbClient:
    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return handler(request)

    fetcher = HttpFetcher(
        transport=httpx.MockTransport(counting),
        allowed_hosts=["api.gloom.sh"],
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


def _unexpected(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request (must be zero-HTTP): {request.url}")


def _mcp(name: str):
    return create_mcp_server()._tool_manager.get_tool(name).fn


# ── approvals ticket lifecycle ──────────────────────────────────────────────


def _ticket() -> OrderTicket:
    return OrderTicket(
        symbol="AAPL", side="buy", quantity=10.0, order_type="limit", limit_price=200.0
    )


def test_approval_ttl_is_15_minutes() -> None:
    assert APPROVAL_TTL_SECONDS == 900


def test_issue_redeem_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    ticket = _ticket()
    token = issue_ticket(ticket, now=1_000_000.0)
    assert isinstance(token, str) and token
    redeemed = redeem_token(token, now=1_000_000.0 + 60.0)
    assert redeemed == ticket


def test_redeem_rejects_tampered_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    token = issue_ticket(_ticket(), now=1_000_000.0)
    head, _, _ = token.rpartition(".")
    tampered = head + ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    with pytest.raises(ApprovalError):
        redeem_token(tampered, now=1_000_000.0 + 60.0)


def test_redeem_rejects_expired_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    token = issue_ticket(_ticket(), now=1_000_000.0)
    with pytest.raises(ApprovalError, match="expired"):
        redeem_token(token, now=1_000_000.0 + APPROVAL_TTL_SECONDS + 1.0)


def test_redeem_rejects_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    token = issue_ticket(_ticket(), now=1_000_000.0)
    redeem_token(token, now=1_000_000.0 + 60.0)
    with pytest.raises(ApprovalError, match="[Rr]eplay|single-use|already"):
        redeem_token(token, now=1_000_000.0 + 120.0)


def test_redeem_rejects_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    token = issue_ticket(_ticket(), now=1_000_000.0)
    with pytest.raises(ApprovalError):
        redeem_token(token, key="other-key", now=1_000_000.0 + 60.0)


def test_issue_fails_closed_without_key() -> None:
    with pytest.raises(ApprovalError, match=APPROVAL_KEY_ENV):
        issue_ticket(_ticket(), now=1_000_000.0)


def test_redeem_rejects_malformed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    with pytest.raises(ApprovalError):
        redeem_token("not-a-token", now=1_000_000.0)


# ── session gating (zero-HTTP auth_required without cookie) ─────────────────


_WORKSPACE_CALLS: dict[str, dict[str, Any]] = {
    "portfolio_view": {},
    "watchlist_add": {"symbol": "AAPL"},
    "watchlist_remove": {"symbol": "AAPL"},
    "portfolio_add": {"symbol": "AAPL", "quantity": 10.0},
    "portfolio_remove": {"symbol": "AAPL"},
    "alert_add": {"symbol": "AAPL", "condition": "above", "price": 250.0},
    "alert_list": {},
    "note_add": {"symbol": "AAPL", "content": "earnings look strong"},
    "thesis_add": {"ticker": "AAPL", "title": "Long AAPL", "document": "thesis body"},
    "view_add": {"name": "my view", "spec": {"panes": ["GP"]}},
    "broker_positions": {"broker": "ibkr"},
    "ibkr_preview_order": {"symbol": "AAPL", "side": "buy", "quantity": 10.0},
    "ibkr_execute_order": {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10.0,
        "approval_token": "gb1.invalid",
    },
}

_CLIENT_METHODS = {
    "digifetch_portfolio_view": ("portfolio_view", _WORKSPACE_CALLS["portfolio_view"]),
    "digifetch_watchlist_add": ("watchlist_add", _WORKSPACE_CALLS["watchlist_add"]),
    "digifetch_watchlist_remove": (
        "watchlist_remove",
        _WORKSPACE_CALLS["watchlist_remove"],
    ),
    "digifetch_portfolio_add": ("portfolio_add", _WORKSPACE_CALLS["portfolio_add"]),
    "digifetch_portfolio_remove": (
        "portfolio_remove",
        _WORKSPACE_CALLS["portfolio_remove"],
    ),
    "digifetch_alert_add": ("alert_add", _WORKSPACE_CALLS["alert_add"]),
    "digifetch_alert_list": ("alert_list", _WORKSPACE_CALLS["alert_list"]),
    "digifetch_note_add": ("note_add", _WORKSPACE_CALLS["note_add"]),
    "digifetch_thesis_add": ("thesis_add", _WORKSPACE_CALLS["thesis_add"]),
    "digifetch_view_add": ("view_add", _WORKSPACE_CALLS["view_add"]),
    "digifetch_broker_positions": (
        "broker_positions",
        _WORKSPACE_CALLS["broker_positions"],
    ),
    "digifetch_ibkr_preview_order": (
        "ibkr_preview_order",
        _WORKSPACE_CALLS["ibkr_preview_order"],
    ),
    "digifetch_ibkr_execute_order": (
        "ibkr_execute_order",
        _WORKSPACE_CALLS["ibkr_execute_order"],
    ),
}


@pytest.mark.parametrize("name", sorted(NEW_SESSION_TOOLS))
def test_new_tools_declare_session_entitlement(name: str) -> None:
    assert TOOL_ENTITLEMENTS[name] == "session"


@pytest.mark.parametrize("name", sorted(NEW_SESSION_TOOLS))
def test_new_tools_registered_in_full_and_read_scope(name: str) -> None:
    full = {t.name for t in create_mcp_server(scope="full")._tool_manager.list_tools()}
    read = {t.name for t in create_mcp_server(scope="read")._tool_manager.list_tools()}
    assert name in full and name in read


@pytest.mark.parametrize(("name", "call"), sorted(_CLIENT_METHODS.items()))
def test_session_gate_returns_auth_required_with_zero_http(
    name: str, call: tuple[str, dict[str, Any]]
) -> None:
    calls: list[int] = []
    client = make_client(_unexpected, calls)  # no session cookie
    method, args = call
    envelope = getattr(client, method)(args)
    assert calls == [], name
    assert envelope.data.code == "auth_required", name  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "name",
    sorted(NEW_SESSION_TOOLS - {"digifetch_ibkr_preview_order", "digifetch_ibkr_execute_order"}),
)
def test_read_only_posture_with_session_and_zero_http(name: str) -> None:
    """With a session but no verified write route: typed upstream_error, no request."""
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    method, args = _CLIENT_METHODS[name]
    envelope = getattr(client, method)(args)
    assert calls == [], name
    error = envelope.data
    assert error.code == "upstream_error", name  # type: ignore[union-attr]
    assert "read-only" in error.message, name  # type: ignore[union-attr]


# ── preview returns a ticket, never executes ────────────────────────────────


def test_preview_returns_ticket_with_zero_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    envelope = client.ibkr_preview_order(
        {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10.0,
            "order_type": "limit",
            "limit_price": 200.0,
        }
    )
    assert calls == []
    data = envelope.data
    assert not hasattr(data, "code"), data
    assert data.ticket.symbol == "AAPL"
    assert data.ticket.side == "buy"
    assert data.ticket.quantity == 10.0
    assert data.ticket.order_type == "limit"
    assert data.ticket.limit_price == 200.0
    assert data.approval_token
    # The token redeems to the bound ticket (single-use: preview mints it, the
    # execute path consumes it).
    redeemed = redeem_token(data.approval_token)
    assert redeemed.symbol == "AAPL"
    assert redeemed.quantity == 10.0


def test_preview_rejects_non_positive_quantity_with_zero_traffic() -> None:
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    envelope = client.ibkr_preview_order({"symbol": "AAPL", "side": "buy", "quantity": 0})
    assert calls == []
    assert envelope.data.code == "invalid_input"  # type: ignore[union-attr]


def test_preview_requires_limit_price_for_limit_orders() -> None:
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    envelope = client.ibkr_preview_order(
        {"symbol": "AAPL", "side": "buy", "quantity": 10.0, "order_type": "limit"}
    )
    assert calls == []
    assert envelope.data.code == "invalid_input"  # type: ignore[union-attr]


# ── execute: token-gated, ships disabled ────────────────────────────────────


def test_execute_without_token_is_invalid_input_with_zero_http() -> None:
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    envelope = client.ibkr_execute_order({"symbol": "AAPL", "side": "buy", "quantity": 10.0})
    assert calls == []
    assert envelope.data.code == "invalid_input"  # type: ignore[union-attr]


def test_execute_with_bad_token_is_invalid_input_with_zero_http() -> None:
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    envelope = client.ibkr_execute_order(
        {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10.0,
            "approval_token": "gb1.invalid",
        }
    )
    assert calls == []
    assert envelope.data.code == "invalid_input"  # type: ignore[union-attr]


def test_execute_with_valid_token_is_disabled_with_zero_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    preview = client.ibkr_preview_order({"symbol": "AAPL", "side": "buy", "quantity": 10.0})
    token = preview.data.approval_token  # type: ignore[union-attr]
    envelope = client.ibkr_execute_order(
        {"symbol": "AAPL", "side": "buy", "quantity": 10.0, "approval_token": token}
    )
    assert calls == []
    error = envelope.data
    assert error.code == "upstream_error"  # type: ignore[union-attr]
    assert "order execution disabled pending approval-gate review" in error.message  # type: ignore[union-attr]


def test_execute_rejects_ticket_order_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    preview = client.ibkr_preview_order({"symbol": "AAPL", "side": "buy", "quantity": 10.0})
    token = preview.data.approval_token  # type: ignore[union-attr]
    envelope = client.ibkr_execute_order(
        {"symbol": "MSFT", "side": "buy", "quantity": 10.0, "approval_token": token}
    )
    assert calls == []
    assert envelope.data.code == "invalid_input"  # type: ignore[union-attr]


def test_execute_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    token = issue_ticket(_ticket(), now=1_000_000.0)
    envelope = client.ibkr_execute_order(
        {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10.0,
            "order_type": "limit",
            "limit_price": 200.0,
            "approval_token": token,
        }
    )
    assert calls == []
    assert envelope.data.code == "invalid_input"  # type: ignore[union-attr]


def test_execute_rejects_replayed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    preview = client.ibkr_preview_order({"symbol": "AAPL", "side": "buy", "quantity": 10.0})
    token = preview.data.approval_token  # type: ignore[union-attr]
    args = {"symbol": "AAPL", "side": "buy", "quantity": 10.0, "approval_token": token}
    first = client.ibkr_execute_order(args)
    assert first.data.code == "upstream_error"  # type: ignore[union-attr]
    second = client.ibkr_execute_order(args)
    assert calls == []
    assert second.data.code == "invalid_input"  # type: ignore[union-attr]


def test_execute_dry_run_returns_would_be_request_with_zero_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    preview = client.ibkr_preview_order({"symbol": "AAPL", "side": "sell", "quantity": 5.0})
    token = preview.data.approval_token  # type: ignore[union-attr]
    envelope = client.ibkr_execute_order(
        {
            "symbol": "AAPL",
            "side": "sell",
            "quantity": 5.0,
            "approval_token": token,
            "dry_run": True,
        }
    )
    assert calls == []
    data = envelope.data
    assert not hasattr(data, "code"), data
    assert data.would_be.body["symbol"] == "AAPL"
    assert data.would_be.body["side"] == "sell"
    assert data.would_be.body["quantity"] == 5.0
    assert data.would_be.path == "/brokers/ibkr/orders"


def test_audit_log_names_symbol_side_quantity_without_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(APPROVAL_KEY_ENV, "test-key")
    calls: list[int] = []
    client = make_client(_unexpected, calls, session_cookie="gloomberb.session_token=test")
    with caplog.at_level(logging.INFO, logger="digiquant.data.gloomberb.client"):
        preview = client.ibkr_preview_order({"symbol": "AAPL", "side": "buy", "quantity": 10.0})
        token = preview.data.approval_token  # type: ignore[union-attr]
        client.ibkr_execute_order(
            {"symbol": "AAPL", "side": "buy", "quantity": 10.0, "approval_token": token}
        )
    text = caplog.text
    assert "AAPL" in text
    assert "buy" in text
    assert "10" in text
    assert token not in text


# ── manifest / dispatcher parity ────────────────────────────────────────────


def test_manifest_lists_each_new_tool_with_session_entitlement() -> None:
    from digiquant.data.gloomberb.entitlements import entitlement_note

    rows = {row["function"]["name"]: row for row in build_orchestrator_tool_manifest()}
    for name in sorted(NEW_SESSION_TOOLS):
        assert rows[name].get("entitlement") == "session", name
        assert entitlement_note(name) in rows[name]["function"]["description"], name
        assert "Gloomberb" in rows[name]["function"]["description"], name


def test_dispatch_covers_new_tools_with_client_methods() -> None:
    from digiquant.data.gloomberb import DIGIFETCH_DISPATCH

    for name in sorted(NEW_SESSION_TOOLS):
        assert name in DIGIFETCH_DISPATCH, name
        method = getattr(GloomberbClient, DIGIFETCH_DISPATCH[name].client_method, None)
        assert callable(method), name
