"""Phase D webset runner (#4066, Task 5a) — the async settling loop.

Drives one webset to ``idle``: recall candidates through the landed Phase A seam
``search_web`` (the single pinned provider boundary, R3; direct import, R1 —
never a raw sidecar call, never the corpus ingest path, never the fetch-enriched
search variant), fetch page markdown through the non-indexing ``fetch_markdown``
(R2 — fetched pages are never indexed), settle every candidate through T3's
``settle_pending_item``/``settlement_results``, enrich through T4's
``enrich_item``, and append every event through ``websets/events.py`` (the
store's single event writer). Returns the stored ``Webset``.

Recall (R3): there is no paging parameter, so a search's ``count`` (1-100 target
VERIFIED items) is reached by query diversification — the base query plus bounded
suffix variants — with ``max_results <= 10`` per ``search_web`` call. Each
variant's batch is verified before the next variant is consulted, so reaching
``count`` stops recall early.

Lifecycle (spec § Async lifecycle, implemented verbatim):

- **Semaphore 4**: fetch/verify/enrich calls are bounded by one semaphore;
  per-item failures are contained (the item keeps a terminal state and the pass
  continues), and the store is reached only through a dedicated single worker
  thread via ``loop.run_in_executor`` — the ``asyncio.to_thread`` mechanism
  pinned to one worker, because ``WebsetStore`` is thread-bound (one sqlite
  connection per instance, ``check_same_thread`` default, WAL + busy timeout)
  and needs no in-process lock (R5).
- **Settlement routing**: every candidate is settled through T3's
  ``settle_pending_item`` (unknown verification ``mode`` is validated BEFORE
  that settlement try so it surfaces instead of being swallowed into a
  ``rejected`` verdict); items already ``verified`` are never re-verified (no
  repeated billable LLM call — the resume re-settle guard); a failed enrichment
  always writes a terminal field (``unresolved``/``skipped``), so a pending
  item/field can never block ``webset.idle`` (flag I9, T2 review note); at the
  candidate-pass end any still-``pending`` item settles ``rejected`` (fail
  closed).
- **Generation semantics**: each pass is a ``WebsetSearch`` generation; terminal
  events may re-emit under a new generation while within one generation the
  store's ``(webset_id, dedup_key)`` key dedups. ``Webset.status`` never goes
  backwards: a refresh runs while the webset stays sticky ``idle`` and is
  observed through the new search row + events.
- **Cancellation**: ``cancel_webset`` flips the row and settles searches
  ``cancelled``; the runner checks the flag before every semaphore acquisition
  and between items, lets an in-flight field finish, then marks unattempted
  fields ``skipped``. No mid-LLM ``task.cancel()``.
- **Startup resume**: :func:`resume_incomplete_websets` re-drives the union of
  websets still ``running`` and websets holding a non-terminal ``running``
  search (the store's selector), idempotently.
- **Poll-only v1 (R8)**: the fan-out target is the webset row itself; no
  scheduled tick driver and no Phase C ``Watch`` is involved (residual risk 6).
- **Ownership**: :func:`schedule_webset_task` registers every background run in
  ``WEBSET_TASKS`` with a done-callback logging ``(webset_id, ok|error)`` and
  removal on completion; bare ``asyncio.create_task`` without a handle is not
  used here.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, get_args

from digisearch.web_search.citation import normalize_url
from digisearch.web_search.fetch import fetch_markdown
from digisearch.web_search.models import WebSearchRequest
from digisearch.web_search.service import search_web
from digisearch.websets import events
from digisearch.websets.enrich import enrich_item
from digisearch.websets.models import (
    EnrichedField,
    EnrichedStatus,
    EnrichmentDef,
    EnrichmentStatus,
    Webset,
    WebsetItem,
    WebsetSearch,
)
from digisearch.websets.store import WebsetStore, WebsetStoreError, get_store
from digisearch.websets.verify import (
    VerificationMode,
    settle_pending_item,
    settlement_results,
)

logger = logging.getLogger(__name__)

__all__ = [
    "RECALL_PAGE_SIZE",
    "SEMAPHORE_SIZE",
    "WEBSET_TASKS",
    "AsyncioRunner",
    "Runner",
    "WebsetNotFoundError",
    "WebsetRecallError",
    "backfill_enrichment",
    "resume_incomplete_websets",
    "run_webset_async",
    "schedule_webset_task",
]

T = TypeVar("T")

#: Fetch/verify/enrich concurrency bound (spec § Async lifecycle).
SEMAPHORE_SIZE = 4

#: Landed ``WebSearchRequest.max_results`` ceiling per recall call (R3).
RECALL_PAGE_SIZE = 10

#: Suffixes appended to the base query; the base itself is always tried first.
_QUERY_VARIANT_SUFFIXES: tuple[str, ...] = ("latest news", "industry analysis", "market report")

#: Idle-flip retries after driving searches that arrived mid-pass (``add_search``).
_FINALIZE_ATTEMPTS = 2

_VERIFICATION_MODES = get_args(VerificationMode)

_CANCELLED_FIELD_REASON = "webset was cancelled before this field was attempted"
_FAILED_FIELD_REASON = "webset failed before this field was attempted"
_UNSETTLED_FIELD_REASON = "enrichment did not complete before the candidate pass settled"
_UNVERIFIED_REASON = "verification did not complete before the candidate pass settled"


class WebsetNotFoundError(WebsetStoreError):
    """The webset id does not exist — the only error allowed past the runner."""


class WebsetRecallError(RuntimeError):
    """Every recall variant failed; the pass cannot produce candidates (webset-level)."""


class _StoreWorker:
    """Serialize store I/O onto one worker thread (thread-bound sqlite, R5).

    ``WebsetStore`` owns exactly one ``sqlite3`` connection, created in its
    constructor and bound to that thread (``check_same_thread`` default), so the
    runner never touches a store object from the event-loop thread. Every store
    call instead goes to one dedicated worker — the ``asyncio.to_thread``
    mechanism pinned to a single worker — which lazily constructs the runner's
    own ``get_store(db_path)`` and serializes all I/O on it. No in-process lock
    is needed: a single worker makes the single connection safe by construction,
    and the file opens in WAL + ``busy_timeout=5000`` so other processes/thread
    connections can share it.
    """

    def __init__(self, db_path: str | None) -> None:
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webset-store")
        self._store: WebsetStore | None = None

    async def call(self, fn: Callable[[WebsetStore], T]) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._invoke, fn)

    def _invoke(self, fn: Callable[[WebsetStore], T]) -> T:
        if self._store is None:
            self._store = get_store(self._db_path)
        return fn(self._store)

    def close(self) -> None:
        self._executor.shutdown(wait=True)


class Runner(Protocol):
    """Structural seam so a future out-of-process worker can replace the in-process one."""

    async def run_webset_async(self, webset_id: str) -> Webset: ...

    async def backfill_enrichment(
        self, webset_id: str, enrichment_id: str, *, search_id: str | None = None
    ) -> list[WebsetItem]: ...


@dataclass
class _Candidate:
    """One unit of item work: a new recall hit or an existing item needing a pass."""

    key: str
    url: str
    title: str
    item: WebsetItem | None = None


@dataclass
class _PassState:
    """Everything one drive needs, loaded once per webset pass."""

    webset: Webset
    mode: str
    llm_client: Any
    enrichment_defs: list[EnrichmentDef]
    items: dict[str, WebsetItem] = field(default_factory=dict)
    by_url: dict[str, WebsetItem] = field(default_factory=dict)
    driven: list[WebsetSearch] = field(default_factory=list)

    @property
    def webset_id(self) -> str:
        return self.webset.id


#: ``webset_id -> task`` registry owned by the server lifespan (spec § Async lifecycle).
WEBSET_TASKS: dict[str, asyncio.Task[Webset]] = {}


class AsyncioRunner:
    """In-process runner: drives one webset per call, semaphore-bounded."""

    def __init__(
        self,
        *,
        store: WebsetStore | None = None,
        db_path: str | None = None,
        verification_mode: str = "llm",
        llm_client: Any = None,
        concurrency: int = SEMAPHORE_SIZE,
    ) -> None:
        _check_mode(verification_mode)
        self._mode = verification_mode
        self._llm_client = llm_client
        # A caller-supplied store is used only as the DB-path source: its
        # connection belongs to the caller's thread, so the runner binds the
        # same file to its own worker thread instead of crossing threads.
        self._store = _StoreWorker(db_path if store is None else store.db_path)
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def __aenter__(self) -> AsyncioRunner:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Shut the store worker down; no store call may follow."""
        self._store.close()

    async def run_webset_async(self, webset_id: str) -> Webset:
        """``Runner`` protocol entry point (same body as :meth:`run`)."""
        return await self.run(webset_id)

    async def run(self, webset_id: str) -> Webset:
        """Drive one webset through its running searches to terminal status.

        Raises :class:`WebsetNotFoundError` for an unknown id (the one error the
        spec allows past); any other failure is contained into the
        ``webset.failed`` path.
        """
        _check_mode(self._mode)
        state = await self._load_state(webset_id)
        if state.webset.status == "cancelled":
            return state.webset
        try:
            await self._drive(state)
            return await self._finalize(state)
        except Exception as exc:  # per-pass containment -> webset.failed
            return await self._fail(state, exc)

    async def list_incomplete_websets(self) -> list[Webset]:
        """The startup-resume union selector (store-owned query)."""
        return await self._store.call(lambda store: store.list_incomplete_websets())

    async def backfill_enrichment(
        self, webset_id: str, enrichment_id: str, *, search_id: str | None = None
    ) -> list[WebsetItem]:
        """Backfill one attached enrichment onto verified items (``add_enrichment`` path).

        Opens a fresh ``WebsetSearch`` generation (the re-settling-flow rule,
        § Async lifecycle) unless the caller passes an explicit ``search_id``,
        reusing the latest search's query/count/criteria; each settled item
        emits ``item.enriched`` under that generation when the terminal-state
        conditions hold, and the generation settles ``idle`` with a
        ``webset.idle`` event. Verified items already carrying the field are
        skipped.
        """
        state = await self._load_state(webset_id)
        definition = next((d for d in state.enrichment_defs if d.id == enrichment_id), None)
        if definition is None:
            raise WebsetStoreError(
                f"enrichment not found: {enrichment_id}", code="enrichment_not_found"
            )
        if state.webset.status == "cancelled":
            return []
        pending = [
            item
            for item in state.items.values()
            if item.verification == "verified" and definition.name not in item.enrichments
        ]
        if not pending:
            await self._settle_enrichment_defs(state, "idle")
            return []
        generation = await self._open_generation(state, search_id)
        settled: list[WebsetItem] = []
        for candidate in pending:
            if await self._is_cancelled(state):
                break
            markdown, fetch_error = await self._fetch(candidate.url)
            async with self._semaphore:
                if fetch_error is not None:
                    field = EnrichedField(
                        value=None,
                        citations=[],
                        status="unresolved",
                        error=f"candidate fetch failed: {fetch_error}",
                    )
                else:
                    field = await self._extract(state, candidate, definition, markdown)
                candidate.enrichments[definition.name] = field
                candidate = await self._store.call(lambda store: store.save_item(candidate))
                state.items[candidate.id] = candidate
                settled.append(candidate)
                if generation is not None and _item_enriched(candidate, state.enrichment_defs):
                    await self._store.call(
                        lambda store: events.emit_item_enriched(store, candidate, generation)
                    )
        remaining = [
            item
            for item in state.items.values()
            if item.verification == "verified" and definition.name not in item.enrichments
        ]
        def_status: EnrichmentStatus = "idle" if not remaining else "failed"
        await self._store.call(
            lambda store: store.update_enrichment(
                state.webset_id, definition.model_copy(update={"status": def_status})
            )
        )
        if generation is not None:
            await self._close_generation(state, generation)
        return settled

    # -- pass orchestration -------------------------------------------------

    async def _load_state(self, webset_id: str) -> _PassState:
        try:
            webset = await self._store.call(lambda store: store.get_webset(webset_id))
        except WebsetStoreError as exc:
            if exc.code == "webset_not_found":
                raise WebsetNotFoundError(str(exc), code=exc.code) from exc
            raise
        items = await self._store.call(lambda store: _all_items(store, webset_id))
        state = _PassState(
            webset=webset,
            mode=self._mode,
            llm_client=self._llm_client,
            enrichment_defs=list(webset.enrichments),
        )
        for item in items:
            state.items[item.id] = item
            key = _url_key(item.url)
            if key:
                state.by_url.setdefault(key, item)
        return state

    async def _drive(self, state: _PassState) -> None:
        for search in state.webset.searches:
            if search.status != "running":
                continue
            if await self._is_cancelled(state):
                return
            state.driven.append(search)
            await self._drive_search(state, search)

    async def _drive_search(self, state: _PassState, search: WebsetSearch) -> None:
        work: dict[str, _Candidate] = {}
        self._queue_stored_work(state, work)
        processed: set[str] = set()
        recall_error: Exception | None = None
        recalled = False
        for index, variant in enumerate(_query_variants(search.query)):
            if await self._is_cancelled(state):
                return
            if index and await self._verified_count(state) >= search.count:
                break
            try:
                response = await asyncio.to_thread(
                    search_web,
                    WebSearchRequest(
                        query=variant,
                        max_results=min(RECALL_PAGE_SIZE, search.count),
                    ),
                )
            except Exception as exc:
                recall_error = exc
                continue
            recalled = True
            for hit in response.results:
                key = _url_key(hit.url)
                if not key or key in work:
                    continue
                item = state.by_url.get(key)
                if item is not None and not self._needs_work(state, item):
                    continue
                work[key] = _Candidate(key=key, url=hit.url, title=hit.title, item=item)
            batch = [candidate for key, candidate in work.items() if key not in processed]
            processed.update(candidate.key for candidate in batch)
            if batch:
                await self._run_batch(state, search, batch)
        if not recalled:
            raise WebsetRecallError(
                f"all recall variants failed for search {search.id}: {recall_error}"
            )
        if await self._is_cancelled(state):
            return
        await self._settle_pending_items(state, search)
        await self._settle_missing_fields(state, "unresolved", _UNSETTLED_FIELD_REASON)
        # A cancel may race in between the flag check above and this settle
        # (cancel_webset already settled the search `cancelled`); re-read the row
        # so the settle is a no-op instead of an illegal cancelled -> idle move.
        current = await self._store.call(lambda store: store.get_search(state.webset_id, search.id))
        if current.status == "running":
            await self._store.call(
                lambda store: store.settle_search(state.webset_id, search.id, "idle")
            )

    def _queue_stored_work(self, state: _PassState, work: dict[str, _Candidate]) -> None:
        """Re-drive stored items needing work even when recall does not return them."""
        for item in state.items.values():
            key = _url_key(item.url)
            if not key or key in work or not self._needs_work(state, item):
                continue
            work[key] = _Candidate(key=key, url=item.url, title=item.title, item=item)

    def _needs_work(self, state: _PassState, item: WebsetItem) -> bool:
        if item.verification == "pending":
            return True
        return item.verification == "verified" and bool(self._missing_fields(state, item))

    @staticmethod
    def _missing_fields(state: _PassState, item: WebsetItem) -> list[EnrichmentDef]:
        return [d for d in state.enrichment_defs if d.name not in item.enrichments]

    async def _run_batch(
        self, state: _PassState, search: WebsetSearch, batch: Sequence[_Candidate]
    ) -> None:
        async with asyncio.TaskGroup() as group:
            for candidate in batch:
                group.create_task(self._process_candidate(state, search, candidate))

    async def _process_candidate(
        self, state: _PassState, search: WebsetSearch, candidate: _Candidate
    ) -> None:
        try:
            async with self._semaphore:
                if await self._is_cancelled(state):
                    return
                item = candidate.item
                if item is None:
                    item = await self._store.call(
                        lambda store: store.save_item(
                            WebsetItem(
                                webset_id=state.webset_id,
                                url=candidate.url,
                                title=candidate.title,
                            )
                        )
                    )
                    state.items[item.id] = item
                    state.by_url[candidate.key] = item
                if item.verification == "rejected":
                    return
                markdown, fetch_error = await self._fetch(candidate.url)
                if item.verification == "pending":
                    item = await self._verify(state, search, item, markdown, fetch_error)
            if item.verification == "verified":
                await self._enrich(state, search, item, markdown)
        except Exception:
            logger.exception("webset %s: item %s failed", state.webset_id, candidate.url)

    async def _verify(
        self,
        state: _PassState,
        search: WebsetSearch,
        item: WebsetItem,
        markdown: str,
        fetch_error: str | None,
    ) -> WebsetItem:
        # T3 carry: an unknown mode must surface before the settlement try, never
        # be swallowed into a `rejected` settlement by settle_pending_item's
        # ValueError arm. Settle only `pending` items (re-settle guard): a
        # `verified` item never repeats its billable verification call.
        _check_mode(state.mode)
        if fetch_error is not None:
            item.verification = "rejected"
            item.criteria_results = settlement_results(
                search.criteria, f"candidate fetch failed: {fetch_error}"
            )
        else:
            item = await asyncio.to_thread(
                settle_pending_item,
                item,
                markdown,
                search.criteria,
                mode=state.mode,
                llm_client=state.llm_client,
            )
        item = await self._store.call(lambda store: store.save_item(item))
        state.items[item.id] = item
        if item.verification == "verified":
            await self._store.call(lambda store: events.emit_item_created(store, item, search.id))
        return item

    async def _enrich(
        self, state: _PassState, search: WebsetSearch, item: WebsetItem, markdown: str
    ) -> None:
        for definition in self._missing_fields(state, item):
            if await self._is_cancelled(state):
                return
            async with self._semaphore:
                if await self._is_cancelled(state):
                    return
                field = await self._extract(state, item, definition, markdown)
                item.enrichments[definition.name] = field
                item = await self._store.call(lambda store: store.save_item(item))
                state.items[item.id] = item
        if _item_enriched(item, state.enrichment_defs):
            await self._store.call(lambda store: events.emit_item_enriched(store, item, search.id))

    async def _extract(
        self, state: _PassState, item: WebsetItem, definition: EnrichmentDef, markdown: str
    ) -> EnrichedField:
        # T2 review note: an enrichment failure always settles a terminal field
        # (unresolved) so a never-settled field cannot make `idle` unreachable.
        try:
            return await asyncio.to_thread(
                enrich_item,
                item.url,
                item.title,
                markdown,
                definition,
                llm_client=state.llm_client,
            )
        except Exception as exc:
            return EnrichedField(
                value=None,
                citations=[],
                status="unresolved",
                error=f"enrichment failed: {type(exc).__name__}: {exc}",
            )

    async def _fetch(self, url: str) -> tuple[str, str | None]:
        try:
            markdown = await asyncio.to_thread(fetch_markdown, url)
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"
        return markdown or "", None

    async def _settle_pending_items(self, state: _PassState, search: WebsetSearch) -> None:
        """Fail-closed candidate-pass-end settlement: pending items become ``rejected``."""
        for item in list(state.items.values()):
            if item.verification != "pending":
                continue
            item.verification = "rejected"
            item.criteria_results = settlement_results(search.criteria, _UNVERIFIED_REASON)
            item = await self._store.call(lambda store: store.save_item(item))
            state.items[item.id] = item

    async def _settle_missing_fields(
        self, state: _PassState, status: EnrichedStatus, reason: str
    ) -> None:
        """Write a terminal field for every verified item still missing one."""
        for item in list(state.items.values()):
            if item.verification != "verified":
                continue
            missing = self._missing_fields(state, item)
            if not missing:
                continue
            for definition in missing:
                item.enrichments[definition.name] = EnrichedField(
                    value=None, citations=[], status=status, error=reason
                )
            item = await self._store.call(lambda store: store.save_item(item))
            state.items[item.id] = item

    async def _settle_enrichment_defs(self, state: _PassState, status: EnrichmentStatus) -> None:
        definitions = await self._store.call(lambda store: store.list_enrichments(state.webset_id))
        for definition in definitions:
            if definition.status == status:
                continue
            await self._store.call(
                lambda store: store.update_enrichment(
                    state.webset_id, definition.model_copy(update={"status": status})
                )
            )

    async def _finalize(self, state: _PassState) -> Webset:
        webset = await self._store.call(lambda store: store.get_webset(state.webset_id))
        if webset.status == "cancelled":
            await self._settle_missing_fields(state, "skipped", _CANCELLED_FIELD_REASON)
            return webset
        if webset.status not in ("running", "idle"):
            return webset
        await self._settle_enrichment_defs(state, "idle")
        if webset.status == "idle":
            # A sticky-idle webset's flip short-circuits the store's settlement
            # blockers (idle is sticky), so a mid-pass `add_search` newcomer would
            # otherwise stay undriven; the running-webset case is caught by the
            # `webset_not_settled` retry below.
            await self._drive_newcomers(state)
        settled = False
        for _ in range(_FINALIZE_ATTEMPTS):
            try:
                webset = await self._store.call(
                    lambda store: store.set_webset_idle(state.webset_id)
                )
                settled = True
                break
            except WebsetStoreError as exc:
                if exc.code == "transition_invalid":  # cancelled between read and write
                    await self._settle_missing_fields(state, "skipped", _CANCELLED_FIELD_REASON)
                    return await self._store.call(lambda store: store.get_webset(state.webset_id))
                if exc.code != "webset_not_settled":
                    return await self._fail(state, exc)
                current = await self._store.call(lambda store: store.get_webset(state.webset_id))
                if current.status == "cancelled":
                    await self._settle_missing_fields(state, "skipped", _CANCELLED_FIELD_REASON)
                    return current
                # A search added mid-pass (``add_search`` on a running/idle webset is
                # allowed; the duplicate-schedule guard means it has no task of its
                # own) refuses the idle flip until it is driven: drive it, retry.
                if not await self._drive_newcomers(state):
                    # A cancel may land between the cancelled re-check above and
                    # ``_drive_newcomers``'s own read, which reports the cancelled
                    # webset as "nothing to drive": re-check so the cancelled path
                    # wins instead of emitting ``webset.failed`` on a cancelled webset.
                    current = await self._store.call(
                        lambda store: store.get_webset(state.webset_id)
                    )
                    if current.status == "cancelled":
                        await self._settle_missing_fields(state, "skipped", _CANCELLED_FIELD_REASON)
                        return current
                    return await self._fail(state, exc)
                await self._settle_enrichment_defs(state, "idle")
        if not settled:
            return await self._fail(
                state, WebsetStoreError("webset still not settled", code="webset_not_settled")
            )
        # Terminal events carry the generation that settled the pass. Emitting for
        # every idle search — not only this pass's drives — recovers an idle event
        # lost to a crash between the search settle and the webset flip/emit; the
        # store's INSERT-or-ignore dedup keeps the re-emission idempotent.
        current = await self._store.call(lambda store: store.get_webset(state.webset_id))
        for search in current.searches:
            if search.status == "idle":
                await self._store.call(
                    lambda store: events.emit_webset_idle(store, state.webset_id, search.id)
                )
        return webset

    async def _drive_newcomers(self, state: _PassState) -> bool:
        """Drive running searches that arrived after this pass loaded (``add_search`` race).

        Returns ``True`` when at least one such generation was driven (the caller
        retries the idle flip), ``False`` when there is nothing new to drive or the
        webset was cancelled meanwhile.
        """
        webset = await self._store.call(lambda store: store.get_webset(state.webset_id))
        if webset.status == "cancelled":
            return False
        driven_ids = {search.id for search in state.driven}
        newcomers = [
            search
            for search in webset.searches
            if search.status == "running" and search.id not in driven_ids
        ]
        for search in newcomers:
            state.driven.append(search)
            await self._drive_search(state, search)
        return bool(newcomers)

    async def _fail(self, state: _PassState, exc: Exception) -> Webset:
        """Best-effort webset-level failure settlement (spec § Async lifecycle)."""
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning("webset %s failed: %s", state.webset_id, reason)
        webset: Webset | None = None
        try:
            webset = await self._store.call(lambda store: store.get_webset(state.webset_id))
            reference = next((s for s in webset.searches if s.status == "running"), None)
            failed_generations: list[str] = []
            for search in webset.searches:
                if search.status != "running":
                    continue
                await self._store.call(
                    lambda store: store.settle_search(state.webset_id, search.id, "failed")
                )
                failed_generations.append(search.id)
            if not failed_generations and webset.searches:
                # No search was running (crash between a failed settle and its
                # event): the latest generation carries the terminal event.
                failed_generations.append(webset.searches[-1].id)
            for generation in failed_generations:
                await self._store.call(
                    lambda store: events.emit_webset_failed(
                        store, state.webset_id, generation, reason
                    )
                )
            if reference is None and webset.searches:
                reference = webset.searches[-1]
            if reference is not None:
                await self._settle_pending_items(state, reference)
            await self._settle_missing_fields(state, "skipped", _FAILED_FIELD_REASON)
            await self._settle_enrichment_defs(state, "failed")
            if webset.status == "running":
                webset = await self._store.call(
                    lambda store: store.set_webset_status(state.webset_id, "failed")
                )
            else:
                webset = await self._store.call(lambda store: store.get_webset(state.webset_id))
        except Exception:
            logger.exception("webset %s: failure settlement did not complete", state.webset_id)
        return state.webset if webset is None else webset

    # -- generations --------------------------------------------------------

    async def _open_generation(self, state: _PassState, search_id: str | None) -> str | None:
        """A re-settling flow runs as a new ``WebsetSearch`` generation (§ Async lifecycle)."""
        if search_id is not None:
            await self._store.call(lambda store: store.get_search(state.webset_id, search_id))
            return search_id
        if not state.webset.searches:
            return None
        latest = state.webset.searches[-1]
        created = await self._store.call(
            lambda store: store.add_search(
                WebsetSearch(
                    webset_id=state.webset_id,
                    query=latest.query,
                    count=latest.count,
                    criteria=latest.criteria,
                )
            )
        )
        return created.id

    async def _close_generation(self, state: _PassState, generation: str) -> None:
        search = await self._store.call(lambda store: store.get_search(state.webset_id, generation))
        if search.status != "running":
            return
        await self._store.call(
            lambda store: store.settle_search(state.webset_id, generation, "idle")
        )
        try:
            await self._store.call(lambda store: store.set_webset_idle(state.webset_id))
        except WebsetStoreError:
            logger.warning("webset %s: idle not reachable after backfill", state.webset_id)
            return
        await self._store.call(
            lambda store: events.emit_webset_idle(store, state.webset_id, generation)
        )

    # -- store reads --------------------------------------------------------

    async def _is_cancelled(self, state: _PassState) -> bool:
        webset = await self._store.call(lambda store: store.get_webset(state.webset_id))
        return webset.status == "cancelled"

    async def _verified_count(self, state: _PassState) -> int:
        counts = await self._store.call(lambda store: store.count_items(state.webset_id))
        return counts["verified"]


# -- module-level entry points (spec § Interfaces) ----------------------------


async def run_webset_async(
    webset_id: str,
    *,
    store: WebsetStore | None = None,
    verification_mode: str = "llm",
    llm_client: Any = None,
    concurrency: int = SEMAPHORE_SIZE,
) -> Webset:
    """Drive one webset to ``idle``: candidates -> verify -> enrich -> events.

    Never raises past :class:`WebsetNotFoundError`; per-item failures mark
    items, a webset-level failure emits ``webset.failed``. ``verification_mode``
    defaults to the spec's ``llm`` (the service/HTTP layer defaults it too) and
    is threaded, never re-derived; ``llm_client`` is the pinned T3/T4 mock seam.
    """
    async with AsyncioRunner(
        store=store,
        verification_mode=verification_mode,
        llm_client=llm_client,
        concurrency=concurrency,
    ) as runner:
        return await runner.run(webset_id)


async def resume_incomplete_websets(
    *,
    store: WebsetStore | None = None,
    verification_mode: str = "llm",
    llm_client: Any = None,
) -> list[str]:
    """Re-drive the startup-resume union; returns the driven webset ids.

    § Async lifecycle: the selection is the UNION of every webset still
    ``running`` (a first pass that never completed — including the window where
    all searches settled but items/fields remain ``pending``) and every webset
    holding a non-terminal ``running`` search (a crashed refresh on a
    sticky-``idle`` webset). The runner is idempotent: ``verified`` items and
    terminal enrichment fields are skipped, ``pending`` items/fields are
    re-driven, and already-appended events are never duplicated within a
    generation (the store's INSERT-or-ignore dedup key).
    """
    async with AsyncioRunner(
        store=store, verification_mode=verification_mode, llm_client=llm_client
    ) as runner:
        driven: list[str] = []
        for webset in await runner.list_incomplete_websets():
            try:
                await runner.run(webset.id)
            except WebsetNotFoundError:
                continue
            driven.append(webset.id)
        return driven


async def backfill_enrichment(
    webset_id: str,
    enrichment_id: str,
    *,
    store: WebsetStore | None = None,
    llm_client: Any = None,
    search_id: str | None = None,
) -> list[WebsetItem]:
    """Backfill one enrichment onto verified items (the ``add_enrichment`` path)."""
    async with AsyncioRunner(store=store, llm_client=llm_client) as runner:
        return await runner.backfill_enrichment(webset_id, enrichment_id, search_id=search_id)


def schedule_webset_task(
    task_group: asyncio.TaskGroup,
    webset_id: str,
    *,
    store: WebsetStore | None = None,
    verification_mode: str = "llm",
    llm_client: Any = None,
    concurrency: int = SEMAPHORE_SIZE,
) -> asyncio.Task[Webset]:
    """Create a registry-tracked run task inside the lifespan ``TaskGroup``.

    Every task carries a ``WEBSET_TASKS`` entry, a done-callback logging
    ``(webset_id, ok|error)`` and removal on completion (spec § Async
    lifecycle). Scheduling a webset whose task is still running returns the
    existing task instead of double-driving it — a duplicated pass would repeat
    billable verification/enrichment calls.
    """
    running = WEBSET_TASKS.get(webset_id)
    if running is not None and not running.done():
        return running
    task = task_group.create_task(
        run_webset_async(
            webset_id,
            store=store,
            verification_mode=verification_mode,
            llm_client=llm_client,
            concurrency=concurrency,
        )
    )
    WEBSET_TASKS[webset_id] = task
    task.add_done_callback(functools.partial(_log_task_done, webset_id))
    return task


def _log_task_done(webset_id: str, task: asyncio.Task[Webset]) -> None:
    """Log ``(webset_id, ok|error)`` and drop only this task's registry entry.

    A reschedule may have replaced the entry after this task finished but before
    this callback ran; popping unconditionally would evict the newer task and
    re-open the double-drive window the schedule guard closes.
    """
    if WEBSET_TASKS.get(webset_id) is task:
        WEBSET_TASKS.pop(webset_id, None)
    if task.cancelled():
        logger.info("webset task done (%s, cancelled)", webset_id)
        return
    error = task.exception()
    if error is None:
        logger.info("webset task done (%s, ok)", webset_id)
    else:
        logger.error("webset task done (%s, error: %s)", webset_id, error)


# -- helpers ------------------------------------------------------------------


def _check_mode(mode: str) -> None:
    """Reject an unknown verification mode before any settlement can swallow it."""
    if mode not in _VERIFICATION_MODES:
        expected = ", ".join(_VERIFICATION_MODES)
        raise ValueError(f"unknown verification mode {mode!r}; expected one of {expected}")


def _query_variants(query: str) -> list[str]:
    """Base query plus bounded suffix variants (no paging exists — R3)."""
    base = " ".join(query.split())[:500]
    variants = [base]
    for suffix in _QUERY_VARIANT_SUFFIXES:
        variants.append(f"{base} {suffix}"[:500])
    return variants


def _url_key(url: str) -> str:
    """Citation-identity key for candidate/item dedupe (shared ``normalize_url``)."""
    text = url.strip()
    if not text:
        return ""
    try:
        return normalize_url(text)
    except ValueError:
        return text.lower()


def _all_items(store: WebsetStore, webset_id: str) -> list[WebsetItem]:
    """Every stored item, paging through the store's bounded item cursor."""
    items, cursor = store.list_items(webset_id, limit=200)
    while cursor is not None:
        page, cursor = store.list_items(webset_id, limit=200, cursor=cursor)
        items.extend(page)
    return items


def _item_enriched(item: WebsetItem, definitions: Sequence[EnrichmentDef]) -> bool:
    """§ Architecture: all requested fields terminal AND at least one resolved."""
    if not definitions:
        return False
    fields = [item.enrichments.get(definition.name) for definition in definitions]
    if any(field is None for field in fields):
        return False
    return any(field is not None and field.status == "resolved" for field in fields)
