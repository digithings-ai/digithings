# score:allow untyped any
# EXA payloads are dynamic remote JSON; Any is the honest annotation.
"""Phase C EXA monitor adapter — live-pinned 2026-09-16, fail closed (#4065, #4123).

**PIN (observed 2026-09-16, real key).** The follow-up live probe
(``.superpowers/sdd/4123-exa-shape-pin/spike-output-3.txt``) replaced this
module's earlier EXPERIMENTAL assumptions: the monitors endpoints ARE
accessible on the operator's key tier — create/list/get/trigger/runs/delete all
answer 2xx, no 401/403 (the websets family stays Pro-gated). Pinned remote
shapes:

- ``POST /monitors`` (201). Request ``{"search": {"query": …}, "trigger":
  {"type": "interval", "period": "1d"}, "webhook": {"url": …}}``; response
  carries ``id/name/status/search/trigger/outputSchema/metadata/webhook/
  nextRunAt/createdAt/updatedAt`` plus a one-time 32-char ``webhookSecret``.
  ``GET /monitors`` and ``GET /monitors/{id}`` omit that secret; the list is
  ``{"data": [...], "hasMore": false, "nextCursor": null}``.
- ``POST /monitors/{id}/trigger`` (200) ``{"triggered": true}``.
- ``GET /monitors/{id}/runs`` (200) paginated run objects (``id/monitorId/
  status/output/failReason/startedAt/completedAt/failedAt/cancelledAt/
  durationMs/createdAt/updatedAt``).
- ``DELETE /monitors/{id}`` (200) returns the monitor object (not 204).

Webhook deliveries are the NESTED event envelope ``{"id": "event_…",
"object": "event", "type": "monitor.run.created" | "monitor.run.completed",
"data": {<RUN>}, "createdAt": …}`` — the run lives under ``data`` (the flat
shape this module originally assumed does not exist on the wire, and there is
no ``newResults`` key in delivered payloads). Run ``output`` is ``null`` while
running; on completion it is ``{"results": [{"id","url","publishedDate",
"title","author?","image?"}], "content": "<answer with [n] markers>",
"grounding": [{"field","citations","confidence"}]}``. Non-terminal events ARE
delivered (``monitor.run.created`` with run ``status: "running"``), so the
inbound route acks any parseable non-terminal status 200 without persisting a
run row (EXA retries non-2xx indefinitely; an unknown-status 422 was an endless
retry loop).

Delivery signature (live-verified 4/4, ``signature-check.txt``): header
``exa-signature: t=<unix>,v1=<hex>`` where ``v1 = HMAC-SHA256(secret,
f"{t}.{body}")`` (hex) and ``secret`` is the PER-MONITOR ``webhookSecret``
(Stripe-style timestamped HMAC); other delivery headers are ``user-agent:
Exa-Webhook/1.0`` and ``content-type: application/json``. EXA's own webhook URL
validator rejects reserved documentation domains (``https://example.com/...`` →
400 ``[webhook.url]: Webhook URL cannot point to localhost, .local domains, or
private IP addresses``) while accepting e.g. ``https://httpbin.org/post``; that
remote rule is EXA's and the stricter landed :func:`validate_delivery` SSRF gate
stays as-is — this adapter documents the difference, it does not relax the gate.

Fail-closed posture (never a silent OSS fallback): a missing API key, any remote
failure, or an untranslatable payload raises :class:`ExaAdapterError` carrying a
stable ``code``:

- ``exa_not_configured`` — no explicit key and no ``EXA_API_KEY``.
- ``exa_api_error`` — any other remote/transport failure.
- ``exa_monitor_not_found`` — delete against a missing remote monitor.
- ``exa_request_invalid`` — local caller input (blank query/schedule/id).
- ``exa_payload_invalid`` — a delivery that is not the pinned nested envelope
  (missing/blank ``type``, missing/non-object ``data``, missing/blank run
  ``status``) or that carries a malformed nested container (present-but-wrong
  ``data.output`` / ``data.output.results``).
- ``exa_run_status_unknown`` — a non-terminal remote run status (e.g.
  ``running``, ``cancelled``) passed to :func:`exa_run_to_monitor_run`; the
  inbound route acks any parseable non-terminal status without persisting.
- ``exa_monitor_id_missing`` — the nested run has no ``monitorId``.
- ``exa_webhook_rejected`` — remote 4xx naming the ``[webhook…]`` field family;
  the message is preserved verbatim.
- ``exa_tier_gated`` — EXA answered 401/403 (paywall / unauthorized class);
  observed only outside the monitors family on this key tier.

Translation (:func:`exa_run_to_monitor_run`): the nested envelope is canonical
and the run is ``exa_payload["data"]``. ``completed`` with a non-empty
``data.output.results`` list is ``ok`` with ``results_all = results_new =
results`` (delivered payloads carry no ``newResults`` split, so nothing is
classified as seen/unchanged and ``changed`` stays 0); ``completed`` with
empty/absent results is ``no_change``; ``failed``/``error`` is ``failed`` with
``failReason`` passed through (``_EXA_RUN_FAILED`` only when it is
missing/blank). Result containers must be lists of objects when present — a
present-but-malformed ``results`` (or a present ``null``) is
``exa_payload_invalid``, never silently coerced to empty: coercing would read
as ``no_change`` and skip delivery. ``costDollars`` is advisory passthrough
when the run carries a mapping, else ``None``. ``backend="exa"`` and
``trigger="exa_webhook"`` are fixed; ``query_snapshot`` records only what the
wire actually carries — ``exa_run_id`` (the run ``id``, never the event id),
``exa_event_type``, and ``exa_monitor_id`` — no invented query fields.

Secret handling (R8 ↔ EXA): EXA returns the one-time 32-char per-monitor
``webhookSecret`` at create and omits it from list/get.
:func:`exa_monitor_secret_from_response` surfaces it without changing
:func:`create_exa_monitor`'s return contract. The inbound route verifies
deliveries with the watch's STORED per-monitor secret
(``MonitorStore.get_delivery_secret``) and fails closed 401
``exa_bad_signature`` when it is missing — no static shared-secret fallback.
The HTTP watch-create path provisions EXA remotely through
``monitors/provisioning.py`` and persists the returned secret at create; the
MCP create surface remains OSS-only (see its docstring).

``create_exa_monitor`` runs the landed :func:`validate_delivery` gate FIRST, so
a webhook EXA would reject (missing, non-https, or private target) fails before
any EXA call is spent; a remote 4xx body naming ``[webhook…]`` is re-raised
with the verbatim message. ``delete_exa_monitor`` is the matching teardown.

The webhook route (``server.py``) resolves the target watch by matching the
nested run's ``monitorId`` against ``Watch.exa_monitor_id`` in the landed store,
then verifies the signature with that watch's stored secret before any
translation or persistence; datatap-scoped watches never match.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx

from digisearch.monitors.delivery import DeliveryConfigError, validate_delivery
from digisearch.monitors.models import DeliveryConfig, DeliveryTarget, MonitorRun
from digisearch.monitors.store import new_ulid
from digisearch.web_exa import EXA_API_BASE, EXA_ENV_VAR, EXA_TIMEOUT_S

__all__ = [
    "ExaAdapterError",
    "create_exa_monitor",
    "delete_exa_monitor",
    "exa_event_is_non_terminal",
    "exa_monitor_id_from_payload",
    "exa_monitor_secret_from_response",
    "exa_run_to_monitor_run",
    "verify_exa_signature",
]

_EXA_MONITORS_PATH = "/monitors"

#: Live-pinned default signature tolerance (symmetric replay window, seconds).
_DEFAULT_SIGNATURE_TOLERANCE_S = 300

_RunStatus = Literal["ok", "no_change", "failed"]

_COMPLETED = "completed"
_FAILED_STATUSES = frozenset({"failed", "error"})

# Stable status text recorded when EXA fails a run without a failReason.
_EXA_RUN_FAILED = "exa_run_failed"

# Default trigger period for the create helper (live-pinned request shape).
_DEFAULT_SCHEDULE = "1d"


class ExaAdapterError(RuntimeError):
    """An EXA adapter failure carrying the stable API-facing ``code``.

    ``code`` is one of the fail-closed codes enumerated in the module
    docstring; ``str(exc)`` is the operator-facing message (verbatim EXA text
    where the remote supplied one).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def verify_exa_signature(
    *, header: str, body: bytes, secret: str, tolerance_s: int = _DEFAULT_SIGNATURE_TOLERANCE_S
) -> bool:
    """Verify an ``exa-signature`` header against the live-pinned HMAC scheme.

    Scheme (live-verified 4/4, 2026-09-16): ``v1 = HMAC-SHA256(secret,
    f"{t}.{body}")`` (hex) where ``secret`` is the per-monitor
    ``webhookSecret`` and ``t`` is unix seconds. ``abs(now - t) > tolerance_s``
    is rejected (replay window). Every malformed or unencodable input returns
    ``False`` — fail closed, never raise into a webhook handler, and never log
    the header or secret.
    """
    if not header or not secret:
        return False
    parts: dict[str, str] = {}
    for segment in header.split(","):
        key, separator, value = segment.partition("=")
        if not separator or not key.strip():
            return False
        parts[key.strip()] = value.strip()
    raw_t = parts.get("t", "")
    presented = parts.get("v1", "")
    if not raw_t or not presented:
        return False
    try:
        timestamp = int(raw_t)
    except ValueError:
        return False
    if abs(time.time() - timestamp) > tolerance_s:
        return False
    try:
        body_text = body.decode()
    except UnicodeDecodeError:
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{body_text}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, presented)


def exa_event_is_non_terminal(exa_payload: dict[str, Any]) -> bool:
    """True when a delivery announces a run that has not finished.

    Non-terminal is defined by exclusion: any parseable run status that is
    neither ``completed`` nor a failed status (``failed``/``error``) — so
    ``running``, ``cancelled``, ``queued``, and any future EXA status are all
    non-terminal, and the inbound route acks them 200 without persisting (EXA
    retries non-2xx, so rejecting an unknown status would retry forever). The
    nested run status is the authoritative signal — an event ``type`` alone
    never suppresses a terminal run. A malformed envelope or missing/blank
    status still fails ``exa_payload_invalid`` (fail closed, 422).
    """
    _, run = _event_envelope(exa_payload)
    return _normalized_status(run) not in {_COMPLETED, *_FAILED_STATUSES}


def exa_run_to_monitor_run(*, watch_id: str, exa_payload: dict[str, Any]) -> MonitorRun:
    """Translate one EXA event delivery into the canonical ``MonitorRun``.

    The NESTED event envelope is canonical (module PIN): the run is
    ``exa_payload["data"]``. Translation and ``dedup_stats`` derivation are
    pinned in the module docstring. Raises :class:`ExaAdapterError`
    (``exa_payload_invalid`` / ``exa_run_status_unknown``) for a payload that
    is not a finished run, and never falls back to an OSS interpretation.
    """
    event_type, run = _event_envelope(exa_payload)
    normalized = _normalized_status(run)
    results = _output_results(run)

    if normalized == _COMPLETED:
        run_status: _RunStatus = "ok" if results else "no_change"
        error: str | None = None
    elif normalized in _FAILED_STATUSES:
        run_status = "failed"
        raw_error = run.get("failReason")
        message = str(raw_error).strip() if raw_error not in (None, "") else ""
        error = message or _EXA_RUN_FAILED
    else:
        raise ExaAdapterError("exa_run_status_unknown", f"Unknown EXA run status: {normalized!r}.")

    # Delivered payloads carry no remote dedup split (`newResults` does not
    # exist on the wire): every surfaced result is new, so seen/unchanged stay 0.
    dedup_stats = {"seen": 0, "new": len(results), "changed": 0, "unchanged": 0}

    now = datetime.now(UTC)
    raw_run_id = run.get("id")
    clean_run_id = raw_run_id.strip() if isinstance(raw_run_id, str) else ""
    run_id = clean_run_id or new_ulid()
    snapshot: dict[str, Any] = {}
    if clean_run_id:
        snapshot["exa_run_id"] = clean_run_id
    snapshot["exa_event_type"] = event_type
    raw_monitor_id = run.get("monitorId")
    if isinstance(raw_monitor_id, str) and raw_monitor_id.strip():
        snapshot["exa_monitor_id"] = raw_monitor_id.strip()

    cost = run.get("costDollars")

    return MonitorRun(
        run_id=run_id,
        watch_id=watch_id,
        backend="exa",
        status=run_status,
        trigger="exa_webhook",
        started_at=_parse_timestamp(run.get("startedAt"))
        or _parse_timestamp(run.get("createdAt"))
        or now,
        finished_at=_parse_timestamp(run.get("completedAt"))
        or _parse_timestamp(run.get("failedAt"))
        or now,
        query_snapshot=snapshot,
        results_all=results,
        results_new=results,
        dedup_stats=dedup_stats,
        cost_dollars=cost if isinstance(cost, dict) else None,
        error=error,
    )


def exa_monitor_id_from_payload(exa_payload: dict[str, Any]) -> str:
    """Return the EXA monitor id a delivery is about (nested, fail closed).

    The route matches this id against stored ``Watch.exa_monitor_id`` values,
    then verifies the delivery with that watch's stored secret; a payload
    without the nested envelope or without a ``monitorId`` cannot be routed and
    must not be guessed at.
    """
    _, run = _event_envelope(exa_payload)
    value = run.get("monitorId")
    if not isinstance(value, str) or not value.strip():
        raise ExaAdapterError(
            "exa_monitor_id_missing",
            "EXA webhook payload has no monitorId — cannot resolve the target watch.",
        )
    return value.strip()


def exa_monitor_secret_from_response(created: dict[str, Any]) -> str | None:
    """Return EXA's one-time per-monitor ``webhookSecret``, else ``None``.

    ``POST /monitors`` returns the secret once; list/get omit it. Callers
    persist it through ``MonitorStore.set_delivery_secret``. This is a read-only
    accessor so :func:`create_exa_monitor`'s return contract stays unchanged.
    """
    secret = created.get("webhookSecret")
    if not isinstance(secret, str) or not secret.strip():
        return None
    return secret.strip()


def create_exa_monitor(
    *,
    query: str,
    webhook_url: str,
    schedule: str = _DEFAULT_SCHEDULE,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create a remote EXA monitor and return EXA's created-monitor document.

    Request/response shapes are live-pinned (module docstring):
    ``validate_delivery`` runs first — a webhook EXA would reject fails before
    any EXA call is spent — then the key is resolved (explicit argument →
    ``EXA_API_KEY`` → fail closed). ``schedule`` is the EXA interval period
    (``"1d"``, ``"7d"``, …). The response's one-time ``webhookSecret`` is
    surfaced by :func:`exa_monitor_secret_from_response`.
    """
    try:
        validate_delivery(
            DeliveryConfig(
                mode="webhook",
                targets=[DeliveryTarget(kind="webhook", url=webhook_url)],
            )
        )
    except DeliveryConfigError as exc:
        raise ExaAdapterError(exc.code, str(exc)) from exc

    clean_query = (query or "").strip()
    if not clean_query:
        raise ExaAdapterError("exa_request_invalid", "query is required.")
    period = (schedule or "").strip()
    if not period:
        raise ExaAdapterError("exa_request_invalid", "schedule is required.")

    key = _resolve_api_key(api_key)
    body = {
        "search": {"query": clean_query},
        "trigger": {"type": "interval", "period": period},
        "webhook": {"url": webhook_url},
    }
    response = _request("POST", _EXA_MONITORS_PATH, api_key=key, json_body=body)
    _check_response(response, context="monitor create")
    try:
        created = response.json()
    except ValueError as exc:
        raise ExaAdapterError("exa_api_error", "EXA monitor create returned non-JSON.") from exc
    if not isinstance(created, dict):
        raise ExaAdapterError("exa_api_error", "EXA monitor create returned an unexpected shape.")
    return created


def delete_exa_monitor(*, exa_monitor_id: str, api_key: str | None = None) -> None:
    """Delete a remote EXA monitor; a missing monitor fails closed.

    Live-pinned: DELETE answers 200 with the monitor object (not 204). Returns
    ``None`` on any 2xx; raises :class:`ExaAdapterError` otherwise.
    """
    monitor = (exa_monitor_id or "").strip()
    if not monitor:
        raise ExaAdapterError("exa_request_invalid", "exa_monitor_id is required.")

    key = _resolve_api_key(api_key)
    path = f"{_EXA_MONITORS_PATH}/{quote(monitor, safe='')}"
    response = _request("DELETE", path, api_key=key)
    if response.status_code == 404:
        raise ExaAdapterError("exa_monitor_not_found", f"EXA monitor not found: {monitor}.")
    _check_response(response, context="monitor delete")


# --- internals ---------------------------------------------------------------------


def _event_envelope(exa_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Unwrap the pinned nested delivery envelope (fail closed).

    Returns ``(type, data)`` where ``data`` is the run object. A payload
    without the envelope — missing/blank/non-string ``type``, or ``data`` that
    is not an object — is shape drift and fails ``exa_payload_invalid``.
    """
    event_type = exa_payload.get("type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ExaAdapterError("exa_payload_invalid", "EXA event payload has no type.")
    data = exa_payload.get("data")
    if not isinstance(data, dict):
        raise ExaAdapterError("exa_payload_invalid", "EXA event payload has no data object.")
    return event_type.strip(), data


def _normalized_status(run: dict[str, Any]) -> str:
    """Read the nested run status; missing/blank is ``exa_payload_invalid``."""
    status = run.get("status")
    if not isinstance(status, str) or not status.strip():
        raise ExaAdapterError("exa_payload_invalid", "EXA run payload has no status.")
    return status.strip().lower()


def _output_results(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the pinned ``data.output.results``: null/absent → empty, else strict.

    ``output`` is ``null`` while a run is running and on failures; a
    present-but-malformed container is shape drift and must fail closed:
    coercing it to ``[]`` would read as ``no_change`` and silently skip
    delivery.
    """
    output = run.get("output")
    if output is None:
        return []
    if not isinstance(output, dict):
        raise ExaAdapterError("exa_payload_invalid", "EXA run output must be an object.")
    if "results" not in output:
        return []
    results = output["results"]
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise ExaAdapterError(
            "exa_payload_invalid",
            "EXA run output field 'results' must be a list of objects.",
        )
    return list(results)


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an EXA ISO timestamp; ``None`` for missing/unparseable values."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _resolve_api_key(api_key: str | None) -> str:
    """Explicit argument → ``EXA_API_KEY`` env → fail closed (never OSS)."""
    key = (api_key or os.environ.get(EXA_ENV_VAR, "")).strip()
    if not key:
        raise ExaAdapterError(
            "exa_not_configured",
            f"{EXA_ENV_VAR} is not set — the EXA monitor backend is disabled. "
            f"Set {EXA_ENV_VAR} to enable it.",
        )
    return key


def _client_for() -> httpx.Client:
    """httpx client factory (test seam): bounded timeout, no redirects."""
    return httpx.Client(timeout=EXA_TIMEOUT_S, follow_redirects=False)


def _request(
    method: str, path: str, *, api_key: str, json_body: dict[str, Any] | None = None
) -> httpx.Response:
    """Send one EXA request; transport failures fail closed as ``exa_api_error``."""
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    try:
        with _client_for() as client:
            return client.request(method, f"{EXA_API_BASE}{path}", json=json_body, headers=headers)
    except httpx.HTTPError as exc:
        raise ExaAdapterError("exa_api_error", f"EXA request failed: {exc}") from exc


def _check_response(response: httpx.Response, *, context: str) -> None:
    """Map a non-2xx EXA response to the fail-closed error vocabulary."""
    if response.is_success:
        return
    status = response.status_code
    body = response.text.strip()
    if status in (401, 403):
        detail = f": {body}" if body else ""
        raise ExaAdapterError(
            "exa_tier_gated",
            f"EXA monitors are tier-gated on this key (HTTP {status}){detail}",
        )
    if 400 <= status < 500 and "[webhook" in body:
        # EXA's webhook-field validation family: ``[webhook]: Required``,
        # ``[webhook.url]: ...localhost, .local domains...``. Preserved verbatim.
        raise ExaAdapterError("exa_webhook_rejected", body)
    raise ExaAdapterError("exa_api_error", f"EXA {context} failed (HTTP {status}): {body[:500]}")
