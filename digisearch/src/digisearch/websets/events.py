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
R13) and extend this module: :func:`deliver_webhook` consumes the append-only
event stream and POSTs ``{event, webset_id, delivered_at}`` to every subscribed,
active webhook of the event's webset, signing with the shared Phase C core
(:func:`~digisearch.monitors.delivery.sign_webhook_body`) so
``X-digi-signature`` is byte-identical across both egresses (R7). Delivery state
lives only in the ledger (INSERT-or-ignore on ``(webhook_id, event_id)``);
event rows are never mutated, and a per-target failure is a recorded ``failed``
row with a redacted error — never an exception out of the delivery path.

Rotation overlap (R7, divergence from Phase C's immediate rotate):
:func:`verify_webhook_signature` accepts a webhook's ``previous_secret`` only
while ``previous_expires_at`` is in the future, then drops it.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from digisearch.monitors.delivery import sign_webhook_body
from digisearch.websets.models import EventKind, WebhookConfig, WebsetEvent, WebsetItem
from digisearch.websets.store import WebhookDelivery, WebsetStore

__all__ = [
    "append_event",
    "deliver_webhook",
    "emit_item_created",
    "emit_item_enriched",
    "emit_webset_failed",
    "emit_webset_idle",
    "list_events",
    "sign_webhook_body",
    "verify_webhook_signature",
]

logger = logging.getLogger(__name__)

#: § Webhook delivery (R7): 3 attempts, then the pinned 5s/25s backoff.
_WEBHOOK_ATTEMPTS = 3
_WEBHOOK_BACKOFF_S: tuple[float, ...] = (5.0, 25.0)
_DEFAULT_TIMEOUT_S = 10.0

#: Stable ledger error for a webhook whose server-generated secret is missing.
_SECRET_MISSING = "webhook_secret_missing"

# Sleep seam: tests record backoff without waiting (Phase C `_sleep` precedent).
_sleep = time.sleep


def append_event(store: WebsetStore, event: WebsetEvent) -> WebsetEvent:
    """Append one event through the store's INSERT-or-ignore path.

    Returns the canonical stored row: a duplicate within a generation returns
    the first stored event instead of appending a second one (the
    ``(webset_id, dedup_key)`` UNIQUE index).
    """
    return store.append_event(event)


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

    Always the current secret; the previous secret only while its 24h overlap
    window is still open. A previous secret with no expiry is ignored — rotation
    must stay bounded (an unbounded old secret would defeat it).
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


def _redacted_error(exc: BaseException, *, secret: str, target_url: str | None) -> str:
    """Exception text safe for ledger rows and logs (R8; Phase C pattern).

    httpx transport errors may embed the request URL (whose path can carry a
    webhook token), so both the target URL and the webhook secret are stripped
    before the text leaves this module.
    """
    text = f"{type(exc).__name__}: {exc}"
    if secret:
        text = text.replace(secret, "<redacted>")
    if target_url:
        for needle in {target_url, target_url.rstrip("/")}:
            if needle:
                text = text.replace(needle, "<target>")
    return text


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
                _sleep(_WEBHOOK_BACKOFF_S[attempt - 2])
            try:
                response = client.post(webhook.url, content=payload, headers=headers)
            except Exception as exc:
                status_code = None
                error = _redacted_error(exc, secret=webhook.secret, target_url=webhook.url)
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
    this path and never abort the remaining targets. Returns the terminal
    ledger rows in webhook registration order. Never mutates the event row.
    """
    delivered_at = now or datetime.now(UTC)
    payload = _delivery_body(event, delivered_at)
    results: list[WebhookDelivery] = []
    for webhook in store.list_webhooks(event.webset_id):
        if not webhook.active or event.type not in webhook.events:
            continue
        recorded = store.get_webhook_delivery(webhook.webhook_id, event.id)
        if recorded is not None:
            results.append(recorded)
            continue
        try:
            if not webhook.secret:
                # Fail closed: a server-generated secret is missing, so nothing
                # is POSTed (signing with "" would send an unverifiable request).
                ok, status_code, error = False, None, _SECRET_MISSING
            else:
                ok, status_code, error = _attempt_delivery(webhook, payload, timeout_s=timeout_s)
        except Exception as exc:  # containment boundary: nothing escapes delivery
            ok, status_code = False, None
            error = _redacted_error(exc, secret=webhook.secret, target_url=webhook.url)
        store.record_webhook_delivery(
            webhook.webhook_id, event.id, ok=ok, status_code=status_code, error=error
        )
        row = store.get_webhook_delivery(webhook.webhook_id, event.id)
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
