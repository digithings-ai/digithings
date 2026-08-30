"""Overlay daily cron CLI — candidate filter + loud-fail store check (T4).

These tests must not import ``overlay.byok`` (digiquant-only CI omits digillm).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
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
from digiquant.olympus.overlay.cron_execute import (
    PROFILE_PIN_MISSING,
    OverlayExecuteRequiresChain,
    load_overlay_profile_version_id,
    parse_overlay_profile_pin,
    require_overlay_chain,
)
from digiquant.olympus.overlay.dispatch import (
    JOB_TYPE_OVERLAY_DAILY,
    JobRun,
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
    plan_floor: PlanTier | None = None,
) -> WorkspaceEntitlement:
    return WorkspaceEntitlement(
        workspace_id=workspace_id or uuid4(),
        plan_tier=tier,
        subscription_status=status,
        plan_floor=plan_floor,
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


def test_dry_run_counts_plan_floor_custom_without_stripe() -> None:
    logs: list[str] = []
    rc = main(
        ["--dry-run", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[
            _ws(
                _USER,
                tier=PlanTier.FREE,
                status=SubscriptionStatus.NONE,
                plan_floor=PlanTier.CUSTOM,
            ),
        ],
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert "targets=1" in logs[0]
    assert "billing_active=1" in logs[0]


def test_parse_workspace_row_reads_plan_floor() -> None:
    parsed = parse_workspace_row(
        {
            "id": str(_USER),
            "plan_tier": "free",
            "subscription_status": "none",
            "plan_floor": "custom",
        }
    )
    assert parsed is not None
    assert parsed.plan_tier is PlanTier.FREE
    assert parsed.plan_floor is PlanTier.CUSTOM


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

    def eq(self, *_args: object, **_kwargs: object) -> _WorkspacesQuery:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rows)


class _WorkspacesClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def table(self, name: str) -> _WorkspacesQuery:
        if name != "workspaces":
            return _WorkspacesQuery([])
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
    assert loaded[0].plan_floor is None


class _GrantClient:
    """Workspaces + grants + owner membership + Auth admin emails."""

    def __init__(
        self,
        *,
        workspaces: list[dict[str, object]],
        grants: list[dict[str, object]],
        members: list[dict[str, object]],
        users: list[SimpleNamespace],
    ) -> None:
        self._tables = {
            "workspaces": workspaces,
            "entitlement_grants": grants,
            "workspace_members": members,
        }
        self.auth = SimpleNamespace(admin=SimpleNamespace(list_users=lambda: users))

    def table(self, name: str) -> _WorkspacesQuery:
        return _WorkspacesQuery(self._tables.get(name, []))


def test_load_overlay_cron_workspaces_attaches_owner_plan_floor() -> None:
    client = _GrantClient(
        workspaces=[
            {"id": str(_USER), "plan_tier": "free", "subscription_status": "none"},
        ],
        grants=[{"email": "chris.stefan@proton.me", "plan_floor": "custom"}],
        members=[
            {
                "workspace_id": str(_USER),
                "user_id": "0408ba97-caba-44d3-b2d0-5690ab5160a9",
                "role": "owner",
            }
        ],
        users=[
            SimpleNamespace(
                id="0408ba97-caba-44d3-b2d0-5690ab5160a9",
                email="chris.stefan@proton.me",
            )
        ],
    )
    loaded = load_overlay_cron_workspaces(client)
    assert len(loaded) == 1
    assert loaded[0].plan_tier is PlanTier.FREE
    assert loaded[0].plan_floor is PlanTier.CUSTOM


def _module_header(name: str) -> str:
    path = Path(main.__code__.co_filename).with_name(name)
    header: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("def ") or line.startswith("class "):
            break
        header.append(line)
    return "\n".join(header)


def test_cron_headers_do_not_import_byok_or_graph() -> None:
    for name in ("cron.py", "cron_execute.py"):
        imports = "\n".join(
            line
            for line in _module_header(name).splitlines()
            if line.startswith(("import ", "from "))
        )
        assert "byok" not in imports
        assert "digillm" not in imports
        assert "overlay.runner" not in imports
        assert "hermes.chain" not in imports


def test_require_overlay_chain_refuses_none() -> None:
    with pytest.raises(OverlayExecuteRequiresChain, match="chain=None"):
        require_overlay_chain(None)


def test_parse_overlay_profile_pin_skips_invalid() -> None:
    assert parse_overlay_profile_pin({}) is None
    assert parse_overlay_profile_pin({"id": "not-a-uuid"}) is None
    assert parse_overlay_profile_pin({"id": str(_USER)}) == _USER


class _ProfileQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def select(self, *_args: object, **_kwargs: object) -> _ProfileQuery:
        return self

    def eq(self, *_args: object, **_kwargs: object) -> _ProfileQuery:
        return self

    def order(self, *_args: object, **_kwargs: object) -> _ProfileQuery:
        return self

    def limit(self, *_args: object, **_kwargs: object) -> _ProfileQuery:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rows)


class _ProfileClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def table(self, name: str) -> _ProfileQuery:
        assert name == "olympus_profile_config"
        return _ProfileQuery(self._rows)


def test_load_overlay_profile_version_id_returns_tip() -> None:
    pin = uuid4()
    loaded = load_overlay_profile_version_id(_ProfileClient([{"id": str(pin)}]), _USER)
    assert loaded == pin
    assert load_overlay_profile_version_id(_ProfileClient([]), _USER) is None


def _succeeding_runner(*, job: JobRun, store: MemoryJobRunStore, request, chain):
    chain(
        workspace_id=request.workspace_id,
        run_date=request.run_date,
        requested_version_id=request.profile_version_id,
    )
    return store.update(
        job.model_copy(update={"status": JobStatus.SUCCEEDED, "finished_at": datetime.now(tz=UTC)})
    )


def test_execute_invokes_injected_chain_and_marks_succeeded() -> None:
    store = MemoryJobRunStore()
    seen: list[dict[str, object]] = []
    pin = uuid4()

    def chain(*, workspace_id, run_date, requested_version_id):
        seen.append(
            {
                "workspace_id": workspace_id,
                "run_date": run_date,
                "requested_version_id": requested_version_id,
            }
        )

    rc = main(
        ["--execute", "--workspace-id", str(_USER), "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER)],
        store=store,
        byok=_byok(ok=True),
        profile_pins={_USER: pin},
        chain_factory=lambda **_k: chain,
        overlay_runner=_succeeding_runner,
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    row = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert row is not None
    assert row.status is JobStatus.SUCCEEDED
    assert seen
    assert seen[0]["workspace_id"] == _USER
    assert seen[0]["requested_version_id"] == pin
    assert seen[0]["workspace_id"] != house_workspace_id()


def test_execute_missing_profile_pin_fails_closed_without_chain() -> None:
    store = MemoryJobRunStore()
    called = {"chain_factory": 0, "runner": 0}

    def chain_factory(**_k):
        called["chain_factory"] += 1
        raise AssertionError("chain must not be built without a profile pin")

    def runner(**_k):
        called["runner"] += 1
        raise AssertionError("runner must not run without a profile pin")

    rc = main(
        ["--execute", "--workspace-id", str(_USER), "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER)],
        store=store,
        byok=_byok(ok=True),
        profile_pins={},
        chain_factory=chain_factory,
        overlay_runner=runner,
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    row = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert row is not None
    assert row.status is JobStatus.FAILED
    assert row.error == PROFILE_PIN_MISSING
    assert called["chain_factory"] == 0
    assert called["runner"] == 0


def test_execute_chain_none_fails_closed_not_succeeded() -> None:
    store = MemoryJobRunStore()
    err: list[str] = []
    pin = uuid4()
    rc = main(
        ["--execute", "--workspace-id", str(_USER), "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER)],
        store=store,
        byok=_byok(ok=True),
        profile_pins={_USER: pin},
        chain_factory=lambda **_k: None,
        overlay_runner=lambda **_k: (_ for _ in ()).throw(AssertionError("runner")),
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert err
    assert "chain=None" in err[0]
    row = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert row is not None
    assert row.status is JobStatus.FAILED
    assert row.error == "chain_required"
    assert row.status is not JobStatus.SUCCEEDED


def test_execute_does_not_run_skipped_workspaces() -> None:
    store = MemoryJobRunStore()
    called = {"runner": 0}

    def runner(**_k):
        called["runner"] += 1
        raise AssertionError("skipped jobs must not execute")

    rc = main(
        ["--execute", "--all", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER, tier=PlanTier.FREE)],
        store=store,
        byok=_byok(ok=True),
        profile_pins={_USER: uuid4()},
        chain_factory=lambda **_k: lambda **__: None,
        overlay_runner=runner,
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    row = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert row is not None
    assert row.status is JobStatus.SKIPPED
    assert called["runner"] == 0


def test_execute_row_exception_fails_closed_and_continues_batch() -> None:
    store = MemoryJobRunStore()
    first = uuid4()
    second = uuid4()
    ran: list[UUID] = []
    pin_a, pin_b = uuid4(), uuid4()

    def runner(*, job: JobRun, store: MemoryJobRunStore, request, chain):
        ran.append(job.workspace_id)
        if job.workspace_id == first:
            raise RuntimeError("boom")
        chain(
            workspace_id=request.workspace_id,
            run_date=request.run_date,
            requested_version_id=request.profile_version_id,
        )
        return store.update(
            job.model_copy(
                update={"status": JobStatus.SUCCEEDED, "finished_at": datetime.now(tz=UTC)}
            )
        )

    err: list[str] = []
    rc = main(
        ["--execute", "--all", "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(first), _ws(second)],
        store=store,
        byok=_byok(ok=True),
        profile_pins={first: pin_a, second: pin_b},
        chain_factory=lambda **_k: lambda **__: None,
        overlay_runner=runner,
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 3
    assert first in ran and second in ran
    row_a = store.get_by_idempotency_key(overlay_idempotency_key(first, _RUN))
    row_b = store.get_by_idempotency_key(overlay_idempotency_key(second, _RUN))
    assert row_a is not None and row_a.status is JobStatus.FAILED
    assert row_a.error == "RuntimeError"
    assert "boom" not in "\n".join(err)
    assert row_b is not None and row_b.status is JobStatus.SUCCEEDED


def test_dispatch_without_execute_stays_running() -> None:
    store = MemoryJobRunStore()
    rc = main(
        ["--workspace-id", str(_USER), "--run-date", _RUN.isoformat()],
        environ={},
        workspaces=[_ws(_USER)],
        store=store,
        byok=_byok(ok=True),
        overlay_runner=lambda **_k: (_ for _ in ()).throw(AssertionError("no execute")),
        log=lambda _m: None,
        log_err=lambda _m: None,
    )
    assert rc == 0
    row = store.get_by_idempotency_key(overlay_idempotency_key(_USER, _RUN))
    assert row is not None
    assert row.status is JobStatus.RUNNING


def test_execute_production_missing_vault_exits_2_before_dispatch() -> None:
    err: list[str] = []
    rc = main(
        ["--execute", "--all", "--run-date", _RUN.isoformat()],
        environ={"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"},
        workspaces=[_ws(_USER)],
        log=lambda _m: None,
        log_err=err.append,
    )
    assert rc == 2
    assert err
    assert "OVERLAY_EXECUTE_NOT_CONFIGURED" in err[0]
    assert "DIGIQUANT_VAULT_MASTER_KEY" in err[0]
