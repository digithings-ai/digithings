# score:allow untyped any
# service payloads and facade results are dynamic JSON; Any is the honest annotation.
"""Phase D webset service facade (#4066, Task 6) — the sync API over T1-T5.

All functions are synchronous store I/O except the background work they hand to
the scheduler seam; every one takes an optional ``store`` and otherwise resolves
:func:`~digisearch.websets.store.get_store` (one thread-bound sqlite connection
per call, the Phase C discipline). The async entry point ``run_webset_async``
lives in :mod:`digisearch.websets.runner` and is re-exported here because the
spec's § Interfaces places it on the service surface; the remaining async
entries (``backfill_enrichment``, ``resume_incomplete_websets``,
``schedule_webset_task``) stay runner-owned.

Scheduling seam
---------------
The facade never opens an ``asyncio`` task itself (bare ``asyncio.create_task``
is banned, § Async lifecycle — the server lifespan owns the TaskGroup and the
``WEBSET_TASKS`` registry). Instead:

- :class:`WebsetScheduler` is the process-wide seam the serving lifespan
  installs for one install window — first entry to last exit (``set_scheduler``)
  — reference-counted across concurrent HTTP/MCP lifespan invocations and torn
  down by the last exit (#4170/#4189). Sequential windows reinstall the seam
  and re-run the startup resume; the default is a logging no-op so offline
  callers — tests, CLI, scripts — can drive runs explicitly via
  ``runner.run_webset_async`` / ``runner.backfill_enrichment``.
- ``create_webset`` / ``add_search`` / ``trigger_monitor`` call
  ``schedule_run``; ``add_enrichment`` calls ``schedule_backfill`` (the def is
  attached with status ``running`` and the worker drains the verified items
  lacking the field through ``runner.backfill_enrichment``, same semaphore and
  per-item containment as the main pass).
- ``verification_mode`` is persisted on the created ``Webset`` and its initial
  ``WebsetSearch`` (T6 review carry); refresh schedules (``add_search`` /
  ``trigger_monitor``) inherit the webset's / latest generation's mode, so a
  ``rules`` webset never silently switches to ``llm``.
- Webhook delivery is wired in the event writer, not here: every event append
  fans out through ``websets/events.deliver_webhook`` (per-target ledger rows,
  never raising). ``add_webhook`` below enforces the Phase C SSRF/private-IP
  rejection **before** a target is stored, so no delivery can reach a private
  address (the R13 human gate).

Error-code mapping (stable codes surfaced to the HTTP/MCP tier)
---------------------------------------------------------------
Raised directly by the facade (spec § Interfaces stable list):

- ``invalid_criteria`` — criteria outside 1-5 rules;
- ``invalid_verification_mode`` — mode outside ``llm|rules``;
- ``datatap_websets_disabled`` — ``workspace_id == "datatap"`` (mirrors Phase C);
- ``enrichment_limit_exceeded`` — more than 10 active enrichments;
- ``webhook_url_required`` / ``webhook_url_private`` — the Phase C delivery
  validator's codes and message text, reused verbatim so one client handler
  covers both webhook egresses.

Surfaced unchanged from consumed layers (the spec list plus the carried
siblings T2/T5b documented): ``webset_not_found`` (as
:class:`WebsetNotFoundError`), ``search_not_found``, ``monitor_not_found``,
``item_not_found``, ``enrichment_not_found``, ``webhook_not_found``,
``enrichment_limit_exceeded``, ``cursor_not_found``. Carried for T7's HTTP
mapping but never raised by the facade: ``webhook_secret_missing`` (a T5b
delivery-ledger receipt error, surfaced only as delivery state, never as a
route failure).

Terminal-state gate (T6 review carry): ``add_search`` / ``trigger_monitor`` /
``add_enrichment`` reject a webset in a terminal ``cancelled``/``failed`` state
with ``webset_terminal`` — a running search appended to a terminal webset can
never settle and would be re-selected by startup resume forever. ``idle`` is a
success-terminal that explicitly remains refreshable (that is the refresh
path).

Store-internal invariants — ``webset_not_settled``, ``transition_invalid``,
``invalid_event_kind``, ``invalid_webhook_delivery``, ``event_not_stored``,
``webhook_id_required`` — are **never** surfaced: they mean the facade crossed a
writer's path it must not cross, so they map to ``internal_error`` (logged
server-side with the original code, generic message client-side). ``count``
bounds (1-100) and monitor ``interval_seconds >= 60`` are enforced by the T1
models themselves (``WebsetSearch`` / ``WebsetMonitor`` field constraints), so
out-of-range values raise ``pydantic.ValidationError`` before any write.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, TypeVar, get_args

from digisearch.monitors.delivery import DeliveryConfigError, validate_delivery
from digisearch.monitors.models import DeliveryConfig, DeliveryTarget
from digisearch.monitors.validation import DATATAP_WORKSPACE_ID
from digisearch.websets import events
from digisearch.websets.export import export_csv, export_json
from digisearch.websets.models import (
    EnrichmentDef,
    VerificationCriterion,
    VerificationState,
    WebhookConfig,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetMonitor,
    WebsetSearch,
)

# Spec-surface re-export: § Interfaces groups ``run_webset_async`` with the
# service functions; its landed implementation home is ``websets/runner.py``.
from digisearch.websets.runner import run_webset_async
from digisearch.websets.store import WebsetStore, WebsetStoreError, get_store
from digisearch.websets.verify import MAX_CRITERIA, VerificationMode

logger = logging.getLogger(__name__)

__all__ = [
    "CARRIED_ERROR_CODES",
    "DEFAULT_VERIFICATION_MODE",
    "INTERNAL_ERROR_CODE",
    "MAX_ENRICHMENTS",
    "ROTATION_OVERLAP",
    "SPEC_ERROR_CODES",
    "WebsetScheduler",
    "WebsetNotFoundError",
    "WebsetServiceError",
    "add_enrichment",
    "add_search",
    "add_webhook",
    "cancel_webset",
    "count_items",
    "create_monitor",
    "create_webset",
    "export_webset",
    "get_webset",
    "list_events",
    "list_items",
    "list_monitors",
    "remove_enrichment",
    "rotate_webhook_secret",
    "run_webset_async",
    "set_scheduler",
    "trigger_monitor",
]

T = TypeVar("T")

#: Spec default (``create_webset`` text); refreshes schedule with this mode.
DEFAULT_VERIFICATION_MODE = "llm"

#: Mirrors ``Webset.enrichments``' ``max_length=10`` and the store's cap.
MAX_ENRICHMENTS = 10

#: ``secrets.token_urlsafe(32)`` per the webhook contract.
WEBHOOK_SECRET_BYTES = 32

#: Rotation grace window (spec: the old secret stays valid for 24h).
ROTATION_OVERLAP = timedelta(hours=24)

#: The spec's stable error-code list (all in the ``digibase.errors`` envelope).
SPEC_ERROR_CODES = (
    "webset_not_found",
    "search_not_found",
    "monitor_not_found",
    "enrichment_limit_exceeded",
    "cursor_not_found",
    "invalid_criteria",
    "invalid_verification_mode",
    "datatap_websets_disabled",
    "webhook_url_required",
    "webhook_url_private",
    "webset_terminal",
    "rate_limit_exceeded",
)

#: Codes from consumed layers that the spec's list omits (documented for T7).
#: ``webhook_secret_missing`` is a T5b delivery-ledger receipt error only.
CARRIED_ERROR_CODES = (
    "item_not_found",
    "enrichment_not_found",
    "webhook_not_found",
    "webhook_secret_missing",
)

#: Mapping target for store-internal invariant violations (never a caller input).
INTERNAL_ERROR_CODE = "internal_error"

#: Terminal webset statuses that refuse new work (``idle`` is refreshable).
_TERMINAL_REFRESH_BLOCKED = frozenset({"cancelled", "failed"})

#: Store codes surfaced unchanged; everything else maps to ``INTERNAL_ERROR_CODE``.
_PASSTHROUGH_CODES = frozenset(
    {
        "search_not_found",
        "monitor_not_found",
        "item_not_found",
        "enrichment_not_found",
        "webhook_not_found",
        "enrichment_limit_exceeded",
        "cursor_not_found",
    }
)

#: Provisional parent id for the initial search: ``store.create_webset`` mints the
#: real webset/search ids and rewrites ``webset_id`` (T2's nested-child contract),
#: so the search validates here — before any write — with a placeholder parent.
_PROVISIONAL_WEBSET_ID = "pending"

_EXPORT_MEDIA_TYPES: dict[str, tuple[Callable[[Webset, Sequence[WebsetItem]], str], str]] = {
    "csv": (export_csv, "text/csv"),
    "json": (export_json, "application/json"),
}


class WebsetServiceError(RuntimeError):
    """Service failure carrying the stable API-facing ``code`` (see mapping above)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class WebsetNotFoundError(WebsetServiceError):
    """The webset id does not exist (the documented ``get_webset`` error)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="webset_not_found")


class WebsetScheduler(Protocol):
    """Process-level background-run seam installed by the server lifespan (T7).

    Implementations register ``runner.run_webset_async`` /
    ``runner.backfill_enrichment`` execution with the lifespan ``TaskGroup`` +
    ``WEBSET_TASKS`` registry (never awaiting inline, never a bare
    ``asyncio.create_task``). The facade calls these from sync code only.
    """

    def schedule_run(
        self, webset_id: str, *, verification_mode: str = DEFAULT_VERIFICATION_MODE
    ) -> None:
        """Register one settling pass for *webset_id*."""

    def schedule_backfill(self, webset_id: str, enrichment_id: str) -> None:
        """Register the ``add_enrichment`` backfill for one attached def."""


class _NullScheduler:
    """Default no-op scheduler: runs are driven explicitly by the caller."""

    def schedule_run(
        self, webset_id: str, *, verification_mode: str = DEFAULT_VERIFICATION_MODE
    ) -> None:
        logger.warning(
            "no webset scheduler installed; run not scheduled webset_id=%s mode=%s",
            webset_id,
            verification_mode,
        )

    def schedule_backfill(self, webset_id: str, enrichment_id: str) -> None:
        logger.warning(
            "no webset scheduler installed; backfill not scheduled webset_id=%s enrichment_id=%s",
            webset_id,
            enrichment_id,
        )


_scheduler: WebsetScheduler = _NullScheduler()


def set_scheduler(scheduler: WebsetScheduler | None) -> None:
    """Install the background-run scheduler (server lifespan); ``None`` restores no-op."""
    global _scheduler
    _scheduler = scheduler if scheduler is not None else _NullScheduler()


# ── websets ───────────────────────────────────────────────────────────────────


def create_webset(
    *,
    query: str,
    count: int = 10,
    criteria: list[VerificationCriterion] | list[dict[str, str]],
    enrichments: list[EnrichmentDef] | list[dict[str, object]] | None = None,
    verification_mode: Literal["llm", "rules"] = "llm",
    workspace_id: str | None = None,
    store: WebsetStore | None = None,
) -> Webset:
    """Create a webset + its initial search, schedule the run, return ``running``.

    ``count`` is the target VERIFIED item count for the initial search (1-100,
    enforced by ``WebsetSearch``), never a backend page size. The OSS path always
    recalls via ``search_web``; there is no provider selector (R4).
    """
    if workspace_id == DATATAP_WORKSPACE_ID:
        raise WebsetServiceError(
            "Websets are disabled for the datatap workspace.",
            code="datatap_websets_disabled",
        )
    mode = _verification_mode(verification_mode)
    rules = _criteria(criteria)
    definitions = _enrichments(enrichments or [])
    # Validate query/count/criteria before any write: the store rewrites the
    # provisional parent id when it persists the nested search (T2 contract).
    # The mode is persisted on both the webset (the default future searches
    # inherit) and this initial generation (the mode the pass actually runs).
    initial_search = WebsetSearch(
        webset_id=_PROVISIONAL_WEBSET_ID,
        query=query,
        count=count,
        criteria=rules,
        verification_mode=mode,
    )
    store = _store_or_default(store)
    created = _call(
        store.create_webset,
        Webset(
            criteria=rules,
            enrichments=definitions,
            workspace_id=workspace_id,
            verification_mode=mode,
            searches=[initial_search],
        ),
    )
    _schedule_run(created.id, verification_mode=mode)
    return created


def get_webset(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Return the webset or raise :class:`WebsetNotFoundError`."""
    return _require_webset(_store_or_default(store), webset_id)


def list_items(
    webset_id: str,
    *,
    verification: VerificationState | None = None,
    limit: int = 50,
    cursor: str | None = None,
    store: WebsetStore | None = None,
) -> tuple[list[WebsetItem], str | None]:
    """List items NEWEST-first, cursor-paged (R11); unknown cursor → ``cursor_not_found``."""
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    return _call(
        store.list_items,
        webset_id,
        verification=verification,
        limit=limit,
        cursor=cursor,
    )


def count_items(webset_id: str, *, store: WebsetStore | None = None) -> dict[str, int]:
    """Item counts per verification state (``verified``/``pending``/``rejected``).

    The MCP/orchestrator ``websets_get`` op reports status + counts; the store
    owns the aggregate so no caller pages every item to count them.
    """
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    return _call(store.count_items, webset_id)


def add_search(
    webset_id: str,
    *,
    query: str,
    count: int = 10,
    criteria: list[VerificationCriterion] | list[dict[str, str]] | None = None,
    store: WebsetStore | None = None,
) -> WebsetSearch:
    """Attach a follow-up search and schedule its run; missing criteria inherits.

    The refresh inherits the webset's persisted ``verification_mode`` and
    rejects a terminal (``cancelled``/``failed``) webset with
    ``webset_terminal``.
    """
    store = _store_or_default(store)
    webset = _require_webset(store, webset_id)
    _require_refreshable(webset)
    rules = webset.criteria if criteria is None else _criteria(criteria)
    mode = webset.verification_mode
    created = _call(
        store.add_search,
        WebsetSearch(
            webset_id=webset_id,
            query=query,
            count=count,
            criteria=rules,
            verification_mode=mode,
        ),
    )
    _schedule_run(webset_id, verification_mode=mode)
    return created


def cancel_webset(webset_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Set ``status=cancelled``; the runner stops scheduling and settles searches (I6)."""
    store = _store_or_default(store)
    return _call(store.cancel_webset, webset_id)


# ── enrichments ───────────────────────────────────────────────────────────────


def add_enrichment(
    webset_id: str,
    enrichment: EnrichmentDef | dict[str, object],
    *,
    store: WebsetStore | None = None,
) -> EnrichmentDef:
    """Attach an enrichment (max 10 active, status ``running``) and schedule its backfill.

    Rejects a terminal (``cancelled``/``failed``) webset with
    ``webset_terminal`` (T6 review carry).
    """
    store = _store_or_default(store)
    webset = _require_webset(store, webset_id)
    _require_refreshable(webset)
    definition = (
        enrichment
        if isinstance(enrichment, EnrichmentDef)
        else EnrichmentDef.model_validate(enrichment)
    )
    attached = _call(
        store.add_enrichment,
        webset_id,
        definition.model_copy(update={"status": "running"}),
    )
    _schedule_backfill(webset_id, attached.id)
    return attached


def remove_enrichment(
    webset_id: str, enrichment_id: str, *, store: WebsetStore | None = None
) -> None:
    """Detach an enrichment; already-resolved item values are retained."""
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    _call(store.remove_enrichment, webset_id, enrichment_id)


# ── monitors (poll-only v1, R8) ───────────────────────────────────────────────


def create_monitor(
    webset_id: str,
    *,
    interval_seconds: int = 3600,
    webhook_url: str | None = None,
    store: WebsetStore | None = None,
) -> WebsetMonitor:
    """Record a refresh cadence (metadata only; no tick driver runs it in v1).

    A ``webhook_url`` is validated with the Phase C delivery rule (https, public
    address) even though v1 never delivers from a monitor record.
    """
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    if webhook_url is not None:
        _validate_webhook_url(webhook_url)
    monitor = WebsetMonitor(
        webset_id=webset_id, interval_seconds=interval_seconds, webhook_url=webhook_url
    )
    return _call(store.add_monitor, webset_id, monitor)


def list_monitors(webset_id: str, *, store: WebsetStore | None = None) -> list[WebsetMonitor]:
    """List a webset's monitors newest-created first (poll-only v1 operator surface)."""
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    return _call(store.list_monitors, webset_id)


def trigger_monitor(webset_id: str, monitor_id: str, *, store: WebsetStore | None = None) -> Webset:
    """Manually refresh: open a new search generation (the v1 tick-driver substitute).

    The new generation inherits the latest search's persisted
    ``verification_mode`` — straight inheritance: ``WebsetSearch.verification_mode``
    is never empty (a non-optional ``VerificationMode``), so there is no
    fallback to prefer, and every generation (including the runner's backfill
    generations) is persisted carrying the webset's mode. A terminal
    (``cancelled``/``failed``) webset is rejected with ``webset_terminal``.
    """
    store = _store_or_default(store)
    webset = _require_webset(store, webset_id)
    _require_refreshable(webset)
    _call(store.get_monitor, webset_id, monitor_id)
    if not webset.searches:
        raise WebsetServiceError(
            f"webset {webset_id} has no search generation to re-run",
            code="search_not_found",
        )
    latest = webset.searches[-1]
    mode = latest.verification_mode
    _call(
        store.add_search,
        WebsetSearch(
            webset_id=webset_id,
            query=latest.query,
            count=latest.count,
            criteria=latest.criteria,
            verification_mode=mode,
        ),
    )
    _schedule_run(webset_id, verification_mode=mode)
    return _call(store.get_webset, webset_id)


# ── webhooks (delivery wiring stays with T7; R13 gate) ────────────────────────


def add_webhook(
    webset_id: str,
    *,
    url: str,
    events: list[str],
    store: WebsetStore | None = None,
) -> WebhookConfig:
    """Register a webhook; the server-generated secret is returned once here.

    The URL passes the Phase C SSRF/private-IP rejection (https-only, no
    userinfo, every resolved address public — identical codes/message text) and
    is validated *before* the record is stored.
    """
    _validate_webhook_url(url)
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    config = WebhookConfig(url=url, events=list(events), secret=_new_webhook_secret())
    return _call(store.add_webhook, webset_id, config)


def rotate_webhook_secret(
    webset_id: str, webhook_id: str, *, store: WebsetStore | None = None
) -> WebhookConfig:
    """Rotate to a new secret with a 24h overlap; returns the NEW secret once."""
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    webhook = _call(store.get_webhook, webset_id, webhook_id)
    rotated = webhook.model_copy(
        update={
            "secret": _new_webhook_secret(),
            "previous_secret": webhook.secret or None,
            "previous_expires_at": datetime.now(UTC) + ROTATION_OVERLAP,
        }
    )
    return _call(store.update_webhook, webset_id, rotated)


# ── events ────────────────────────────────────────────────────────────────────


def list_events(
    webset_id: str,
    *,
    after: str | None = None,
    limit: int = 50,
    store: WebsetStore | None = None,
) -> tuple[list[WebsetEvent], str | None]:
    """Cursor-page the append-only event log oldest-first (R11); ``after`` is the
    last seen event id; unknown cursor → ``cursor_not_found``."""
    store = _store_or_default(store)
    _require_webset(store, webset_id)
    return _call(events.list_events, store, webset_id, after=after, limit=limit)


# ── export ────────────────────────────────────────────────────────────────────


def export_webset(
    webset_id: str,
    *,
    fmt: Literal["csv", "json"] = "json",
    store: WebsetStore | None = None,
) -> tuple[str, str]:
    """Return ``(content, media_type)``; only verified items are exported."""
    store = _store_or_default(store)
    webset = _require_webset(store, webset_id)
    try:
        exporter, media_type = _EXPORT_MEDIA_TYPES[fmt]
    except KeyError as exc:
        raise ValueError(f"unknown export format {fmt!r}; expected 'csv' or 'json'") from exc
    return exporter(webset, _verified_items(store, webset_id)), media_type


# ── internals ─────────────────────────────────────────────────────────────────


def _store_or_default(store: WebsetStore | None) -> WebsetStore:
    return store if store is not None else get_store()


def _require_webset(store: WebsetStore, webset_id: str) -> Webset:
    return _call(store.get_webset, webset_id)


def _require_refreshable(webset: Webset) -> None:
    """Reject new work on a terminal ``cancelled``/``failed`` webset.

    ``idle`` is the success terminal and stays refreshable (the refresh path);
    appending a running search to a ``cancelled``/``failed`` webset could never
    settle and would be re-selected by startup resume forever (T6 review
    carry).
    """
    if webset.status in _TERMINAL_REFRESH_BLOCKED:
        raise WebsetServiceError(
            f"webset {webset.id} is {webset.status} and cannot accept new work",
            code="webset_terminal",
        )


def _verified_items(store: WebsetStore, webset_id: str) -> list[WebsetItem]:
    """Every verified item, paging through the store's bounded item cursor."""
    items, cursor = _call(store.list_items, webset_id, verification="verified", limit=200)
    while cursor is not None:
        page, cursor = _call(
            store.list_items, webset_id, verification="verified", limit=200, cursor=cursor
        )
        items.extend(page)
    return items


def _schedule_run(webset_id: str, *, verification_mode: str = DEFAULT_VERIFICATION_MODE) -> None:
    _scheduler.schedule_run(webset_id, verification_mode=verification_mode)


def _schedule_backfill(webset_id: str, enrichment_id: str) -> None:
    _scheduler.schedule_backfill(webset_id, enrichment_id)


def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Invoke *fn*, translating every :class:`WebsetStoreError` to a stable code."""
    try:
        return fn(*args, **kwargs)
    except WebsetStoreError as exc:
        raise _translate(exc) from exc


def _translate(exc: WebsetStoreError) -> WebsetServiceError:
    if exc.code == "webset_not_found":
        return WebsetNotFoundError(str(exc))
    if exc.code in _PASSTHROUGH_CODES:
        return WebsetServiceError(str(exc), code=exc.code)
    logger.warning("webset store invariant error mapped to %s: %s", INTERNAL_ERROR_CODE, exc.code)
    return WebsetServiceError("internal webset store failure", code=INTERNAL_ERROR_CODE)


def _verification_mode(value: str) -> str:
    modes = get_args(VerificationMode)
    if value not in modes:
        raise WebsetServiceError(
            f"unknown verification mode {value!r}; expected one of {', '.join(modes)}",
            code="invalid_verification_mode",
        )
    return value


def _criteria(
    criteria: Sequence[VerificationCriterion] | Sequence[dict[str, str]],
) -> list[VerificationCriterion]:
    parsed = [
        criterion
        if isinstance(criterion, VerificationCriterion)
        else VerificationCriterion.model_validate(criterion)
        for criterion in criteria
    ]
    if not 1 <= len(parsed) <= MAX_CRITERIA:
        raise WebsetServiceError(
            f"criteria must carry between 1 and {MAX_CRITERIA} rules, got {len(parsed)}",
            code="invalid_criteria",
        )
    return parsed


def _enrichments(
    enrichments: Sequence[EnrichmentDef] | Sequence[dict[str, object]],
) -> list[EnrichmentDef]:
    parsed = [
        enrichment
        if isinstance(enrichment, EnrichmentDef)
        else EnrichmentDef.model_validate(enrichment)
        for enrichment in enrichments
    ]
    if len(parsed) > MAX_ENRICHMENTS:
        raise WebsetServiceError(
            f"at most {MAX_ENRICHMENTS} active enrichments per webset",
            code="enrichment_limit_exceeded",
        )
    return parsed


def _validate_webhook_url(url: str) -> None:
    """Reuse Phase C's https + public-address gate verbatim (codes + message text)."""
    try:
        validate_delivery(
            DeliveryConfig(mode="webhook", targets=[DeliveryTarget(kind="webhook", url=url)])
        )
    except DeliveryConfigError as exc:
        raise WebsetServiceError(str(exc), code=exc.code) from exc


def _new_webhook_secret() -> str:
    return secrets.token_urlsafe(WEBHOOK_SECRET_BYTES)
