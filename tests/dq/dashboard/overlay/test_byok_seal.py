"""BYOK seal resume path — names/fingerprints only, never secret values."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import UUID, uuid4

import pytest
from digiquant.dashboard.overlay.byok_seal import (
    BYOK_AAD_PURPOSE,
    BYOK_SECRET_FILENAME,
    EXIT_BYOK_FILE_OR_KEYS_MISSING,
    EXIT_BYOK_NOT_ENTITLED,
    LLM_PROVIDERS,
    ByokSealError,
    assert_workspace_may_receive_byok,
    build_sealed_row,
    format_byok_seal_blocked,
    inspect_byok_secret_file,
    persist_active_byok,
    run_byok_seal,
    verify_sealed_row,
)
from digiquant.dashboard.overlay.dispatch import WorkspaceEntitlement
from digiquant.dashboard.tenancy import (
    PlanTier,
    SubscriptionStatus,
    house_workspace_id,
    system_workspace_id,
)
from digiquant.vault.envelope import MasterKey

pytestmark = pytest.mark.unit

_SECRET = "gsk_not_a_real_overlay_key_for_tests"


def _key() -> MasterKey:
    return MasterKey(key_id="v1", material=os.urandom(32))


def _entitled(workspace_id: UUID | None = None) -> WorkspaceEntitlement:
    return WorkspaceEntitlement(
        workspace_id=workspace_id or uuid4(),
        plan_tier=PlanTier.FREE,
        subscription_status=SubscriptionStatus.NONE,
        plan_floor=PlanTier.STUDIO,
    )


def _write_file(root: Path, *, provider: str = "groq", workspace_id: UUID | None = None) -> None:
    secrets = root / ".local" / "secrets"
    secrets.mkdir(parents=True)
    lines = [f"BYOK_PROVIDER={provider}", f"BYOK_API_KEY={_SECRET}"]
    if workspace_id is not None:
        lines.append(f"BYOK_WORKSPACE_ID={workspace_id}")
    (secrets / BYOK_SECRET_FILENAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


class _UniqueConflict(Exception):
    code = "23505"


class _Result:
    def __init__(self, data: object, error: object | None = None) -> None:
        self.data = data
        self.error = error


class _Query:
    def __init__(self, store: _MemoryStore, table: str) -> None:
        self._store = store
        self._table = table
        self._action = "select"
        self._row: dict[str, object] | None = None
        self._filters: dict[str, str] = {}
        self._updates: dict[str, object] | None = None

    def select(self, _columns: str) -> Self:
        self._action = "select"
        return self

    def insert(self, row: dict[str, object]) -> Self:
        self._action = "insert"
        self._row = dict(row)
        return self

    def update(self, values: dict[str, object]) -> Self:
        self._action = "update"
        self._updates = dict(values)
        return self

    def eq(self, column: str, value: object) -> Self:
        self._filters[column] = str(value)
        return self

    def limit(self, _count: int) -> Self:
        return self

    def execute(self) -> _Result:
        if self._action == "insert":
            assert self._row is not None
            return self._store.insert(self._row)
        if self._action == "update":
            assert self._updates is not None
            self._store.update(self._filters, self._updates)
            return _Result(data=[])
        return _Result(data=self._store.select(self._filters))


class _MemoryStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def table(self, name: str) -> _Query:
        assert name == "workspace_provider_credentials"
        return _Query(self, name)

    def insert(self, row: dict[str, object]) -> _Result:
        active = [
            item
            for item in self.rows
            if item["workspace_id"] == row["workspace_id"]
            and item["provider"] == row["provider"]
            and item["status"] == "active"
        ]
        if active:
            raise _UniqueConflict
        stored = dict(row)
        stored.setdefault("created_at", datetime(2026, 8, 31, tzinfo=UTC).isoformat())
        self.rows.append(stored)
        return _Result(data=[stored])

    def update(self, filters: dict[str, str], values: dict[str, object]) -> None:
        for item in self.rows:
            if all(str(item.get(key)) == value for key, value in filters.items()):
                item.update(values)

    def select(self, filters: dict[str, str]) -> list[dict[str, object]]:
        return [
            item
            for item in self.rows
            if all(str(item.get(key)) == value for key, value in filters.items())
        ]


def test_inspect_reports_missing_file_by_name(tmp_path: Path) -> None:
    report = inspect_byok_secret_file(tmp_path)
    assert report.missing_file is True
    assert "BYOK_PROVIDER" in report.missing_keys
    msg = format_byok_seal_blocked(report)
    assert BYOK_SECRET_FILENAME in msg
    assert _SECRET not in msg


def test_inspect_complete_file_names_only(tmp_path: Path) -> None:
    _write_file(tmp_path, provider="groq")
    report = inspect_byok_secret_file(tmp_path)
    assert report.missing_file is False
    assert report.missing_keys == ()
    assert report.provider == "groq"
    assert _SECRET not in str(report.model_dump())


def test_check_exits_2_when_file_missing(tmp_path: Path) -> None:
    logs: list[str] = []
    code = run_byok_seal(repo_root=tmp_path, apply=False, log=logs.append)
    assert code == EXIT_BYOK_FILE_OR_KEYS_MISSING
    assert any("missing file" in line for line in logs)
    assert not any(_SECRET in line for line in logs)


def test_seal_roundtrip_unseals_and_persist_is_fingerprint_only(tmp_path: Path) -> None:
    workspace = uuid4()
    master = _key()
    row = build_sealed_row(workspace_id=workspace, provider="groq", secret=_SECRET, key=master)
    assert _SECRET not in str(row)
    assert str(row["ciphertext"]).startswith("\\x")
    verify_sealed_row(row, key=master)
    store = _MemoryStore()
    result = persist_active_byok(client=store, row=row)
    assert result.workspace_id == workspace
    assert result.provider == "groq"
    assert result.replaced is False
    assert len(result.fingerprint) == 8
    assert _SECRET not in result.fingerprint


def test_reconnect_revokes_previous_active_row() -> None:
    workspace = uuid4()
    master = _key()
    store = _MemoryStore()
    first = build_sealed_row(workspace_id=workspace, provider="groq", secret=_SECRET, key=master)
    persist_active_byok(client=store, row=first)
    second = build_sealed_row(
        workspace_id=workspace, provider="groq", secret="gsk_replacement_not_real", key=master
    )
    result = persist_active_byok(client=store, row=second)
    assert result.replaced is True
    statuses = [str(item["status"]) for item in store.rows]
    assert statuses.count("revoked") == 1
    assert statuses.count("active") == 1


def test_refuse_house_and_unentitled() -> None:
    with pytest.raises(ByokSealError) as house:
        assert_workspace_may_receive_byok(
            WorkspaceEntitlement(
                workspace_id=house_workspace_id(),
                plan_tier=PlanTier.ENTERPRISE,
                subscription_status=SubscriptionStatus.ACTIVE,
            )
        )
    assert getattr(house.value, "code", "") == "reserved_workspace"
    with pytest.raises(ByokSealError) as system:
        assert_workspace_may_receive_byok(
            WorkspaceEntitlement(
                workspace_id=system_workspace_id(),
                plan_tier=PlanTier.ENTERPRISE,
                subscription_status=SubscriptionStatus.NONE,
            )
        )
    assert getattr(system.value, "code", "") == "reserved_workspace"
    with pytest.raises(ByokSealError) as free:
        assert_workspace_may_receive_byok(
            WorkspaceEntitlement(
                workspace_id=uuid4(),
                plan_tier=PlanTier.FREE,
                subscription_status=SubscriptionStatus.NONE,
            )
        )
    assert getattr(free.value, "code", "") == "not_entitled"


def test_apply_refuses_not_entitled_without_writing(tmp_path: Path) -> None:
    workspace = uuid4()
    _write_file(tmp_path, workspace_id=workspace)
    store = _MemoryStore()
    logs: list[str] = []
    code = run_byok_seal(
        repo_root=tmp_path,
        apply=True,
        log=logs.append,
        workspace_id=workspace,
        client=store,
        key=_key(),
        entitlement=WorkspaceEntitlement(
            workspace_id=workspace,
            plan_tier=PlanTier.FREE,
            subscription_status=SubscriptionStatus.NONE,
        ),
    )
    assert code == EXIT_BYOK_NOT_ENTITLED
    assert store.rows == []
    assert not any(_SECRET in line for line in logs)


def test_apply_stores_for_plan_floor_studio(tmp_path: Path) -> None:
    workspace = uuid4()
    _write_file(tmp_path, workspace_id=workspace)
    store = _MemoryStore()
    logs: list[str] = []
    code = run_byok_seal(
        repo_root=tmp_path,
        apply=True,
        log=logs.append,
        workspace_id=workspace,
        client=store,
        key=_key(),
        entitlement=_entitled(workspace),
    )
    assert code == 0
    assert len(store.rows) == 1
    assert store.rows[0]["status"] == "active"
    joined = "\n".join(logs)
    assert "fingerprint=" in joined
    assert _SECRET not in joined
    assert "gsk_" not in joined


def test_aad_purpose_matches_overlay_byok_module() -> None:
    pytest.importorskip("digillm.client", reason="optional; constants still pinned locally")
    from digiquant.dashboard.overlay.byok import BYOK_AAD_PURPOSE as live
    from digiquant.dashboard.overlay.byok import LLM_PROVIDERS as live_providers

    assert BYOK_AAD_PURPOSE == live
    assert LLM_PROVIDERS == live_providers
