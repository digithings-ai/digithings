"""Shared webset driver (#4170): in-process run ownership for HTTP and MCP.

Both serving entrypoints carry the same driver:

- the FastAPI app lifespan (``digisearch.server._lifespan``), and
- the FastMCP server lifespan (``digisearch.mcp_server.mcp``).

:func:`webset_task_lifespan` owns one ``asyncio.TaskGroup`` per invocation,
installs a :class:`WebsetTaskScheduler` on the service facade
(``set_scheduler``), re-schedules the startup-resume union of incomplete
websets, and on shutdown undoes the seam first, then cancels every tracked
run/backfill.

The install lifetime is set by the host, not by this module:

- the FastAPI lifespan spans the HTTP serving window;
- the stdio MCP lifespan spans the process (FastMCP runs once per process);
- the streamable-http MCP lifespan is entered **once per client session** by
  the installed ``mcp`` 1.26.0 FastMCP, so the driver, its ``TaskGroup``, and
  the seam install last only for that session.

Because ``set_scheduler`` and ``WEBSET_TASKS`` are process-global, overlapping
streamable-http sessions can uninstall or cancel each other's runs; the
reference-counted install is tracked in
https://github.com/digithings-ai/digithings/issues/4189. HTTP and MCP
processes otherwise stay independent: each owns its own scheduler instance
and the ``WEBSET_TASKS`` registry is per-process.

No HTTP-app import lives here, so either entrypoint can carry the lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from digisearch.websets import service as websets_service
from digisearch.websets.models import Webset, WebsetItem
from digisearch.websets.runner import (
    WEBSET_TASKS,
    backfill_enrichment,
    guard_webset_task,
    schedule_webset_task,
)
from digisearch.websets.store import WebsetStoreError
from digisearch.websets.store import get_store as get_webset_store

logger = logging.getLogger(__name__)

__all__ = [
    "WebsetTaskScheduler",
    "webset_task_lifespan",
]


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

    One instance is installed per :func:`webset_task_lifespan` invocation, so
    its lifetime is the HTTP serving window, an MCP client session
    (streamable-http), or the MCP process (stdio) — see the module docstring.
    The seam itself is process-global: a later install replaces an earlier
    session's scheduler, and ``cancel_all`` cancels every ``WEBSET_TASKS``
    entry in the process, not only its own instance's. Per-process
    (reference-counted) install semantics are tracked in
    https://github.com/digithings-ai/digithings/issues/4189.
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


@asynccontextmanager
async def webset_task_lifespan(_app: object | None = None) -> AsyncIterator[None]:
    """Install and own the webset scheduler for one lifespan invocation.

    Entered by the FastAPI lifespan (``server._lifespan``, after its
    fail-closed backend gate) and by the FastMCP lifespan
    (``mcp_server.mcp``); ``_app`` is the hosting app instance and is unused.
    The TaskGroup wraps the invocation, so schedules from any surface stay
    cancelable at teardown; ``set_scheduler`` is undone first so no new work
    can be scheduled mid-teardown.

    How long that invocation lasts is the host's decision: the FastAPI
    lifespan spans the HTTP serving window and the stdio MCP lifespan spans
    the process, but FastMCP on streamable-http enters this context manager
    once per MCP client session, so the install lasts for that session only.
    ``set_scheduler`` and ``WEBSET_TASKS`` are process-global, so overlapping
    streamable-http sessions can null or cancel each other's runs — tracked in
    https://github.com/digithings-ai/digithings/issues/4189.
    """
    async with asyncio.TaskGroup() as task_group:
        scheduler = WebsetTaskScheduler(task_group)
        websets_service.set_scheduler(scheduler)
        await _resume_incomplete_websets(task_group)
        try:
            yield
        finally:
            websets_service.set_scheduler(None)
            scheduler.cancel_all()
