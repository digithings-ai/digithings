"""Overlay daily cron CLI — candidate filter + loud-fail store check (T4).

These tests must not import ``overlay.byok`` (digiquant-only CI omits digillm).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.overlay.cron import (
    format_overlay_store_not_configured,
    load_overlay_cron_workspaces,
    main,
    missing_overlay_cron_env_names,
    overlay_cron_targets,
    parse_workspace_row,
    reserved_overlay_workspace_ids,
    run_overlay_cron,
)
from digiquant.olympus.overlay.dispatch import (
    JOB_TYPE_OVERLAY_DAILY,
    JobStatus,
    MemoryJobRunStore,
    OverlaySkipReason,
    WorkspaceEntitlement,
    overlay_idempotency_key,
)
from digiquant.olympus.tenancy import (
    PlanTier,
    SubscriptionStatus,
    house_workspace_id,
    system_workspace_id,
)

pytestmark = pytest.mark.unit

_RUN = date(2026, 8, 31)
_USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _ws(
    workspace_id: UUID | None = None,
    *,
    tier: PlanTier = PlanTier.CUSTOM,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> WorkspaceEntitlement:
    return WorkspaceEntitlement(
        workspace_id=workspace_id or uuid4(),
        plan_tier=tier,
        subscription_status=status,
    )


def _byok(*, ok: bool) -> SimpleNamespace:
    return SimpleNamespace(present_and_unsealable=ok)


def test_reserved_ids_are_house_and_system() -> None:
    reserved = reserved_overlay_workspace_ids()
    assert house_workspace_id() in reserved
    assert system_workspace_id() in reserved
    assert len(reserved) == 2


def test_overlay_cron_targets_drop_house_and_system() -> None:
    house = _ws(house_workspace_id(), tier=PlanTier.ENTERPRISE)
    system = _ws(system_workspace_id(), tier=PlanTier.ENTERPRISE)
    user = _ws(_USER)
    targets = overlay_cron_targets((house, system, user))
    assert [row.workspace_id for row in targets] == [_USER]


def test_parse_workspace_row_skips_invalid() -> None:
    invalid = parse_workspace_row(
        {"id": str(_USER), "plan_tier": "nope", "subscription_status": "active"}
    )
    assert invalid is None
    parsed = parse_workspace_row(
        {"id": str(_USER), "plan_tier": "custom", "subscription_status": "active"}
    )
    assert parsed is not None
    assert parsed.workspace_id == _USER
    assert parsed.plan_tier is PlanTier.CUSTOM


def test_missing_overlay_cron_env_names_are_canonical() -> None:
    missing = missing_overlay_cron_env_names({})
    assert missing == ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    msg = format_overlay_store_not_configured(missing)
    assert msg.startswith("OVERLAY_STORE_NOT_CONFIGURED:")
    assert "SUPABASE_URL" in msg
    present = missing_overlay_cron_env_names(
        {"CORE_SUPABASE_URL": "https://example.supabase.co", "CORE_SUPABASE_SERVICE_KEY": "service"}
    )
    assert present == []


def test_check_missing_env_exits_2() -> None:
    err: list[str] = []
    rc = main(["--check"], environ={}, log=lambda _m: None, log_err=err.append)
    assert rc == 2
    assert err
    assert "OVERLAY_STORE_NOT_CONFIGURED" in err[0]
    assert "SUPABASE_URL" in err[0]


def test_check_present_env_exits_0_without_store() -> None:
    logs: list[str] = []
    rc = main(
        ["--check"],
        environ={"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"},
        log=logs.append,
        log_err=lambda _m: None,
        build_store=lambda: (_ for _ in ()).throw(AssertionError("store must not be built")),
    )
    assert rc == 0
    assert logs
    assert "dispatch not attempted" in logs[0]


def test_apply_refuses_implicit_writes() -> None:
    err: list[str] = []
    rc = main(
        [],
        environ={},
        workspaces=[_ws(_USER)],
        store=MemoryJobRunStore(),
        byok=_byok(ok=True),
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 2
    assert err
    assert "--dry-run" in err[0]


def test_dry_run_does_not_write_job_runs() -> None:
    store = MemoryJobRunStore()
    logs: list[str] = []
    rc = main(
        ["--dry-run", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[
            _ws(house_workspace_id(), tier=PlanTier.ENTERPRISE),
            _ws(_USER),
        ],
        store=store,
        byok=_byok(ok=True),
        log=logs.append,
        log_err=lambda _m: None,
        build_store=lambda: (_ for _ in ()).throw(AssertionError("dry-run must not build store")),
    )
    assert rc == 0
    assert store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN)) is None
    assert "targets=1" in logs[0]
    assert "billing_active=1" in logs[0]


def test_apply_without_store_and_missing_env_exits_2() -> None:
    err: list[str] = []
    rc = main(
        ["--all", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER, tier=PlanTier.FREE)],
        store=None,
        byok=_byok(ok=True),
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 2
    assert "OVERLAY_STORE_NOT_CONFIGURED" in err[0]


def test_all_skips_free_workspace_not_entitled() -> None:
    store = MemoryJobRunStore()
    rc = main(
        ["--all", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER, tier=PlanTier.FREE)],
        store=store,
        byok=_byok(ok=True),
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    row = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert row is not None
    assert row.status is JobStatus.SKIPPED
    assert row.error == OverlaySkipReason.NOT_ENTITLED.value
    assert row.job_type == JOB_TYPE_OVERLAY_DAILY


def test_all_never_writes_house_or_system_job_rows() -> None:
    store = MemoryJobRunStore()
    user = _ws(_USER)
    rc = main(
        ["--all", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[
            _ws(house_workspace_id(), tier=PlanTier.ENTERPRISE),
            _ws(system_workspace_id(), tier=PlanTier.ENTERPRISE),
            user,
        ],
        store=store,
        byok=_byok(ok=True),
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert store.get_by_idempotency_key(overlay_idempotency_key(house_workspace_id(), _RUN)) is None
    assert (
        store.get_by_idempotency_key(overlay_idempotency_key(system_workspace_id(), _RUN)) is None
    )
    claimed = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert claimed is not None
    assert claimed.status is JobStatus.RUNNING
    assert claimed.workspace_id == _USER


def test_workspace_id_house_exits_3_without_writes() -> None:
    store = MemoryJobRunStore()
    err: list[str] = []
    rc = main(
        ["--workspace-id", str(house_workspace_id()), "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(house_workspace_id(), tier=PlanTier.ENTERPRISE)],
        store=store,
        byok=_byok(ok=True),
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert "reserved" in err[0]
    assert store.get_by_idempotency_key(overlay_idempotency_key(house_workspace_id(), _RUN)) is None


def test_run_overlay_cron_counts_reserved_as_considered_not_dispatched() -> None:
    store = MemoryJobRunStore()
    report = run_overlay_cron(
        store=store,
        workspaces=(
            _ws(house_workspace_id(), tier=PlanTier.ENTERPRISE),
            _ws(_USER, tier=PlanTier.FREE),
        ),
        run_date=_RUN,
        byok=_byok(ok=True),
    )
    assert report.considered == 2
    assert report.dispatched == 1
    assert report.claimed == 0
    assert report.skipped == 1


class _WorkspacesQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def select(self, *_args: object, **_kwargs: object) -> _WorkspacesQuery:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rows)


class _WorkspacesClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def table(self, name: str) -> _WorkspacesQuery:
        assert name == "workspaces"
        return _WorkspacesQuery(self._rows)


def test_load_overlay_cron_workspaces_parses_valid_rows() -> None:
    client = _WorkspacesClient(
        [
            {"id": str(_USER), "plan_tier": "custom", "subscription_status": "none"},
            {"id": "not-a-uuid", "plan_tier": "custom", "subscription_status": "active"},
        ]
    )
    loaded = load_overlay_cron_workspaces(client)
    assert len(loaded) == 1
    assert loaded[0].workspace_id == _USER
    assert loaded[0].subscription_status is SubscriptionStatus.NONE
