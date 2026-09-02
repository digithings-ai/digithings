"""Unit tests for execution broker-mirror sync cron CLI (K4).

These tests inject fingerprints and a sync callback — they never unseal
credentials or construct Alpaca/IBKR adapters.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from uuid import UUID

import pytest
from digiquant.brokers.connections import AuthKind, Broker, ConnectionEnv, ConnectionStatus
from digiquant.execution.sync_cron import (
    ALPACA_API_KEY_HOLD_REASON,
    SyncTarget,
    format_execution_sync_not_configured,
    execution_sync_targets,
    load_execution_sync_targets,
    main,
    missing_execution_sync_apply_env_names,
    missing_execution_sync_env_names,
    parse_connection_row,
    plan_execution_sync,
)
from digiquant.dashboard.tenancy import house_workspace_id, system_workspace_id

pytestmark = pytest.mark.unit

_USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CONN = UUID("11111111-2222-3333-4444-555555555555")
_IBKR = UUID("22222222-3333-4444-5555-666666666666")
_API_KEY = UUID("33333333-4444-5555-6666-777777777777")
_FP = "abcd1234"


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


def test_execution_sync_targets_drop_house_system_live_and_inactive() -> None:
    kept = _target()
    rows = (
        _target(workspace_id=house_workspace_id()),
        _target(workspace_id=system_workspace_id(), connection_id=UUID(int=2)),
        _target(env=ConnectionEnv.LIVE, connection_id=UUID(int=3)),
        _target(status=ConnectionStatus.REVOKED, connection_id=UUID(int=4)),
        kept,
    )
    targets = execution_sync_targets(rows)
    assert [row.connection_id for row in targets] == [_CONN]


def test_plan_execution_sync_holds_ibkr() -> None:
    alpaca = _target()
    ibkr = _target(connection_id=_IBKR, broker=Broker.IBKR)
    runnable, held = plan_execution_sync((alpaca, ibkr))
    assert [row.connection_id for row in runnable] == [_CONN]
    assert len(held) == 1
    assert held[0].connection_id == _IBKR
    assert held[0].reason == "ibkr_requires_brokerage_session"


def test_plan_execution_sync_holds_alpaca_api_key() -> None:
    oauth = _target()
    api_key = _target(connection_id=_API_KEY, auth_kind=AuthKind.API_KEY)
    runnable, held = plan_execution_sync((oauth, api_key))
    assert [row.connection_id for row in runnable] == [_CONN]
    assert len(held) == 1
    assert held[0].connection_id == _API_KEY
    assert held[0].reason == ALPACA_API_KEY_HOLD_REASON


def test_parse_connection_row_skips_invalid() -> None:
    invalid = parse_connection_row({"id": str(_CONN), "broker": "nope"})
    assert invalid is None
    parsed = parse_connection_row(
        {
            "id": str(_CONN),
            "workspace_id": str(_USER),
            "broker": "alpaca",
            "env": "paper",
            "auth_kind": "oauth",
            "status": "active",
            "fingerprint": _FP,
        }
    )
    assert parsed is not None
    assert parsed.connection_id == _CONN
    assert parsed.auth_kind is AuthKind.OAUTH


def test_missing_env_names_are_canonical() -> None:
    missing = missing_execution_sync_env_names({})
    assert missing == ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    apply_missing = missing_execution_sync_apply_env_names({})
    assert "DIGIQUANT_VAULT_MASTER_KEY" in apply_missing
    msg = format_execution_sync_not_configured(apply_missing)
    assert msg.startswith("KAIROS_SYNC_NOT_CONFIGURED:")
    assert "sk_test" not in msg


def test_check_missing_env_exits_2() -> None:
    err: list[str] = []
    rc = main(["--check"], environ={}, log=lambda _m: None, log_err=err.append)
    assert rc == 2
    assert "KAIROS_SYNC_NOT_CONFIGURED" in err[0]
    assert "SUPABASE_URL" in err[0]


def test_apply_refuses_implicit_writes() -> None:
    err: list[str] = []
    called: list[UUID] = []
    rc = main(
        [],
        environ={},
        targets=[_target()],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 2
    assert "--dry-run" in err[0]
    assert called == []


def test_dry_run_does_not_call_sync_batch() -> None:
    logs: list[str] = []
    called: list[UUID] = []
    rc = main(
        ["--dry-run"],
        environ={},
        targets=[
            _target(workspace_id=house_workspace_id()),
            _target(),
            _target(connection_id=_IBKR, broker=Broker.IBKR),
        ],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert called == []
    assert "runnable=1" in logs[0]
    assert "ibkr_held=1" in logs[0]
    assert "alpaca_api_key_held=0" in logs[0]


def test_dry_run_counts_alpaca_api_key_held() -> None:
    logs: list[str] = []
    called: list[UUID] = []
    rc = main(
        ["--dry-run"],
        environ={},
        targets=[
            _target(),
            _target(connection_id=_API_KEY, auth_kind=AuthKind.API_KEY),
            _target(connection_id=_IBKR, broker=Broker.IBKR),
        ],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert called == []
    assert "runnable=1" in logs[0]
    assert "ibkr_held=1" in logs[0]
    assert "alpaca_api_key_held=1" in logs[0]


def test_all_calls_sync_batch_only_for_alpaca_paper() -> None:
    called: list[UUID] = []
    rc = main(
        ["--all"],
        environ={},
        targets=[
            _target(workspace_id=house_workspace_id()),
            _target(),
            _target(connection_id=_IBKR, broker=Broker.IBKR),
        ],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert called == [_CONN]


def test_all_does_not_sync_alpaca_api_key() -> None:
    called: list[UUID] = []
    rc = main(
        ["--all"],
        environ={},
        targets=[
            _target(),
            _target(connection_id=_API_KEY, auth_kind=AuthKind.API_KEY),
        ],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert called == [_CONN]


def test_apply_without_callback_and_missing_vault_exits_2() -> None:
    err: list[str] = []
    rc = main(
        ["--all"],
        environ={"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"},
        targets=[_target()],
        sync_batch=None,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 2
    assert "DIGIQUANT_VAULT_MASTER_KEY" in err[0]


def test_apply_with_vault_uses_production_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []

    def _fake_prod(runnable: Sequence[SyncTarget], *, environ: Mapping[str, str]) -> int:
        del environ
        seen.append(len(runnable))
        return 4

    monkeypatch.setattr(
        "digiquant.execution.sync_cron._production_sync_batch",
        _fake_prod,
    )
    logs: list[str] = []
    rc = main(
        ["--all"],
        environ={
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "k",
            "DIGIQUANT_VAULT_MASTER_KEY": "not-a-real-key",
        },
        targets=[_target()],
        sync_batch=None,
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert seen == [1]
    assert "synced=4" in logs[0]
    assert "not-a-real-key" not in logs[0]


def test_connection_id_house_exits_3() -> None:
    err: list[str] = []
    called: list[UUID] = []
    house_conn = UUID("99999999-9999-9999-9999-999999999999")
    rc = main(
        ["--connection-id", str(house_conn)],
        environ={},
        targets=[_target(connection_id=house_conn, workspace_id=house_workspace_id())],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert "reserved" in err[0]
    assert called == []


def test_connection_id_live_exits_3() -> None:
    err: list[str] = []
    rc = main(
        ["--connection-id", str(_CONN)],
        environ={},
        targets=[_target(env=ConnectionEnv.LIVE)],
        sync_batch=lambda _rows: 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert "live" in err[0]


def test_connection_id_api_key_exits_3() -> None:
    err: list[str] = []
    called: list[UUID] = []
    rc = main(
        ["--connection-id", str(_API_KEY)],
        environ={},
        targets=[_target(connection_id=_API_KEY, auth_kind=AuthKind.API_KEY)],
        sync_batch=lambda rows: called.extend(t.connection_id for t in rows) or 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert "ALPACA_API_KEY_SYNC_HELD" in err[0]
    assert str(_API_KEY) in err[0]
    assert called == []


def test_connection_id_invalid_exits_3() -> None:
    err: list[str] = []
    rc = main(
        ["--connection-id", "not-a-uuid"],
        environ={},
        targets=[_target()],
        sync_batch=lambda _rows: 0,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert "not found" in err[0]


def test_production_empty_does_not_import_alpaca(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.execution.sync_cron import _production_sync_batch

    monkeypatch.delitem(sys.modules, "digiquant.brokers.alpaca", raising=False)
    synced = _production_sync_batch([], environ={})
    assert synced == 0
    assert "digiquant.brokers.alpaca" not in sys.modules


def test_production_refuses_house_and_ibkr_before_unseal(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.execution.sync_cron import _production_sync_batch

    monkeypatch.delitem(sys.modules, "digiquant.brokers.alpaca", raising=False)
    house = _target(workspace_id=house_workspace_id())
    ibkr = _target(connection_id=_IBKR, broker=Broker.IBKR)
    synced = _production_sync_batch((house, ibkr), environ={})
    assert synced == 0
    assert "digiquant.brokers.alpaca" not in sys.modules


def test_production_refuses_alpaca_api_key_before_unseal(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.execution.sync_cron import _production_sync_batch

    monkeypatch.delitem(sys.modules, "digiquant.brokers.alpaca", raising=False)
    api_key = _target(connection_id=_API_KEY, auth_kind=AuthKind.API_KEY)
    synced = _production_sync_batch((api_key,), environ={})
    assert synced == 0
    assert "digiquant.brokers.alpaca" not in sys.modules


class _Query:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def select(self, *_args: object, **_kwargs: object) -> _Query:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rows)


class _Client:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def table(self, name: str) -> _Query:
        assert name == "broker_connections"
        return _Query(self._rows)


def test_load_execution_sync_targets_parses_valid_rows() -> None:
    client = _Client(
        [
            {
                "id": str(_CONN),
                "workspace_id": str(_USER),
                "broker": "alpaca",
                "env": "paper",
                "auth_kind": "oauth",
                "status": "active",
                "fingerprint": _FP,
            },
            {"id": "not-a-uuid", "broker": "alpaca"},
        ]
    )
    loaded = load_execution_sync_targets(client)
    assert len(loaded) == 1
    assert loaded[0].connection_id == _CONN
