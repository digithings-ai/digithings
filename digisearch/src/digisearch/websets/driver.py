"""Shared webset driver (#4170): in-process run ownership for HTTP and MCP.

Both serving entrypoints carry the same driver:

- the FastAPI app lifespan (``digisearch.server._lifespan``), and
- the FastMCP server lifespan (``digisearch.mcp_server.mcp``).

:func:`webset_task_lifespan` owns one install window at a time per process,
reference-counted across concurrent lifespan invocations (#4189). The first
entry starts a supervisor coroutine that owns the ``asyncio.TaskGroup``,
installs a :class:`WebsetTaskScheduler` on the service facade
(``set_scheduler``), re-schedules the startup-resume union of incomplete
websets, and then waits for the last exit; teardown undoes the seam first, then
cancels every tracked run/backfill.

The install guard is a **per-running-loop** lock (#4202): the lock is reused
only while the running loop is unchanged, so a process that opens a fresh loop
per window (two sequential ``asyncio.run`` calls, for example) installs,
resumes, and tears down cleanly in each. Concurrent installs on *different*
event loops in one process remain unsupported: entering while an install on
another loop is active or still starting up raises ``RuntimeError`` instead of
corrupting the reference count.

The install lifetime is therefore the install window (first entry to last
exit), not the lifespan invocation:

- the FastAPI lifespan spans the HTTP serving window (exactly one invocation);
- the stdio MCP lifespan spans the process (FastMCP runs once per process);
- FastMCP on streamable-http (digisearch's only transport) enters the lifespan
  once per client session, so concurrent sessions share one install: install on
  the first entry, teardown on the last exit. An earlier session's exit never
  nulls the seam or cancels another still-active session's runs, and the
  startup resume runs once per install window, not once per session. Exit
  followed by a later entry is a fresh window (new scheduler, new resume).

HTTP and MCP processes stay independent: each owns its own scheduler instance
and the ``WEBSET_TASKS`` registry is per-process.

Each install window also runs the scheduled tick loop (#4221): one pass per
``WEBSET_TICK_SECONDS`` re-reads every monitor (``store.list_all_monitors``)
and refreshes each due, unpaused monitor through the same
``websets_service.trigger_monitor`` path the manual route uses, containing
per-monitor faults so the pass survives. ``last_tick`` is in-process state owned
by the install window, so a restart re-anchors every cadence at its first
post-install sighting. Nothing ticks without an installed driver.

A second TaskGroup child owns automated webhook re-delivery (#4226): one pass
per ``WEBSET_REDELIVERY_SECONDS`` reads the failed, due ledger rows
(``store.list_due_webhook_deliveries``) and re-attempts each through
``websets.events.redeliver_webhook`` — the same signed POST core, current-secret
signing, and the bounded attempts/backoff the events module pins. Rows are
processed serially under a per-pass in-flight guard, each row's fault is
contained, and the pass is torn down promptly by the stop event, so a failed
delivery recorded while the process was down is retried once the driver
installs. Nothing re-delivers without an installed driver.

No HTTP-app import lives here, so either entrypoint can carry the lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from digisearch.websets import service as websets_service
from digisearch.websets.events import redeliver_webhook
from digisearch.websets.models import Webset, WebsetItem, WebsetMonitor
from digisearch.websets.runner import (
    WEBSET_TASKS,
    backfill_enrichment,
    guard_webset_task,
    schedule_webset_task,
)
from digisearch.websets.store import WebhookDelivery, WebsetStoreError
from digisearch.websets.store import get_store as get_webset_store

logger = logging.getLogger(__name__)

__all__ = [
    "WEBSET_REDELIVERY_SECONDS",
    "WEBSET_TICK_SECONDS",
    "WebsetTaskScheduler",
    "webset_task_lifespan",
]

#: Seconds between scheduled tick passes (monkeypatchable; in-process state).
WEBSET_TICK_SECONDS: float = 60.0

#: Seconds between webhook re-delivery passes (monkeypatchable; in-process state).
WEBSET_REDELIVERY_SECONDS: float = 300.0

#: Due-ledger rows a single re-delivery pass scans.
_WEBSET_REDELIVERY_BATCH = 100


def _now() -> float:
    """Monotonic seconds for tick-due math (monkeypatched with a fake clock)."""
    return time.monotonic()


def _utc_now() -> datetime:
    """UTC wall clock for ledger due-ness (monkeypatched with a fake clock)."""
    return datetime.now(UTC)


_install_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None
_supervisor_loop: asyncio.AbstractEventLoop | None = None
_active = 0
_supervisor: asyncio.Task[None] | None = None
_stop: asyncio.Event | None = None


def _install_lock_for_running_loop() -> asyncio.Lock:
    """Return the install guard, bound to the running event loop (#4202).

    An ``asyncio.Lock`` binds to the first event loop that contends it, so one
    module-level lock breaks a process that opens a fresh loop per install
    window (two sequential ``asyncio.run`` calls, for example). Reuse the lock
    only while the running loop is unchanged; a new loop gets a fresh lock.
    """
    global _install_lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _install_lock is None or _lock_loop is not loop:
        _install_lock = asyncio.Lock()
        _lock_loop = loop
    return _install_lock


class WebsetTaskScheduler:
    """TaskGroup-owned ``WebsetScheduler``: runs are TaskGroup children.

    Installed on the service facade at startup (``set_scheduler``) so every
    route/tool/service schedule ends up in the driver TaskGroup:

    - ``schedule_run`` delegates to ``runner.schedule_webset_task``, which owns
      the ``WEBSET_TASKS`` registry entry, the ``(webset_id, ok|error)``
      done-callback, and the single-drive guard;
    - ``schedule_backfill`` opens a tracked ``runner.backfill_enrichment`` task
      (the ``add_enrichment`` drain path);
    - ``cancel_all`` cancels every tracked task first so a clean shutdown never
      hangs on an in-flight pass (spec § Async lifecycle: a selected webset at
      boot is an orphan).

    One instance is installed per process install window (see
    :func:`webset_task_lifespan`), so its lifetime spans the HTTP serving
    window, the MCP process (stdio), or the union of concurrent streamable-http
    MCP client sessions. The seam itself is process-global: ``cancel_all``
    cancels every ``WEBSET_TASKS`` entry in the process, not only its own
    instance's — which is exactly the last-exit teardown of ``#4189``.
    """

    def __init__(self, task_group: asyncio.TaskGroup) -> None:
        self._task_group = task_group
        self._backfills: set[asyncio.Task[list[WebsetItem] | None]] = set()

    def schedule_run(self, webset_id: str, *, verification_mode: str = "llm") -> None:
        schedule_webset_task(self._task_group, webset_id, verification_mode=verification_mode)

    def schedule_backfill(self, webset_id: str, enrichment_id: str) -> None:
        task = self._task_group.create_task(
            guard_webset_task(
                backfill_enrichment(webset_id, enrichment_id),
                webset_id=webset_id,
                kind="backfill",
            )
        )
        self._backfills.add(task)
        task.add_done_callback(self._backfills.discard)

    def cancel_all(self) -> None:
        for task in [*WEBSET_TASKS.values(), *self._backfills]:
            task.cancel()


def _load_incomplete_websets() -> list[Webset]:
    """Startup-resume selector query, run on a worker thread by the driver."""
    return get_webset_store().list_incomplete_websets()


def _load_all_monitors() -> list[WebsetMonitor]:
    """Tick selector query, run on a worker thread by the driver."""
    return get_webset_store().list_all_monitors()


def _load_due_deliveries(now: datetime, limit: int) -> list[WebhookDelivery]:
    """Re-delivery selector query, run on a worker thread by the driver."""
    return get_webset_store().list_due_webhook_deliveries(now=now, limit=limit)


def _redeliver_delivery(delivery: WebhookDelivery, now: datetime) -> WebhookDelivery:
    """Re-attempt one due ledger row on a worker thread (thread-bound sqlite)."""
    return redeliver_webhook(get_webset_store(), delivery, now=now)


async def _resume_incomplete_websets(task_group: asyncio.TaskGroup) -> None:
    """Re-schedule every orphaned webset as a registry-tracked run.

    § Async lifecycle: the selector is the store's union of websets still
    ``running`` and websets holding a non-terminal ``running`` search; each
    selected webset is re-scheduled via ``run_webset_async`` (here through
    ``schedule_webset_task``, so the run is visible in ``WEBSET_TASKS`` like
    every other pass) under its persisted ``verification_mode``. The store
    query runs on a worker thread because the sqlite connection is thread-bound.
    A store that cannot be opened must not block startup: the routes will
    surface the same fault per request.
    """
    try:
        incomplete = await asyncio.to_thread(_load_incomplete_websets)
    except (OSError, sqlite3.Error, WebsetStoreError) as exc:
        logger.warning("webset startup resume skipped; store unavailable: %s", exc)
        return
    for webset in incomplete:
        logger.info("webset startup resume scheduled webset_id=%s", webset.id)
        schedule_webset_task(task_group, webset.id, verification_mode=webset.verification_mode)


async def _tick_once(last_tick: dict[tuple[str, str], float], stop: asyncio.Event) -> None:
    """Run one tick pass: refresh every due, unpaused monitor.

    Due-selection per monitor from ``store.list_all_monitors``:

    - ``paused`` monitors are skipped and never anchored, so the first pass
      after a resume anchors their cadence then;
    - the first sight of a ``(webset_id, monitor_id)`` pair anchors
      ``last_tick = now`` instead of firing, so an install (or restart — the map
      is per install window) never emits a refresh storm for cadences that
      elapsed while the process was down;
    - a monitor whose webset already has a run in ``WEBSET_TASKS`` is skipped
      (dedupe: manual triggers and prior ticks share the registry);
    - due is ``now - last_tick >= interval_seconds``; ``last_tick`` is recorded
      at trigger time so cadence stays interval-spaced.

    ``last_tick`` is recorded for service-skipped monitors too
    (``webset_terminal``, ``search_not_found``, ...) so a doomed refresh is
    retried at the monitor's interval instead of every tick. Store work runs on
    worker threads (thread-bound sqlite, same as :func:`_resume_incomplete_websets`);
    a store that cannot be opened skips the pass, and per-monitor failures
    (``WebsetServiceError`` and broad ``Exception``) are logged and contained —
    one bad monitor never kills the pass, the tick task, or the TaskGroup.
    ``stop`` is checked between monitors so teardown does not wait out a pass.
    """
    try:
        monitors = await asyncio.to_thread(_load_all_monitors)
    except (OSError, sqlite3.Error, WebsetStoreError) as exc:
        logger.warning("webset tick skipped; store unavailable: %s", exc)
        return
    now = _now()
    for monitor in monitors:
        if stop.is_set():
            return
        if monitor.paused:
            continue
        key = (monitor.webset_id, monitor.id)
        anchor = last_tick.get(key)
        if anchor is None:
            last_tick[key] = now
            continue
        if monitor.webset_id in WEBSET_TASKS:
            continue
        if now - anchor < monitor.interval_seconds:
            continue
        last_tick[key] = now
        try:
            await asyncio.to_thread(websets_service.trigger_monitor, monitor.webset_id, monitor.id)
        except websets_service.WebsetServiceError as exc:
            logger.warning(
                "webset tick refresh skipped webset_id=%s monitor_id=%s: %s",
                monitor.webset_id,
                monitor.id,
                exc,
            )
        except Exception:
            logger.exception(
                "webset tick refresh failed webset_id=%s monitor_id=%s",
                monitor.webset_id,
                monitor.id,
            )


async def _tick_loop(stop: asyncio.Event) -> None:
    """One tick pass per ``WEBSET_TICK_SECONDS`` until *stop* is set.

    Waiting on the stop event with a tick-interval timeout (rather than a plain
    sleep) keeps teardown prompt: a set stop event ends the wait immediately, an
    in-flight pass finishes and then observes the stop before the next pass, and
    the task is cancel-safe besides. ``last_tick`` is created here, so it lives
    exactly one install window. A pass-level escape is logged here instead of
    raised: the tick task is a TaskGroup child, so an uncontained raise would
    cancel the sibling runs.
    """
    last_tick: dict[tuple[str, str], float] = {}
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=WEBSET_TICK_SECONDS)
        except TimeoutError:
            pass
        if stop.is_set():
            return
        try:
            await _tick_once(last_tick, stop)
        except Exception:
            logger.exception("webset tick pass failed")


async def _redeliver_once(stop: asyncio.Event) -> None:
    """Run one re-delivery pass: re-attempt every due failed ledger row.

    Due selection is the store's ``list_due_webhook_deliveries`` (failed,
    unexhausted, scheduled at/before the injected wall clock) run on a worker
    thread — thread-bound sqlite, same as the tick pass. Rows are processed
    serially and pinned in a per-pass in-flight set, so one pass cannot
    double-process a pair (even if a snapshot carried it twice) and a row whose
    attempt is still running is never re-picked. Each row's re-delivery runs
    under its own containment (a fault is logged and the next row still runs),
    a store that cannot be opened skips the pass, and ``stop`` is checked
    between rows so teardown does not wait out a pass.
    """
    now = _utc_now()
    try:
        due = await asyncio.to_thread(_load_due_deliveries, now, _WEBSET_REDELIVERY_BATCH)
    except (OSError, sqlite3.Error, WebsetStoreError) as exc:
        logger.warning("webset webhook redelivery skipped; store unavailable: %s", exc)
        return
    in_flight: set[tuple[str, str]] = set()
    for delivery in due:
        if stop.is_set():
            return
        key = (delivery.webhook_id, delivery.event_id)
        if key in in_flight:
            continue
        in_flight.add(key)
        try:
            await asyncio.to_thread(_redeliver_delivery, delivery, now)
        except Exception:
            logger.exception(
                "webset webhook redelivery failed webhook_id=%s event_id=%s",
                delivery.webhook_id,
                delivery.event_id,
            )


async def _redelivery_loop(stop: asyncio.Event) -> None:
    """One re-delivery pass per ``WEBSET_REDELIVERY_SECONDS`` until *stop* is set.

    Mirrors :func:`_tick_loop`: waiting on the stop event with an interval
    timeout (rather than a plain sleep) keeps teardown prompt — a set stop event
    ends the wait immediately, an in-flight pass finishes and then observes the
    stop before the next pass, and the task is cancel-safe besides. A pass-level
    escape is logged here instead of raised: the task is a TaskGroup child, so
    an uncontained raise would cancel the sibling runs. The loop is created by
    :func:`_supervise`, so it lives exactly one install window and nothing
    re-delivers without an installed driver.
    """
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=WEBSET_REDELIVERY_SECONDS)
        except TimeoutError:
            pass
        if stop.is_set():
            return
        try:
            await _redeliver_once(stop)
        except Exception:
            logger.exception("webset webhook redelivery pass failed")


async def _supervise(stop: asyncio.Event, ready: asyncio.Event) -> None:
    """Own one process install: TaskGroup, seam install, resume, tick, teardown."""
    async with asyncio.TaskGroup() as task_group:
        scheduler = WebsetTaskScheduler(task_group)
        websets_service.set_scheduler(scheduler)
        try:
            await _resume_incomplete_websets(task_group)
            task_group.create_task(_tick_loop(stop))
            task_group.create_task(_redelivery_loop(stop))
            ready.set()
            await stop.wait()
        finally:
            websets_service.set_scheduler(None)
            scheduler.cancel_all()


async def _await_ready(ready: asyncio.Event, supervisor: asyncio.Task[None]) -> None:
    """Wait for the supervisor's install, or re-raise its failure."""
    waiter = asyncio.ensure_future(ready.wait())
    try:
        await asyncio.wait({waiter, supervisor}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiter
    if not ready.is_set():
        supervisor.result()
        raise RuntimeError("webset driver supervisor exited before signaling ready")


@asynccontextmanager
async def webset_task_lifespan(_app: object | None = None) -> AsyncIterator[None]:
    """Install and own the webset scheduler per process, reference-counted.

    Entered by the FastAPI lifespan (``server._lifespan``, after its
    fail-closed backend gate) and by the FastMCP lifespan
    (``mcp_server.mcp``); ``_app`` is the hosting app instance and is unused.
    The first concurrent entry starts the supervisor and waits for its install
    (TaskGroup + ``set_scheduler`` + startup resume); later entries only bump
    the depth. Exit decrements, and only the last exit signals the supervisor
    and awaits its teardown (``set_scheduler(None)`` then ``cancel_all``), so
    one session closing never uninstalls or cancels another session's runs. An
    entry cancelled while waiting for the install tears its supervisor down
    instead of leaking it (#4189).

    How long that install lasts is the process's lifespan, not this
    invocation's: the FastAPI lifespan spans the HTTP serving window, the stdio
    MCP lifespan spans the process, and FastMCP on streamable-http enters this
    context manager once per MCP client session, so concurrent sessions share
    the one install. See the module docstring.

    The install guard is a per-running-loop lock (#4202): sequential windows on
    fresh event loops each install, resume, and tear down cleanly, while
    entering this context manager from a different event loop than a live
    install — active or still starting up — raises ``RuntimeError`` (one
    process must use one event loop at a time).
    """
    global _active, _stop, _supervisor, _supervisor_loop
    running_loop = asyncio.get_running_loop()
    async with _install_lock_for_running_loop():
        if (
            _supervisor_loop is not None
            and _supervisor_loop is not running_loop
            and (_active > 0 or (_supervisor is not None and not _supervisor.done()))
        ):
            raise RuntimeError(
                "webset driver is already installed on another event loop; "
                "one process must use one event loop"
            )
        if _active == 0 or _supervisor is None or _supervisor.done():
            stop = asyncio.Event()
            ready = asyncio.Event()
            supervisor = asyncio.create_task(_supervise(stop, ready))
            _stop = stop
            _supervisor = supervisor
            _supervisor_loop = running_loop
            try:
                await _await_ready(ready, supervisor)
            except BaseException:
                if _supervisor is supervisor:
                    _stop = None
                    _supervisor = None
                    _supervisor_loop = None
                    if not supervisor.done():
                        supervisor.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await supervisor
                raise
        _active += 1
    try:
        yield
    finally:
        async with _install_lock_for_running_loop():
            _active -= 1
            if _active == 0:
                stop = _stop
                supervisor = _supervisor
                _stop = None
                _supervisor = None
                _supervisor_loop = None
                if stop is not None:
                    stop.set()
                if supervisor is not None:
                    await supervisor
