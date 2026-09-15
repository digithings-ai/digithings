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

Fail-hard semantics: any recall exception persists a ``status="failed"`` run
with ``error=str(exc)`` and re-raises ``MonitorRunError`` carrying the persisted
``run_id``. A delivery-enabled run whose stored secret is ``None`` (see
:meth:`MonitorStore.get_delivery_secret`) fails just as loudly — the run is
persisted ``failed`` with ``delivery_secret_missing`` and ``MonitorRunError`` is
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
from digisearch.monitors.models import DeliveryReceipt, MonitorRun, Watch
from digisearch.monitors.store import MonitorStore, get_store, new_ulid
from digisearch.web_exa import ExaSearchType, WebSearchData, exa_search, is_exa_configured
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse
from digisearch.web_search.service import search_web

__all__ = ["MonitorRunError", "deliver", "is_due", "run_watch", "tick_due_watches"]

logger = logging.getLogger(__name__)

_RunStatus = Literal["ok", "no_change", "failed"]
_Trigger = Literal["schedule", "manual", "poll"]

# Landed WebSearchRequest.max_results bound (R6): the OSS seam clamps to it.
_OSS_MAX_RESULTS = 10

# §5: DataTap stays OFF end-to-end — the tick never runs a datatap-scoped watch.
_DATATAP_WORKSPACE_ID = "datatap"

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
    (``error="delivery_secret_missing"``) and raises :class:`MonitorRunError`.
    Delivery receipts are attached to the returned run; the append-only store
    cannot rewrite the already-persisted body, so stored runs keep ``delivery=[]``.
    """
    store = store if store is not None else get_store()
    watch = store.get_watch(watch_id)
    started_at = datetime.now(UTC)
    exa_configured = is_exa_configured()
    query_snapshot = _query_snapshot(watch, exa_configured=exa_configured)

    try:
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
    status: _RunStatus = "ok" if results_new else "no_change"

    error: str | None = None
    deliver_after_persist = status == "ok" and watch.delivery.mode != "poll"
    delivery_secret: str | None = None
    if deliver_after_persist:
        delivery_secret = store.get_delivery_secret(watch_id)
        if delivery_secret is None:
            status = "failed"
            error = _DELIVERY_SECRET_MISSING
            deliver_after_persist = False

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
        receipts = deliver(run, watch, delivery_secret=delivery_secret)
        run = run.model_copy(update={"delivery": receipts})

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
        if not watch.schedule.enabled or watch.workspace_id == _DATATAP_WORKSPACE_ID:
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


def _invoke_shallow_recall(
    *,
    query: str,
    search_type: str,
    num_results: int,
    category: str | None,
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
) -> WebSearchData:
    """Call the shallow recall leg directly in-process and return ``WebSearchData``.

    EXA when configured; otherwise the OSS seam with ``recency_days=None`` (R5)
    and the R6 clamp, adapted through :func:`_oss_response_to_data` (R3). The
    EXA-only ``search_type``/``category`` knobs are passed only to EXA.
    """
    if is_exa_configured():
        return exa_search(
            query,
            search_type=cast(ExaSearchType, search_type),
            num_results=num_results,
            category=category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
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
