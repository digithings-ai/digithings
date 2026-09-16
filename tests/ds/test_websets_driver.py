"""Shared webset driver (#4170) and its per-process ref-counted install (#4189).

Offline only: every store/runner seam is monkeypatched and no real store file is
opened. Pins the shared lifespan install/teardown protocol (AC1), the
startup-resume scheduling + store-failure tolerance (AC2), the unchanged
scheduler delegation incl. the ``WEBSET_TASKS`` dedupe (AC3), the FastMCP
lifespan wiring (AC4), the #4189 ref-counting: overlapping sessions share one
install, only the last exit tears down and cancels, resume runs once per install
window (not per session), a cancelled entry leaks nothing, and a later install
window is fresh, and the #4202 loop-safe install guard: sequential
``asyncio.run`` windows across event loops install/tear down cleanly, a
supervisor that dies before ready clears the driver state for the next window, a
dead supervisor at depth ≥ 1 re-installs fresh, and a concurrent install on a
different event loop raises ``RuntimeError``.

``@pytest.mark.unit`` on every test.
"""

from __future__ import annotations

import asyncio
import contextlib
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


@pytest.fixture(autouse=True)
def _reset_driver_state():
    driver._active = 0
    driver._supervisor = None
    driver._stop = None
    driver._supervisor_loop = None
    yield
    driver._active = 0
    driver._supervisor = None
    driver._stop = None
    driver._supervisor_loop = None


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


# ── #4189: one ref-counted per-process install ───────────────────────────────


@pytest.mark.unit
def test_overlapping_sessions_share_one_install_and_teardown_on_last_exit(monkeypatch):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    monkeypatch.setattr(runner_module, "run_webset_async", _never)
    resumes: list[int] = []

    async def _resume(task_group: asyncio.TaskGroup) -> None:
        resumes.append(1)

    monkeypatch.setattr(driver, "_resume_incomplete_websets", _resume)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)
    runner_module.WEBSET_TASKS.clear()

    async def _run() -> None:
        a = driver.webset_task_lifespan(None)
        await a.__aenter__()
        scheduler_a = installed[-1]
        assert isinstance(scheduler_a, driver.WebsetTaskScheduler)
        scheduler_a.schedule_run("ws_a")
        task_a = runner_module.WEBSET_TASKS["ws_a"]

        b = driver.webset_task_lifespan(None)
        await b.__aenter__()
        assert installed == [scheduler_a]
        assert driver._active == 2
        assert resumes == [1]

        await b.__aexit__(None, None, None)
        assert installed == [scheduler_a]
        assert driver._active == 1
        assert not task_a.done()

        scheduler_a.schedule_run("ws_b")
        task_b = runner_module.WEBSET_TASKS["ws_b"]
        assert not task_b.done()

        await a.__aexit__(None, None, None)
        assert installed[-1] is None
        assert task_a.cancelled()
        assert task_b.cancelled()

    asyncio.run(_run())
    assert resumes == [1]
    assert len(installed) == 2
    assert installed[-1] is None
    assert runner_module.WEBSET_TASKS == {}
    assert driver._active == 0
    assert driver._supervisor is None
    assert driver._stop is None


@pytest.mark.unit
def test_single_session_resumes_once(monkeypatch):
    resumes: list[int] = []

    async def _resume(task_group: asyncio.TaskGroup) -> None:
        resumes.append(1)

    monkeypatch.setattr(driver, "_resume_incomplete_websets", _resume)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _run() -> None:
        async with driver.webset_task_lifespan(None):
            pass

    asyncio.run(_run())
    assert resumes == [1]
    assert len(installed) == 2


@pytest.mark.unit
def test_cancelled_entry_leaves_no_installed_scheduler_or_orphan_tasks(monkeypatch):
    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())
    monkeypatch.setattr(runner_module, "run_webset_async", _never)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)
    runner_module.WEBSET_TASKS.clear()
    resume_started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_resume(task_group: asyncio.TaskGroup) -> None:
        driver.schedule_webset_task(task_group, "ws_orphan")
        resume_started.set()
        await release.wait()

    monkeypatch.setattr(driver, "_resume_incomplete_websets", _slow_resume)

    async def _run() -> None:
        entry = asyncio.create_task(driver.webset_task_lifespan(None).__aenter__())
        await asyncio.wait_for(resume_started.wait(), timeout=5)
        assert isinstance(installed[-1], driver.WebsetTaskScheduler)
        orphan = runner_module.WEBSET_TASKS["ws_orphan"]
        assert not orphan.done()

        entry.cancel()
        with pytest.raises(asyncio.CancelledError):
            await entry

        assert installed[-1] is None
        assert orphan.cancelled()
        assert runner_module.WEBSET_TASKS == {}
        assert driver._active == 0
        assert driver._supervisor is None
        assert driver._stop is None

        release.set()
        async with driver.webset_task_lifespan(None):
            assert isinstance(installed[-1], driver.WebsetTaskScheduler)
        assert installed[-1] is None
        assert driver._active == 0

    asyncio.run(_run())


@pytest.mark.unit
def test_sequential_install_windows_install_and_resume_afresh(monkeypatch):
    resumes: list[int] = []

    async def _resume(task_group: asyncio.TaskGroup) -> None:
        resumes.append(1)

    monkeypatch.setattr(driver, "_resume_incomplete_websets", _resume)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _run() -> tuple[Any, Any]:
        async with driver.webset_task_lifespan(None):
            first = installed[-1]
        assert installed[-1] is None
        async with driver.webset_task_lifespan(None):
            second = installed[-1]
        assert installed[-1] is None
        return first, second

    first, second = asyncio.run(_run())
    assert isinstance(first, driver.WebsetTaskScheduler)
    assert isinstance(second, driver.WebsetTaskScheduler)
    assert first is not second
    assert resumes == [1, 1]
    assert installed == [first, None, second, None]


# ── #4202: loop-safe install guard ────────────────────────────────────────────


@pytest.mark.unit
def test_sequential_windows_across_event_loops_install_and_tear_down(monkeypatch):
    """M1 pin (#4202): a second event loop must not inherit the first's lock.

    Two ``asyncio.run`` windows — two distinct event loops in one process —
    each with overlapping sessions that make the install lock contend (the
    waiting session is what bound the old module-level lock to the first loop
    and raised ``RuntimeError: ... bound to a different event loop`` here).
    """
    resumes: list[int] = []
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _window() -> None:
        release = asyncio.Event()
        resume_started = asyncio.Event()

        async def _slow_resume(task_group: asyncio.TaskGroup) -> None:
            resumes.append(1)
            resume_started.set()
            await release.wait()

        monkeypatch.setattr(driver, "_resume_incomplete_websets", _slow_resume)

        first = driver.webset_task_lifespan(None)
        first_enter = asyncio.create_task(first.__aenter__())
        await resume_started.wait()
        assert driver._active == 0

        second = driver.webset_task_lifespan(None)
        second_enter = asyncio.create_task(second.__aenter__())
        await asyncio.sleep(0)
        release.set()
        await first_enter
        await second_enter
        assert driver._active == 2
        scheduler = installed[-1]
        assert isinstance(scheduler, driver.WebsetTaskScheduler)

        await second.__aexit__(None, None, None)
        assert driver._active == 1
        assert installed[-1] is scheduler

        await first.__aexit__(None, None, None)
        assert driver._active == 0
        assert installed[-1] is None

    asyncio.run(_window())
    asyncio.run(_window())

    assert resumes == [1, 1]
    assert len(installed) == 4
    assert installed[0] is not installed[2]
    assert installed[-1] is None
    assert driver._active == 0
    assert driver._supervisor is None
    assert driver._stop is None


@pytest.mark.unit
def test_supervisor_failure_before_ready_clears_state_and_next_window_installs(monkeypatch):
    """#4202: a supervisor dying before ready surfaces the failure, clears the
    driver state, and leaves the next install window healthy."""
    monkeypatch.setattr(
        driver, "get_webset_store", lambda: _FakeStore(error=ValueError("webset ledger corrupt"))
    )
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _broken() -> None:
        with pytest.raises(ExceptionGroup) as excinfo:
            async with driver.webset_task_lifespan(None):
                pass
        assert any(isinstance(exc, ValueError) for exc in excinfo.value.exceptions)

    asyncio.run(_broken())
    assert driver._active == 0
    assert driver._supervisor is None
    assert driver._stop is None
    assert driver._supervisor_loop is None
    assert installed[-1] is None

    monkeypatch.setattr(driver, "get_webset_store", lambda: _FakeStore())

    async def _healthy() -> None:
        async with driver.webset_task_lifespan(None):
            pass

    asyncio.run(_healthy())
    assert isinstance(installed[-2], driver.WebsetTaskScheduler)
    assert installed[-1] is None
    assert driver._active == 0
    assert driver._supervisor is None
    assert driver._stop is None


@pytest.mark.unit
def test_dead_supervisor_at_depth_reinstalls_fresh(monkeypatch):
    """#4202: a dead supervisor at depth ≥ 1 is replaced on the next entry."""
    resumes: list[int] = []

    async def _resume(task_group: asyncio.TaskGroup) -> None:
        resumes.append(1)

    monkeypatch.setattr(driver, "_resume_incomplete_websets", _resume)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    async def _run() -> None:
        first = driver.webset_task_lifespan(None)
        await first.__aenter__()
        first_scheduler = installed[-1]
        assert isinstance(first_scheduler, driver.WebsetTaskScheduler)

        dead = driver._supervisor
        assert dead is not None
        dead.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dead
        assert dead.done()
        assert installed[-1] is None

        second = driver.webset_task_lifespan(None)
        await second.__aenter__()
        second_scheduler = installed[-1]
        assert isinstance(second_scheduler, driver.WebsetTaskScheduler)
        assert second_scheduler is not first_scheduler
        assert driver._active == 2
        assert resumes == [1, 1]

        await second.__aexit__(None, None, None)
        assert driver._active == 1
        assert installed[-1] is second_scheduler

        await first.__aexit__(None, None, None)
        assert driver._active == 0
        assert installed[-1] is None

    asyncio.run(_run())
    assert resumes == [1, 1]
    assert installed[-1] is None
    assert driver._active == 0
    assert driver._supervisor is None
    assert driver._stop is None


@pytest.mark.unit
def test_concurrent_install_on_another_event_loop_raises(monkeypatch):
    """#4202: a second loop entering while an install is active must fail loud."""
    resumes: list[int] = []

    async def _resume(task_group: asyncio.TaskGroup) -> None:
        resumes.append(1)

    monkeypatch.setattr(driver, "_resume_incomplete_websets", _resume)
    installed: list[Any] = []
    monkeypatch.setattr(service_module, "set_scheduler", installed.append)

    entered = threading.Event()
    release = threading.Event()
    outcome: list[Exception] = []

    async def _holder() -> None:
        async with driver.webset_task_lifespan(None):
            entered.set()
            await asyncio.to_thread(release.wait, 20)

    def _second_loop() -> None:
        async def _attempt() -> None:
            async with driver.webset_task_lifespan(None):
                pass

        try:
            asyncio.run(_attempt())
        except Exception as exc:
            outcome.append(exc)
        finally:
            release.set()

    def _run_holder() -> None:
        asyncio.run(_holder())

    holder = threading.Thread(target=_run_holder, daemon=True)
    holder.start()
    assert entered.wait(20)

    worker = threading.Thread(target=_second_loop, daemon=True)
    worker.start()
    worker.join(timeout=20)
    release.set()
    holder.join(timeout=20)

    assert not worker.is_alive()
    assert not holder.is_alive()
    assert len(outcome) == 1
    assert isinstance(outcome[0], RuntimeError)
    assert "another event loop" in str(outcome[0])
    assert resumes == [1]
    assert installed[-1] is None
    assert driver._active == 0
    assert driver._supervisor is None
    assert driver._stop is None


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
