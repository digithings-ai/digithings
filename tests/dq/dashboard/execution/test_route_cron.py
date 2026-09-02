"""Unit tests for Kairos order-intent route cron (K4 production seam).

Injects fingerprints and a route callback — never unseals credentials or
constructs Alpaca adapters. Never treats kill-switch-off as a successful submit.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from digiquant.brokers.connections import AuthKind, Broker, ConnectionEnv, ConnectionStatus
from digiquant.execution.route_cron import (
    EXIT_ROUTING_DISABLED,
    KAIROS_ROUTING_DISABLED,
    main,
)
from digiquant.execution.sync_cron import SyncTarget
from digiquant.dashboard.tenancy import house_workspace_id

pytestmark = pytest.mark.unit

_USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CONN = UUID("11111111-2222-3333-4444-555555555555")
_IBKR = UUID("22222222-3333-4444-5555-666666666666")
_API_KEY = UUID("33333333-4444-5555-6666-777777777777")
_FP = "abcd1234"
_STORE = {
    "CORE_SUPABASE_URL": "https://example.supabase.co",
    "CORE_SUPABASE_SERVICE_KEY": "service-role",
}


def _target(
    *,
    connection_id: UUID = _CONN,
    workspace_id: UUID = _USER,
    broker: Broker = Broker.ALPACA,
    env: ConnectionEnv = ConnectionEnv.PAPER,
    auth_kind: AuthKind = AuthKind.OAUTH,
    status: ConnectionStatus = ConnectionStatus.ACTIVE,
) -> SyncTarget:
    return SyncTarget(
        connection_id=connection_id,
        workspace_id=workspace_id,
        broker=broker,
        env=env,
        auth_kind=auth_kind,
        status=status,
        fingerprint=_FP,
    )


def test_check_missing_env_exits_2() -> None:
    err: list[str] = []
    rc = main(["--check"], environ={}, log=lambda _m: None, log_err=err.append)
    assert rc == 2
    assert "KAIROS_SYNC_NOT_CONFIGURED" in err[0]


def test_check_store_present_routing_off_exits_0() -> None:
    logs: list[str] = []
    rc = main(["--check"], environ=_STORE, log=logs.append, log_err=lambda _m: None)
    assert rc == 0
    assert any("routing_enabled=false" in line for line in logs)


def test_check_store_present_routing_on_exits_0() -> None:
    logs: list[str] = []
    env = {**_STORE, "OLYMPUS_KAIROS_ROUTING": "1"}
    rc = main(["--check"], environ=env, log=logs.append, log_err=lambda _m: None)
    assert rc == 0
    assert any("routing_enabled=true" in line for line in logs)


def test_refuses_implicit_submits() -> None:
    err: list[str] = []
    called: list[UUID] = []
    rc = main(
        [],
        environ={**_STORE, "OLYMPUS_KAIROS_ROUTING": "1"},
        targets=[_target()],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 2
    assert "--dry-run" in err[0]
    assert called == []


def test_dry_run_does_not_call_route_batch() -> None:
    logs: list[str] = []
    called: list[UUID] = []
    rc = main(
        ["--dry-run"],
        environ=_STORE,
        targets=[
            _target(workspace_id=house_workspace_id()),
            _target(),
            _target(connection_id=_IBKR, broker=Broker.IBKR),
        ],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert called == []
    assert "runnable=1" in logs[0]
    assert "routing_enabled=false" in logs[0]


def test_all_with_routing_off_does_not_submit() -> None:
    err: list[str] = []
    called: list[UUID] = []
    loaded: list[str] = []
    rc = main(
        ["--all"],
        environ=_STORE,
        targets=[_target()],
        load_targets=lambda: loaded.append("loaded") or [_target()],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == EXIT_ROUTING_DISABLED
    assert KAIROS_ROUTING_DISABLED in err[0]
    assert called == []
    assert loaded == []


def test_all_with_routing_on_routes_alpaca_oauth_only() -> None:
    called: list[UUID] = []
    rc = main(
        ["--all"],
        environ={**_STORE, "OLYMPUS_KAIROS_ROUTING": "1"},
        targets=[
            _target(workspace_id=house_workspace_id()),
            _target(),
            _target(connection_id=_IBKR, broker=Broker.IBKR),
            _target(connection_id=_API_KEY, auth_kind=AuthKind.API_KEY),
        ],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert called == [_CONN]


def test_dispatch_is_refused() -> None:
    err: list[str] = []
    called: list[UUID] = []
    rc = main(
        ["--dispatch"],
        environ={**_STORE, "OLYMPUS_KAIROS_ROUTING": "1"},
        targets=[_target()],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 4
    assert "dispatch" in err[0].lower()
    assert called == []


def test_apply_is_refused() -> None:
    err: list[str] = []
    called: list[UUID] = []
    rc = main(
        ["--apply"],
        environ={**_STORE, "OLYMPUS_KAIROS_ROUTING": "1"},
        targets=[_target()],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 4
    assert "--apply" in err[0]
    assert called == []


def test_connection_id_routing_off_does_not_load() -> None:
    err: list[str] = []
    called: list[UUID] = []
    loaded: list[str] = []
    rc = main(
        ["--connection-id", str(_CONN)],
        environ=_STORE,
        load_targets=lambda: loaded.append("loaded") or [_target()],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == EXIT_ROUTING_DISABLED
    assert KAIROS_ROUTING_DISABLED in err[0]
    assert called == []
    assert loaded == []


def test_connection_id_missing_says_route_not_sync() -> None:
    err: list[str] = []
    called: list[UUID] = []
    missing = UUID("00000000-0000-0000-0000-000000000000")
    rc = main(
        ["--connection-id", str(missing)],
        environ={**_STORE, "OLYMPUS_KAIROS_ROUTING": "1"},
        targets=[_target()],
        route_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == EXIT_ROUTING_DISABLED
    assert "kairos route:" in err[0]
    assert "kairos sync:" not in err[0]
    assert called == []


def test_none_argv_uses_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["route_cron", "--check"])
    err: list[str] = []
    rc = main(None, environ={}, log=lambda _m: None, log_err=err.append)
    assert rc == 2
    assert "KAIROS_SYNC_NOT_CONFIGURED" in err[0]
