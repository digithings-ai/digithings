"""Shared webset driver (#4170): the in-process scheduler both entrypoints carry.

Offline only: every store/runner seam is monkeypatched and no real store file is
opened. Pins the shared lifespan install/teardown protocol (AC1), the
startup-resume scheduling + store-failure tolerance (AC2), the unchanged
scheduler delegation incl. the ``WEBSET_TASKS`` dedupe (AC3), and the FastMCP
lifespan wiring (AC4).

``@pytest.mark.unit`` on every test.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from collections.abc import Awaitable
from typing import Any

import pytest
from digisearch.websets import driver
from digisearch.websets import runner as runner_module
from digisearch.websets import service as service_module
from digisearch.websets.models import VerificationCriterion, Webset
from digisearch.websets.store import WebsetStoreError

pytestmark = pytest.mark.unit


class _FakeStore:
    """Fake webset store: records the calling thread, raises on demand."""

    def __init__(
        self, incomplete: list[Webset] | None = None, *, error: Exception | None = None
    ) -> None:
        self.incomplete = list(incomplete or [])
        self.error = error
        self.threads: list[int] = []

    def list_incomplete_websets(self) -> list[Webset]:
        self.threads.append(threading.get_ident())
        if self.error is not None:
            raise self.error
        return self.incomplete


def _webset(*, mode: str = "llm") -> Webset:
    return Webset(
        criteria=[VerificationCriterion(name="relevance", rule="is relevant")],
        verification_mode=mode,
    )


async def _never(*_args: Any, **_kwargs: Any) -> None:
    await asyncio.Event().wait()


# ── AC1: the shared lifespan installs, tears down, and cancels ────────────────


@pytest.mark.unit
def test_shared_lifespan_installs_and_tears_down_scheduler(monkeypatch):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _run() -> None:
        async with driver.webset_task_lifespan(None):
            assert isinstance(installed[-1], driver.WebsetTaskScheduler)
        assert installed[-1] is None

    asyncio.run(_run())
    assert len(installed) == 2


@pytest.mark.unit
def test_shared_lifespan_cancels_tracked_runs_on_exit(monkeypatch):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    monkeypatch.setattr(runner_module, "run_webset_async", _never)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)
    runner_module.WEBSET_TASKS.clear()

    async def _run() -> asyncio.Task[Any]:
        async with driver.webset_task_lifespan(None):
            scheduler = installed[-1]
            scheduler.schedule_run("ws_1")
            await asyncio.sleep(0)
            task = runner_module.WEBSET_TASKS["ws_1"]
            assert not task.done()
            return task

    task = asyncio.run(_run())
    assert task.cancelled()
    assert runner_module.WEBSET_TASKS == {}


@pytest.mark.unit
def test_shared_lifespan_cancels_tracked_backfills_on_exit(monkeypatch):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    monkeypatch.setattr(driver, "backfill_enrichment", _never)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _run() -> asyncio.Task[Any]:
        async with driver.webset_task_lifespan(None):
            scheduler = installed[-1]
            scheduler.schedule_backfill("ws_1", "wse_1")
            await asyncio.sleep(0)
            return next(iter(scheduler._backfills))

    task = asyncio.run(_run())
    assert task.cancelled()


# ── AC2: startup resume ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_resume_schedules_incomplete_websets_with_persisted_modes(monkeypatch):
    websets = [_webset(mode="llm"), _webset(mode="rules")]
    store = _FakeStore(websets)
    monkeypatch.setattr(driver, "get_webset_store", lambda: store)
    scheduled: list[tuple[Any, str, str]] = []

    def _record(
        task_group: asyncio.TaskGroup, webset_id: str, *, verification_mode: str = "llm"
    ) -> None:
        scheduled.append((task_group, webset_id, verification_mode))

    monkeypatch.setattr(driver, "schedule_webset_task", _record)
    main_thread = threading.get_ident()

    async def _run() -> None:
        async with driver.webset_task_lifespan(None):
            pass

    asyncio.run(_run())
    assert [(webset_id, mode) for _, webset_id, mode in scheduled] == [
        (websets[0].id, "llm"),
        (websets[1].id, "rules"),
    ]
    assert scheduled[0][0] is scheduled[1][0]
    assert store.threads and store.threads[0] != main_thread


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        OSError("websets home is not readable"),
        sqlite3.Error("database is locked"),
        WebsetStoreError("ledger locked", code="store_locked"),
    ],
)
def test_resume_store_failure_logs_and_does_not_abort(monkeypatch, caplog, error):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore(error=error))
    entered = False

    async def _run() -> None:
        nonlocal entered
        async with driver.webset_task_lifespan(None):
            entered = True

    with caplog.at_level(logging.WARNING, logger="digisearch.websets.driver"):
        asyncio.run(_run())
    assert entered is True
    assert any(
        "webset startup resume skipped; store unavailable" in record.getMessage()
        for record in caplog.records
    )


# ── AC3: scheduler delegation ─────────────────────────────────────────────────


@pytest.mark.unit
def test_schedule_run_delegates_with_mode(monkeypatch):
    calls: list[tuple[Any, str, str]] = []

    def _record(
        task_group: asyncio.TaskGroup, webset_id: str, *, verification_mode: str = "llm"
    ) -> None:
        calls.append((task_group, webset_id, verification_mode))

    monkeypatch.setattr(driver, "schedule_webset_task", _record)

    async def _run() -> None:
        async with asyncio.TaskGroup() as group:
            scheduler = driver.WebsetTaskScheduler(group)
            scheduler.schedule_run("ws_1")
            scheduler.schedule_run("ws_2", verification_mode="rules")

    asyncio.run(_run())
    assert [(webset_id, mode) for _, webset_id, mode in calls] == [
        ("ws_1", "llm"),
        ("ws_2", "rules"),
    ]
    assert calls[0][0] is calls[1][0]


@pytest.mark.unit
def test_schedule_run_dedupes_via_webset_tasks_registry(monkeypatch):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    monkeypatch.setattr(runner_module, "run_webset_async", _never)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)
    runner_module.WEBSET_TASKS.clear()

    async def _run() -> tuple[asyncio.Task[Any], asyncio.Task[Any]]:
        async with driver.webset_task_lifespan(None):
            scheduler = installed[-1]
            scheduler.schedule_run("ws_1")
            await asyncio.sleep(0)
            first = runner_module.WEBSET_TASKS["ws_1"]
            scheduler.schedule_run("ws_1")
            return first, runner_module.WEBSET_TASKS["ws_1"]

    first, second = asyncio.run(_run())
    assert first is second
    assert runner_module.WEBSET_TASKS == {}


@pytest.mark.unit
def test_schedule_backfill_tracks_task_and_delegates(monkeypatch):
    calls: list[tuple[str, str]] = []
    guards: list[tuple[str, str]] = []

    async def _backfill(webset_id: str, enrichment_id: str) -> list[Any]:
        calls.append((webset_id, enrichment_id))
        return []

    async def _guard(coro: Awaitable[Any], *, webset_id: str, kind: str = "run") -> Any:
        guards.append((webset_id, kind))
        return await coro

    monkeypatch.setattr(driver, "backfill_enrichment", _backfill)
    monkeypatch.setattr(driver, "guard_webset_task", _guard)

    async def _run() -> set[Any]:
        async with asyncio.TaskGroup() as group:
            scheduler = driver.WebsetTaskScheduler(group)
            scheduler.schedule_backfill("ws_1", "wse_1")
            assert len(scheduler._backfills) == 1
        return scheduler._backfills

    leftover = asyncio.run(_run())
    assert calls == [("ws_1", "wse_1")]
    assert guards == [("ws_1", "backfill")]
    assert leftover == set()


# ── AC4: FastMCP carries the driver lifespan ──────────────────────────────────


@pytest.mark.unit
def test_fastmcp_instance_carries_driver_lifespan(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from digisearch import mcp_server

    assert mcp_server.mcp.settings.lifespan is driver.webset_task_lifespan

    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _run() -> None:
        lifespan = mcp_server.mcp.settings.lifespan
        assert lifespan is not None
        async with lifespan(mcp_server.mcp):
            assert isinstance(installed[-1], driver.WebsetTaskScheduler)
        assert installed[-1] is None

    asyncio.run(_run())
