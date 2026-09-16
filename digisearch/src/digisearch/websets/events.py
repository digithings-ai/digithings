# score:allow untyped any
# event payloads and delivery receipts are heterogeneous JSON; Any is the honest annotation.
"""Phase D webset events (#4066, Task 5a) — the single event writer.

The append-only ``events`` table and its ``(webset_id, dedup_key)`` generation
key are owned by the T2 store (``websets/store.py``): the dedup key is built from
``(kind, search_id, item_id or "", field or "")`` so a resumed pass within one
``WebsetSearch`` generation cannot duplicate an event, while each new generation
(``add_search`` / the ``add_enrichment`` backfill run / ``trigger_monitor``) may
legitimately re-emit terminal events (spec § Async lifecycle, flag I3).

This module is the only place the runner builds event rows, and it delegates
every write to :meth:`WebsetStore.append_event` — events are never written
anywhere else (single-writer rule; T2 review note), so the dedup-key and
generation scheme is enforced at exactly one site. ``payload`` is the compact
delivery/consumer body (ids, urls, titles, field names, reasoning) and never a
full page body.

Webhook fan-out and the ``webhook_deliveries`` ledger are Task 5b (human gate,
R13) and **wired into the append path here**: :func:`append_event` fans every
stored event out through :func:`deliver_webhook`, which POSTs
``{event, webset_id, delivered_at}`` to every subscribed, active webhook of the
event's webset, signing with the shared Phase C core
(:func:`~digisearch.monitors.delivery.sign_webhook_body`) so
``X-digi-signature`` is byte-identical across both egresses (R7). Delivery state
lives only in the ledger (INSERT-or-ignore on ``(webhook_id, event_id)``);
event rows are never mutated, and a per-target failure is a recorded ``failed``
row with a redacted error — never an exception out of the append/delivery path.
Re-appending a duplicate (same generation dedup key) re-runs delivery, which the
ledger turns into a no-op for already-recorded targets — so a crash between the
append and its fan-out is recoverable, without ever double-POSTing a target.

Rotation overlap (R7, divergence from Phase C's immediate rotate):
:func:`verify_webhook_signature` accepts a webhook's ``previous_secret`` only
while ``previous_expires_at`` is in the future, then drops it.

Re-delivery (#4226, the retired ARCH deferral): :func:`redeliver_webhook`
re-attempts one failed ledger row on behalf of the shared driver's re-delivery
loop (``websets/driver.py``). It rebuilds the byte-identical
``{event, webset_id, delivered_at}`` body from the stored event and re-POSTs
through the same :func:`_attempt_delivery` core (the in-call 3-attempt/5s-25s
backoff is preserved), always signing with the webhook's *current* secret so a
retry after rotation is accepted under the 24h overlap. Retries are bounded —
``_WEBHOOK_REDELIVERY_ATTEMPTS`` attempts on the pinned
``_WEBHOOK_REDELIVERY_BACKOFF_S`` ladder — and each outcome updates the same
ledger row in place; an exhausted row keeps a terminal failed row that the due
selector never offers again. :func:`deliver_webhook`'s one-shot semantics are
unchanged (its "a recorded terminal failure is final" contract governs the
append path; re-delivery is the loop explicitly driving failed rows).
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from digisearch.monitors.delivery import redact_error, sign_webhook_body
from digisearch.websets.models import EventKind, WebhookConfig, WebsetEvent, WebsetItem
from digisearch.websets.store import WebhookDelivery, WebsetStore, WebsetStoreError

__all__ = [
    "append_event",
    "deliver_webhook",
    "emit_item_created",
    "emit_item_enriched",
    "emit_webset_failed",
    "emit_webset_idle",
    "list_events",
    "redeliver_webhook",
    "sign_webhook_body",
    "verify_webhook_signature",
]

logger = logging.getLogger(__name__)

#: § Webhook delivery (R7): 3 attempts, then the pinned 5s/25s backoff.
_WEBHOOK_ATTEMPTS = 3
_WEBHOOK_BACKOFF_S: tuple[float, ...] = (5.0, 25.0)
_DEFAULT_TIMEOUT_S = 10.0

#: § Webhook re-delivery (#4226): bounded attempts on the pinned 5m/30m/2h/6h
#: ladder. A failure stores ``attempts + 1`` and schedules the next attempt
#: from the ladder while that incremented count stays below
#: ``_WEBHOOK_REDELIVERY_ATTEMPTS``; the cap-many failure exhausts the row
#: (``next_attempt_at = None``), which the due selector then never offers again.
_WEBHOOK_REDELIVERY_ATTEMPTS = 4
_WEBHOOK_REDELIVERY_BACKOFF_S: tuple[float, ...] = (300.0, 1800.0, 7200.0, 21600.0)

#: Stable ledger error for a webhook whose server-generated secret is missing.
_SECRET_MISSING = "webhook_secret_missing"

#: Stable terminal ledger errors for a re-delivery target that can never POST:
#: the webhook is inactive (or no longer subscribed), deleted, or its event row
#: is gone. Recorded once, then exhausted.
_WEBHOOK_INACTIVE = "webhook_inactive"
_WEBHOOK_MISSING = "webhook_not_found"
_EVENT_MISSING = "event_not_found"

# Sleep seam: tests record backoff without waiting (Phase C `_sleep` precedent).
_sleep = time.sleep


def append_event(store: WebsetStore, event: WebsetEvent) -> WebsetEvent:
    """Append one event through the store's INSERT-or-ignore path, then fan it out.

    Returns the canonical stored row: a duplicate within a generation returns
    the first stored event instead of appending a second one (the
    ``(webset_id, dedup_key)`` UNIQUE index). The fan-out uses the T5b delivery
    contract (:func:`deliver_webhook`): one signed POST per subscribed, active
    webhook; per-target failures persist ledger rows and never raise, and the
    ledger keeps a re-appended duplicate from double-POSTing a target.
    """
    stored = store.append_event(event)
    try:
        deliver_webhook(store, stored)
    except Exception:
        # Belt-and-braces for "never raise out of the append path":
        # deliver_webhook contains every target/ledger fault itself; an escape
        # here means a containment regression and must still not fail the
        # append that produced the event (the ledger's INSERT-or-ignore means a
        # later delivery re-reads whatever was persisted).
        logger.exception(
            "webset webhook fan-out escaped containment webset_id=%s event_id=%s",
            stored.webset_id,
            stored.id,
        )
    return stored


def list_events(
    store: WebsetStore,
    webset_id: str,
    *,
    after: str | None = None,
    limit: int = 50,
) -> tuple[list[WebsetEvent], str | None]:
    """Cursor-page a webset's event log oldest-first (R11) through the store."""
    return store.list_events(webset_id, after=after, limit=limit)


def _emit(
    store: WebsetStore,
    webset_id: str,
    kind: EventKind,
    search_id: str,
    *,
    payload: dict[str, Any],
    item_id: str = "",
) -> WebsetEvent:
    return append_event(
        store,
        WebsetEvent(
            webset_id=webset_id,
            type=kind,
            search_id=search_id,
            item_id=item_id,
            payload=payload,
        ),
    )


def emit_item_created(store: WebsetStore, item: WebsetItem, search_id: str) -> WebsetEvent:
    """``item.created`` — emitted once the candidate passed verification.

    Rejected candidates emit no item event and stay queryable via
    ``items?verification=rejected`` for audit (spec § Architecture). The
    generation that admitted the item is part of the dedup key, so a resume
    within one ``WebsetSearch`` cannot duplicate this event.
    """
    return _emit(
        store,
        item.webset_id,
        "item.created",
        search_id,
        item_id=item.id,
        payload={"item_id": item.id, "url": item.url, "title": item.title},
    )


def emit_item_enriched(store: WebsetStore, item: WebsetItem, search_id: str) -> WebsetEvent:
    """``item.enriched`` — all requested fields settled with >= 1 resolved.

    An item whose every field is ``unresolved``/``skipped`` settles silently
    (spec § Architecture); this emitter is only called once the terminal-state
    conditions hold.
    """
    return _emit(
        store,
        item.webset_id,
        "item.enriched",
        search_id,
        item_id=item.id,
        payload={"item_id": item.id, "url": item.url, "fields": sorted(item.enrichments)},
    )


def emit_webset_idle(store: WebsetStore, webset_id: str, search_id: str) -> WebsetEvent:
    """``webset.idle`` — terminal ``webset.*`` events carry the pass generation."""
    return _emit(
        store,
        webset_id,
        "webset.idle",
        search_id,
        payload={"webset_id": webset_id, "status": "idle"},
    )


def emit_webset_failed(
    store: WebsetStore, webset_id: str, search_id: str, reason: str
) -> WebsetEvent:
    """``webset.failed`` — a webset-level failure under the pass generation."""
    return _emit(
        store,
        webset_id,
        "webset.failed",
        search_id,
        payload={"webset_id": webset_id, "status": "failed", "reason": reason},
    )


# ── webhook delivery (Task 5b, human gate R13) ────────────────────────────────


def _as_utc(value: datetime) -> datetime:
    """Normalize *value* to UTC (a naive timestamp is read as UTC, store-style)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _active_secrets(webhook: WebhookConfig, *, now: datetime) -> tuple[str, ...]:
    """Secrets a delivery may be verified under at *now* (rotation overlap, R7).

    Always the current secret; the previous secret only while its overlap
    window is open — i.e. any ``previous_expires_at`` still in the future (the
    24h value is a T6 caller convention, not enforced here). A previous secret
    with no expiry is ignored — rotation must stay bounded (an unbounded old
    secret would defeat it).
    """
    secrets = [webhook.secret] if webhook.secret else []
    expires = webhook.previous_expires_at
    if webhook.previous_secret and expires is not None and _as_utc(now) < _as_utc(expires):
        secrets.append(webhook.previous_secret)
    return tuple(secrets)


def verify_webhook_signature(
    webhook: WebhookConfig,
    payload: bytes,
    signature: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Verify *signature* for *payload* against a webhook's active secrets (R7).

    During the rotation overlap the previous secret is accepted alongside the
    current one; at/after ``previous_expires_at`` it is dropped. Comparison is
    constant-time against the shared signing core's output.
    """
    moment = now or datetime.now(UTC)
    return any(
        hmac.compare_digest(sign_webhook_body(secret, payload), signature)
        for secret in _active_secrets(webhook, now=moment)
    )


def _delivery_body(event: WebsetEvent, delivered_at: datetime) -> bytes:
    """The exact POST body: ``{event, webset_id, delivered_at}`` (§ Webhook delivery)."""
    body = {
        "event": event.model_dump(mode="json"),
        "webset_id": event.webset_id,
        "delivered_at": _as_utc(delivered_at).isoformat(),
    }
    return json.dumps(body).encode("utf-8")


def _retryable_status(status_code: int) -> bool:
    """Server errors and rate limiting are worth another attempt; 4xx is final."""
    return status_code == 429 or status_code >= 500


def _client_for(timeout_s: float) -> httpx.Client:
    """httpx client factory (test seam): bounded timeout, no redirects.

    Redirects are never followed so an approved public target cannot 30x the
    delivery to an internal address (Phase C SSRF precedent).
    """
    return httpx.Client(timeout=timeout_s, follow_redirects=False)


def _backoff_s(attempt: int) -> float:
    """Sleep before *attempt* (1-based) from the pinned 5s/25s sequence.

    The last pinned step repeats when ``_WEBHOOK_ATTEMPTS`` exceeds the number
    of steps — clamping instead of indexing the tuple keeps a longer retry
    schedule from raising ``IndexError`` mid-delivery.
    """
    return _WEBHOOK_BACKOFF_S[min(attempt - 2, len(_WEBHOOK_BACKOFF_S) - 1)]


def _attempt_delivery(
    webhook: WebhookConfig, payload: bytes, *, timeout_s: float
) -> tuple[bool, int | None, str | None]:
    """POST *payload* signed with the CURRENT secret; one terminal outcome.

    Returns ``(ok, status_code, error)`` where a failure carries a redacted
    error string instead of raising (transport exhaustion included). Retry
    policy per R7: 3 attempts with the pinned 5s/25s backoff; 429/5xx retry,
    any other 4xx is definitive and fails fast.
    """
    headers = {
        "Content-Type": "application/json",
        "X-digi-signature": sign_webhook_body(webhook.secret, payload),
    }
    status_code: int | None = None
    error: str | None = None
    with _client_for(timeout_s) as client:
        for attempt in range(1, _WEBHOOK_ATTEMPTS + 1):
            if attempt > 1:
                _sleep(_backoff_s(attempt))
            try:
                response = client.post(webhook.url, content=payload, headers=headers)
            except Exception as exc:
                status_code = None
                error = redact_error(exc, secret=webhook.secret, target_url=webhook.url)
                continue
            if response.is_success:
                return True, response.status_code, None
            status_code = response.status_code
            error = f"HTTP {response.status_code}"
            if not _retryable_status(response.status_code):
                break
    return False, status_code, error


def deliver_webhook(
    store: WebsetStore,
    event: WebsetEvent,
    *,
    now: datetime | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> list[WebhookDelivery]:
    """Deliver *event* to its webset's subscribed, active webhooks (R7).

    One signed POST per target with body ``{event, webset_id, delivered_at}``;
    a target whose ``(webhook_id, event_id)`` pair is already in the ledger is
    not re-attempted (INSERT-or-ignore dedup, so a resumed run cannot
    double-record, and a recorded terminal failure is final). Every outcome —
    success, HTTP failure, transport exhaustion, missing secret — becomes a
    ledger row with a redacted error; per-target failures never raise out of
    this path and never abort the remaining targets. Store faults are
    contained the same way: a ledger read failure skips that target (fail
    closed, no second POST), a ledger write failure is logged and the next
    target is still attempted, and a failed webhook listing returns no rows.
    Returns the terminal ledger rows in webhook registration order. Never
    mutates the event row.
    """
    delivered_at = now or datetime.now(UTC)
    try:
        webhooks = store.list_webhooks(event.webset_id)
    except Exception as exc:  # containment boundary: nothing escapes delivery
        # Only the exception class is logged: a stored webhook row can fail
        # validation with its secret embedded in the input, and no target is
        # known yet to redact against.
        logger.warning(
            "webset webhook fan-out aborted: listing webhooks failed "
            "webset_id=%s event_id=%s error=%s",
            event.webset_id,
            event.id,
            type(exc).__name__,
        )
        return []
    results: list[WebhookDelivery] = []
    for webhook in webhooks:
        if not webhook.active or event.type not in webhook.events:
            continue
        try:
            recorded = store.get_webhook_delivery(webhook.webhook_id, event.id)
        except Exception as exc:  # containment boundary: nothing escapes delivery
            # Fail closed: an unknown ledger state must not risk a second POST,
            # and the fault must not abort the remaining targets.
            logger.warning(
                "webset webhook ledger read failed webhook_id=%s event_id=%s error=%s",
                webhook.webhook_id,
                event.id,
                redact_error(exc, secret=webhook.secret, target_url=webhook.url),
            )
            continue
        if recorded is not None:
            results.append(recorded)
            continue
        try:
            payload = _delivery_body(event, delivered_at)
            if not webhook.secret:
                # Fail closed: a server-generated secret is missing, so nothing
                # is POSTed (signing with "" would send an unverifiable request).
                ok, status_code, error = False, None, _SECRET_MISSING
            else:
                ok, status_code, error = _attempt_delivery(webhook, payload, timeout_s=timeout_s)
        except Exception as exc:  # containment boundary: nothing escapes delivery
            ok, status_code = False, None
            error = redact_error(exc, secret=webhook.secret, target_url=webhook.url)
        try:
            store.record_webhook_delivery(
                webhook.webhook_id, event.id, ok=ok, status_code=status_code, error=error
            )
            row = store.get_webhook_delivery(webhook.webhook_id, event.id)
        except Exception as exc:  # containment boundary: nothing escapes delivery
            # Contained to this target; a later delivery re-reads whatever the
            # ledger actually persisted, and the remaining targets still run.
            logger.warning(
                "webset webhook ledger write failed webhook_id=%s event_id=%s error=%s",
                webhook.webhook_id,
                event.id,
                redact_error(exc, secret=webhook.secret, target_url=webhook.url),
            )
            continue
        if row is not None:
            results.append(row)
        if not ok:
            # Neither the secret nor the target URL is ever logged (R8); the
            # error text is already redacted.
            logger.warning(
                "webset webhook delivery failed webhook_id=%s event_id=%s status=%s error=%s",
                webhook.webhook_id,
                event.id,
                status_code,
                error,
            )
    return results


# ── webhook re-delivery (#4226) ───────────────────────────────────────────────


def _redelivery_backoff_s(attempt: int) -> float:
    """The pinned gap before 1-based *attempt*, clamped like :func:`_backoff_s`.

    Clamping (not indexing) keeps a raised ``_WEBHOOK_REDELIVERY_ATTEMPTS``
    from running past the pinned ladder with an ``IndexError``.
    """
    return _WEBHOOK_REDELIVERY_BACKOFF_S[min(attempt - 1, len(_WEBHOOK_REDELIVERY_BACKOFF_S) - 1)]


def _exhaust_delivery(store: WebsetStore, delivery: WebhookDelivery, error: str) -> WebhookDelivery:
    """Mark a row terminal without a POST (a target/event that can never deliver).

    ``attempts`` is pinned at the cap so the row drops out of
    ``list_due_webhook_deliveries`` even though ``next_attempt_at`` is ``None``
    (NULL there means "unscheduled, due now" for a fresh first-attempt failure).
    """
    return store.update_webhook_delivery(
        delivery.webhook_id,
        delivery.event_id,
        ok=False,
        status_code=None,
        error=error,
        attempts=_WEBHOOK_REDELIVERY_ATTEMPTS,
        next_attempt_at=None,
    )


def redeliver_webhook(
    store: WebsetStore,
    delivery: WebhookDelivery,
    *,
    now: datetime | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> WebhookDelivery:
    """Re-attempt one failed ledger row and update it in place (R7, #4226).

    The shared driver's re-delivery pass calls this for every due row:
    ``deliver_webhook``'s ``(webhook_id, event_id)`` INSERT-or-ignore contract
    makes it a no-op for recorded pairs, so this is the explicit re-drive.

    The POST reuses the delivery core unchanged: the payload is rebuilt with the
    same :func:`_delivery_body` from the stored event, and
    :func:`_attempt_delivery` keeps its 3 in-call attempts with the pinned
    5s/25s backoff. Signing always uses the webhook's *current* secret, so a
    retry after rotation lands inside the 24h previous-secret overlap.

    Ledger accounting (``attempts`` counts re-deliveries performed against the
    row): success stores ``ok=True``, the status, ``error=None`` and
    ``next_attempt_at=None`` (done). Failure stores ``attempts + 1`` and, while
    that count stays below ``_WEBHOOK_REDELIVERY_ATTEMPTS``, the next due moment
    from the pinned ladder; at the cap the row is exhausted
    (``next_attempt_at=None``) and stays a terminal failed ledger row. A
    webhook/event that is gone, or a webhook that is inactive or no longer
    subscribed, is exhausted once without a POST; a missing secret records the
    fail-closed ``webhook_secret_missing`` outcome exactly like the one-shot
    path (no egress). Store faults other than the not-found lookups propagate
    to the caller's per-row containment. Returns the updated ledger row.
    """
    moment = _as_utc(now or datetime.now(UTC))
    try:
        event = store.get_event(delivery.event_id)
    except WebsetStoreError as exc:
        if exc.code != "event_not_found":
            raise
        return _exhaust_delivery(store, delivery, _EVENT_MISSING)
    try:
        webhook = store.get_webhook(event.webset_id, delivery.webhook_id)
    except WebsetStoreError as exc:
        if exc.code != "webhook_not_found":
            raise
        return _exhaust_delivery(store, delivery, _WEBHOOK_MISSING)
    if not webhook.active or event.type not in webhook.events:
        return _exhaust_delivery(store, delivery, _WEBHOOK_INACTIVE)
    payload = _delivery_body(event, moment)
    if not webhook.secret:
        # Fail closed exactly like the one-shot path: nothing is POSTed (signing
        # with "" would send an unverifiable request); the attempt is recorded
        # and the bounded schedule still applies, so the row exhausts on its own.
        ok, status_code, error = False, None, _SECRET_MISSING
    else:
        ok, status_code, error = _attempt_delivery(webhook, payload, timeout_s=timeout_s)
    attempts = delivery.attempts + 1
    if ok:
        return store.update_webhook_delivery(
            delivery.webhook_id,
            delivery.event_id,
            ok=True,
            status_code=status_code,
            error=None,
            attempts=attempts,
            next_attempt_at=None,
        )
    next_attempt_at = (
        moment + timedelta(seconds=_redelivery_backoff_s(attempts))
        if attempts < _WEBHOOK_REDELIVERY_ATTEMPTS
        else None
    )
    logger.warning(
        "webset webhook re-delivery failed webhook_id=%s event_id=%s attempts=%s "
        "status=%s error=%s",
        delivery.webhook_id,
        delivery.event_id,
        attempts,
        status_code,
        error,
    )
    return store.update_webhook_delivery(
        delivery.webhook_id,
        delivery.event_id,
        ok=False,
        status_code=status_code,
        error=error,
        attempts=attempts,
        next_attempt_at=next_attempt_at,
    )
