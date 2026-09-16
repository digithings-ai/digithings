# score:allow untyped any
# recall payloads and query snapshots are dynamic JSON; Any is the honest annotation.
"""Phase C watch runner — shallow recall → dedup → persist → deliver (#4065, Task 4).

One watch turn (``run_watch``) runs the Phase B shallow recall path directly
in-process (R2 — no loopback HTTP, no bearer token): ``web_exa.exa_search`` when
``is_exa_configured()``, else the OSS seam ``web_search/service.py::search_web``
with ``recency_days=None`` (R5 — monitors must not inherit the landed 7-day
default as a silent rolling window) and ``max_results=min(num_results, 10)``
clamped to the landed OSS bound (R6). The OSS leg returns ``WebSearchResponse``,
so the seam adapts it to the canonical recall payload via
``_oss_response_to_data`` (R3) and both legs hand the runner a ``WebSearchData``.

The turn then dedups against :meth:`MonitorStore.seen_fingerprints` (the store
recomputes fingerprints with the public ``result_fingerprint`` — never ad-hoc
field picking), persists the ``MonitorRun`` (append-only), and fans delivery out
only when ``status == ok`` and the watch's delivery mode is not ``poll`` (R13),
threading the watch's stored secret into :func:`deliver` for the
``X-digi-signature`` HMAC. ``no_change`` and ``failed`` runs never deliver.

The C→D bridge (#4249) runs after persist like delivery: an ``ok`` run on a
watch carrying ``bridge`` opens one search generation on the target webset via
:func:`handoff` — an in-process call into the websets service (R2: no loopback
HTTP, no bearer token), never on ``no_change``/``failed`` runs. The websets
store's ``(watch_id, run_id, webset_id)`` ledger makes repeat deliveries of one
run idempotent, and this turn is the single retry owner: a bridge failure is
recorded as a ``BridgeReceipt(ok=False)`` on the returned run — it never flips
the run's status — so the next ``ok`` run re-attempts the handoff.

Research mode (#4250) swaps the turn: ``answer_mode="research"`` runs the full
Phase B research turn for the watch query (the optional ``digisearch[agent]``
layer, lazily imported) and stores a cited ``MonitorDigest`` on the run. The
turn's hits still flow through the SAME ``dedup_results`` pass (URL identity via
``normalize_url``), but status semantics diverge by design: ``ok`` means a
digest was produced — URL novelty for research runs lives only in
``results_new``/``dedup_stats``, so a fresh digest delivers/bridges even when no
URL is new. Recall mode is byte-identical to v1.

Fail-hard semantics: any recall exception persists a ``status="failed"`` run
with ``error=str(exc)`` and re-raises ``MonitorRunError`` carrying the persisted
``run_id``. A delivery-enabled run whose stored secret is ``None`` (see
:meth:`MonitorStore.get_delivery_secret`) fails just as loudly — the run is
persisted ``failed`` with ``delivery_secret_missing`` (and ``results_all=[]`` so
the dedup memory cannot absorb undelivered content) and ``MonitorRunError`` is
raised — never a silent skip.

``tick_due_watches`` is the scheduler-facing entry point: it evaluates every
enabled watch (cron or interval) with ``is_due`` and runs the due ones with
``trigger="schedule"``, isolating per-watch failures so one broken watch never
aborts the tick. Datatap-scoped watches are skipped outright — DataTap stays
OFF end-to-end (§5).

``is_due`` owns all timezone conversion: ``now`` (assumed UTC when naive) and
``last_run_at`` are normalized to the watch's ``schedule.timezone``. Cron mode
imports the grammar from :mod:`digiclaw.cron` (``parse_cron`` +
``CronExpression.matches``) — never a copy — and suppresses a second run inside
the same matching minute; interval mode fires when ``last_run_at + interval <=
now``, with a missing ``last_run_at`` meaning due.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from digiclaw.cron import parse_cron

from digisearch.monitors.dedup import dedup_results
from digisearch.monitors.models import (
    BridgeReceipt,
    DeliveryReceipt,
    MonitorDigest,
    MonitorRun,
    Watch,
)
from digisearch.monitors.store import MonitorStore, get_store, new_ulid
from digisearch.monitors.validation import DATATAP_WORKSPACE_ID
from digisearch.web_exa import ExaSearchType, WebSearchData, exa_search, is_exa_configured
from digisearch.web_search.citation import Citation, normalize_url
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse
from digisearch.web_search.service import search_web

__all__ = [
    "MonitorRunError",
    "deliver",
    "handoff",
    "is_due",
    "run_watch",
    "tick_due_watches",
]

logger = logging.getLogger(__name__)

_RunStatus = Literal["ok", "no_change", "failed"]
_Trigger = Literal["schedule", "manual", "poll"]

# Landed WebSearchRequest.max_results bound (R6): the OSS seam clamps to it.
_OSS_MAX_RESULTS = 10

# Stable error code recorded on a delivery-enabled run with no stored secret.
_DELIVERY_SECRET_MISSING = "delivery_secret_missing"


class MonitorRunError(RuntimeError):
    """A watch turn failed and its failure was persisted.

    ``run_id`` identifies the stored ``MonitorRun`` (``status="failed"``,
    ``error`` set); callers may load it with
    :meth:`MonitorStore.get_run` instead of re-deriving the failure.
    """

    def __init__(self, message: str, *, run_id: str) -> None:
        super().__init__(message)
        self.run_id = run_id


def run_watch(
    watch_id: str,
    *,
    trigger: _Trigger = "manual",
    store: MonitorStore | None = None,
) -> MonitorRun:
    """Execute one watch turn and persist it (see the module docstring for flow).

    A missing watch raises :class:`MonitorStoreError` from the store. Any recall
    failure persists ``status="failed"`` and raises :class:`MonitorRunError`.
    A delivery-enabled run with no stored secret persists ``status="failed"``
    (``error="delivery_secret_missing"``, ``results_all=[]`` so the dedup memory
    does not absorb undelivered content, ``results_new`` kept as the factual
    record) and raises :class:`MonitorRunError`. Delivery and bridge receipts
    are attached to the returned run; the append-only store cannot rewrite the
    already-persisted body, so stored runs keep ``delivery=[]`` and
    ``bridge=None``.
    """
    store = store if store is not None else get_store()
    watch = store.get_watch(watch_id)
    started_at = datetime.now(UTC)
    exa_configured = is_exa_configured()
    query_snapshot = _query_snapshot(watch, exa_configured=exa_configured)

    digest: MonitorDigest | None = None
    try:
        if watch.answer_mode == "research":
            digest, data = _invoke_research_digest(watch, watch_id=watch_id)
        else:
            data = _invoke_shallow_recall(
                query=watch.query,
                search_type=watch.search_type,
                num_results=watch.num_results,
                category=watch.category,
                include_domains=watch.include_domains,
                exclude_domains=watch.exclude_domains,
            )
    except Exception as exc:
        run = MonitorRun(
            run_id=new_ulid(),
            watch_id=watch_id,
            backend=watch.backend,
            status="failed",
            trigger=trigger,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            query_snapshot=query_snapshot,
            results_all=[],
            results_new=[],
            dedup_stats={},
            error=str(exc),
        )
        store.append_run(run)
        logger.warning(
            "monitor run failed watch_id=%s run_id=%s error=%s", watch_id, run.run_id, exc
        )
        raise MonitorRunError(str(exc), run_id=run.run_id) from exc

    results_all = [dict(result) for result in data.results]
    results_new, dedup_stats = dedup_results(
        results_all, store.seen_fingerprints(watch_id), watch.dedup
    )
    if watch.answer_mode == "research":
        # Divergence by design (#4250): a produced digest is the ok signal;
        # URL novelty lives only in results_new/dedup_stats.
        status: _RunStatus = "ok" if digest is not None and digest.answer else "no_change"
    else:
        status = "ok" if results_new else "no_change"

    error: str | None = None
    deliver_after_persist = status == "ok" and watch.delivery.mode != "poll"
    delivery_secret: str | None = None
    if deliver_after_persist:
        delivery_secret = store.get_delivery_secret(watch_id)
        if delivery_secret is None:
            status = "failed"
            error = _DELIVERY_SECRET_MISSING
            deliver_after_persist = False
            # The store's seen memory merges results_all regardless of status, so
            # persisting the found results would dedup them to unchanged once a
            # secret exists — the content would never be delivered. Keep
            # results_new as the factual record and leave the memory untouched:
            # the next run re-detects the content and fails loudly again.
            results_all = []

    run = MonitorRun(
        run_id=new_ulid(),
        watch_id=watch_id,
        backend=watch.backend,
        status=status,
        trigger=trigger,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        query_snapshot=query_snapshot,
        results_all=results_all,
        results_new=results_new,
        dedup_stats=dedup_stats,
        cost_dollars=data.cost_dollars,
        digest=digest,
        error=error,
    )
    store.append_run(run)

    if status == "failed":
        logger.warning(
            "monitor run failed watch_id=%s run_id=%s error=%s", watch_id, run.run_id, error
        )
        raise MonitorRunError(error or "monitor run failed", run_id=run.run_id)

    if deliver_after_persist:
        assert delivery_secret is not None
        # Create-time check leaves a DNS-rebinding window; verified TLS + no redirects mitigate.
        receipts = deliver(run, watch, delivery_secret=delivery_secret)
        run = run.model_copy(update={"delivery": receipts})

    bridge = handoff(run, watch) if run.status == "ok" else None
    if bridge is not None:
        run = run.model_copy(update={"bridge": bridge})

    logger.info(
        "monitor run watch_id=%s run_id=%s status=%s new=%d all=%d",
        watch_id,
        run.run_id,
        run.status,
        len(run.results_new),
        len(run.results_all),
    )
    return run


def tick_due_watches(
    *,
    now: datetime | None = None,
    store: MonitorStore | None = None,
) -> list[MonitorRun]:
    """Run every due + enabled watch once; return one run per attempted watch.

    Per-watch failures are isolated: a recall failure contributes its persisted
    failed run to the result, and an unexpected error is logged without aborting
    the tick. Datatap-scoped watches are skipped (§5).
    """
    store = store if store is not None else get_store()
    current = _ensure_aware(now) if now is not None else datetime.now(UTC)
    runs: list[MonitorRun] = []
    for watch in store.list_watches():
        # §5: DataTap stays OFF end-to-end — the tick never runs a datatap watch.
        if not watch.schedule.enabled or watch.workspace_id == DATATAP_WORKSPACE_ID:
            continue
        try:
            if not is_due(watch, current, _last_run_at(store, watch.watch_id)):
                continue
            runs.append(run_watch(watch.watch_id, trigger="schedule", store=store))
        except MonitorRunError as exc:
            runs.append(store.get_run(watch.watch_id, exc.run_id))
        except Exception:
            logger.exception("monitor tick failed watch_id=%s", watch.watch_id)
    return runs


def is_due(watch: Watch, now: datetime, last_run_at: datetime | None) -> bool:
    """Return whether *watch* is due at *now*.

    ``now`` (naive means UTC) and ``last_run_at`` are converted to the watch's
    ``schedule.timezone`` here — callers pass UTC. Interval mode is due when
    ``last_run_at + interval_seconds <= now`` (a missing ``last_run_at`` means
    due). Cron mode is due when the local wall clock matches the imported
    ``digiclaw.cron`` grammar, except when the previous run started inside the
    same matching minute (one fire per cron minute).
    """
    schedule = watch.schedule
    zone = ZoneInfo(schedule.timezone)
    current = _ensure_aware(now).astimezone(zone)

    if schedule.mode == "interval":
        if last_run_at is None:
            return True
        assert schedule.interval_seconds is not None
        previous = _ensure_aware(last_run_at).astimezone(zone)
        return previous + timedelta(seconds=schedule.interval_seconds) <= current

    assert schedule.cron is not None
    if last_run_at is not None:
        previous = _ensure_aware(last_run_at).astimezone(zone)
        if previous.replace(second=0, microsecond=0) == current.replace(second=0, microsecond=0):
            return False
    # digiclaw's matches() re-tags a naive datetime as UTC without shifting its
    # fields, so the local wall clock goes in naive: the astimezone() above did
    # the shifting, and the imported grammar then sees the watch's local fields.
    return parse_cron(schedule.cron).matches(current.replace(tzinfo=None))


def deliver(
    run: MonitorRun,
    watch: Watch,
    *,
    delivery_secret: str,
    timeout_s: float = 10.0,
) -> list[DeliveryReceipt]:
    """Delivery seam — delegates to ``monitors/delivery.py`` (Task 5).

    Imported lazily so the runner stays importable before Task 5 lands and so
    tests can patch this attribute. ``delivery_secret`` is REQUIRED and must be
    the watch's stored secret: a delivery-enabled watch whose stored secret is
    ``None`` must fail loudly (recorded failed run), never silently skip
    delivery — :func:`run_watch` enforces that constraint before calling here.
    """
    from digisearch.monitors.delivery import deliver as _deliver

    return _deliver(run, watch, delivery_secret=delivery_secret, timeout_s=timeout_s)


def handoff(run: MonitorRun, watch: Watch) -> BridgeReceipt | None:
    """Bridge seam — hand an ``ok`` run to its webset (C→D contract, #4249).

    Returns ``None`` when the watch carries no ``bridge``. The actual call goes
    through :func:`_invoke_handoff` (lazily imported, patchable in tests); any
    failure becomes a ``BridgeReceipt(ok=False, error=...)`` — the handoff
    never flips the run's status. Retry ownership stays with the watch turn
    (one attempt here): the next ``ok`` run re-attempts, and the websets store
    ledger makes that re-attempt idempotent per ``(watch_id, run_id,
    webset_id)``.
    """
    bridge = watch.bridge
    if bridge is None:
        return None
    try:
        search, created = _invoke_handoff(
            bridge.webset_id, watch_id=watch.watch_id, run_id=run.run_id
        )
    except Exception as exc:
        logger.warning(
            "monitor bridge handoff failed watch_id=%s run_id=%s webset_id=%s error=%s",
            watch.watch_id,
            run.run_id,
            bridge.webset_id,
            exc,
        )
        return BridgeReceipt(webset_id=bridge.webset_id, ok=False, error=str(exc))
    return BridgeReceipt(
        webset_id=bridge.webset_id, ok=True, search_id=search.id, duplicate=not created
    )


def _invoke_handoff(webset_id: str, *, watch_id: str, run_id: str) -> tuple[Any, bool]:
    """Call the websets service handoff in-process (lazy import seam, #4249)."""
    from digisearch.websets.service import handoff_from_watch

    return handoff_from_watch(webset_id, watch_id=watch_id, run_id=run_id)


def _invoke_shallow_recall(
    *,
    query: str,
    search_type: str,
    num_results: int,
    category: str | None,
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
    offset: int = 0,
) -> WebSearchData:
    """Call the shallow recall leg directly in-process and return ``WebSearchData``.

    EXA when configured; otherwise the OSS seam with ``recency_days=None`` (R5)
    and the R6 clamp, adapted through :func:`_oss_response_to_data` (R3). The
    EXA-only ``search_type``/``category`` knobs are passed only to EXA.

    ``offset`` threads the #4234 paging contract through this third
    ``exa_search`` call site (#4241). Watches carry no paging config, so
    :func:`run_watch` always takes the default ``offset=0`` — the unpaged call,
    byte-identical to before. The OSS leg has no offset (``WebSearchRequest``
    has no such field): a nonzero ``offset`` there raises rather than silently
    serving page 1.
    """
    if is_exa_configured():
        return exa_search(
            query,
            search_type=cast(ExaSearchType, search_type),
            num_results=num_results,
            offset=offset,
            category=category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
    if offset != 0:
        raise ValueError(
            f"offset is EXA-only (got {offset}): the OSS web_search seam has no offset"
        )
    response = search_web(
        WebSearchRequest(
            query=query,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            max_results=_oss_clamped_num_results(num_results),
            recency_days=None,
        )
    )
    return _oss_response_to_data(response)


def _oss_response_to_data(resp: WebSearchResponse) -> WebSearchData:
    """Adapt the OSS leg (``WebSearchResponse``) to the canonical recall payload (R3)."""
    return WebSearchData(results=[result.model_dump() for result in resp.results])


def _invoke_research_digest(watch: Watch, *, watch_id: str) -> tuple[MonitorDigest, WebSearchData]:
    """Run the Phase B research turn in-process and adapt its output (#4250).

    Always the OSS Phase B web branch (``source="web"``): research mode is
    OSS-local-only and rejected on EXA watches at the config gate. The turn is
    the optional ``digisearch[agent]`` layer, so it is imported lazily — a
    missing extra surfaces as the call raising ImportError inside
    :func:`run_watch`'s failure path. A turn-reported ``error`` is raised too:
    a failed turn persists a failed run, never an empty digest.
    """
    from digisearch.agent import run_research_turn

    turn = run_research_turn(
        {
            "user_message": watch.query,
            "source": "web",
            "effort": watch.effort,
            "index_name": "default",
            "session_id": f"watch:{watch_id}",
        }
    )
    if turn.get("error"):
        raise RuntimeError(f"research turn failed: {turn['error']}")
    web_output = dict(turn.get("web_output") or {})
    rows = [row for row in (turn.get("results") or []) if isinstance(row, dict)]
    digest = MonitorDigest(
        answer=str(web_output.get("text") or "").strip(),
        citations=_digest_citations(rows),
        effort=watch.effort,
    )
    return digest, WebSearchData(
        results=[dict(row) for row in rows],
        output=web_output,
        cost_dollars=turn.get("cost_dollars"),
    )


def _digest_citations(rows: list[dict[str, Any]]) -> list[Citation]:
    """Cited hit rows → ``Citation``s, deduped on ``normalize_url`` identity (#4250)."""
    citations: list[Citation] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "")
        if not url:
            continue
        identity = normalize_url(url)
        if identity in seen:
            continue
        seen.add(identity)
        citations.append(
            Citation(
                url=url,
                title=str(row.get("title") or ""),
                excerpt=str(row.get("snippet") or ""),
            )
        )
    return citations


def _oss_clamped_num_results(num_results: int) -> int:
    """Clamp to the landed OSS ``max_results`` bound (R6)."""
    return min(num_results, _OSS_MAX_RESULTS)


def _query_snapshot(watch: Watch, *, exa_configured: bool) -> dict[str, Any]:
    """Snapshot the effective query, incl. the R6 clamp and ``recency_days=None`` (R5)."""
    snapshot: dict[str, Any] = {
        "query": watch.query,
        "search_type": watch.search_type,
        "category": watch.category,
        "recency_days": None,
        "include_domains": list(watch.include_domains),
        "exclude_domains": list(watch.exclude_domains),
    }
    if watch.answer_mode != "recall":
        # Gated so recall-mode snapshots stay byte-identical to v1 (#4250).
        snapshot["answer_mode"] = watch.answer_mode
        snapshot["effort"] = watch.effort
    if watch.bridge is not None:
        snapshot["bridge"] = {"webset_id": watch.bridge.webset_id}
    if exa_configured:
        snapshot["num_results"] = watch.num_results
        return snapshot
    clamped = _oss_clamped_num_results(watch.num_results)
    snapshot["num_results"] = clamped
    if clamped != watch.num_results:
        snapshot["num_results_clamped_from"] = watch.num_results
    return snapshot


def _last_run_at(store: MonitorStore, watch_id: str) -> datetime | None:
    """Newest run's ``started_at`` regardless of status.

    Failed runs count as a cadence tick too: a watch whose recall keeps failing
    must not retry on every 60s wake-up.
    """
    runs, _ = store.list_runs(watch_id, limit=1)
    return runs[0].started_at if runs else None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
