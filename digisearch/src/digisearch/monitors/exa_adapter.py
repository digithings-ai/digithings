# score:allow untyped any
# EXA payloads are dynamic remote JSON; Any is the honest annotation.
"""Phase C EXA monitor adapter — EXPERIMENTAL, tier-gated, fail closed (#4065, Task 8c).

EXPERIMENTAL — NOT LIVE-VALIDATED. The remote shapes used here are derived from
observed EXA docs/error strings (2026-09-14), not from a live probe: the Task 8a
spike was deferred because the operator's key tier observably rejects the
monitor/websets family (paywall 401, the "Upgrade to a Pro plan" class). The
create request shape (``search`` / ``trigger`` / ``webhook``), the run payload
fields (``id`` / ``monitorId`` / ``status`` / ``createdAt`` / ``completedAt`` /
``results`` / ``newResults``), and the observed validation messages (``[webhook]:
Required``, ``[webhook.url]: ...localhost...``) are therefore provisional. A
live-pin follow-up issue (#4123) tracks validation and reconciliation; there
is deliberately no ``# PIN`` record in this docstring — the follow-up owns it,
and nothing here may be treated as frozen.

Fail-closed posture (never a silent OSS fallback): a missing API key, a
tier-gated key (401/403), any other remote failure, or an untranslatable
payload raises :class:`ExaAdapterError` carrying a stable ``code``:

- ``exa_not_configured`` — no explicit key and no ``EXA_API_KEY``.
- ``exa_tier_gated`` — EXA answered 401/403 (paywall / unauthorized class).
- ``exa_webhook_rejected`` — remote 4xx naming the ``[webhook…]`` field family;
  the message is preserved verbatim.
- ``exa_api_error`` — any other remote/transport failure.
- ``exa_monitor_not_found`` — delete against a missing remote monitor.
- ``exa_request_invalid`` — local caller input (blank query/schedule/id).
- ``exa_payload_invalid`` — untranslatable webhook payload (missing/blank
  ``status``, or a malformed ``results``/``newResults`` container);
  ``exa_run_status_unknown`` — a non-terminal remote status.
- ``exa_monitor_id_missing`` — webhook payload without a ``monitorId``.

One integration gap is deliberately not papered over: EXA returns a one-time
per-monitor ``webhookSecret`` that signs its deliveries, while the landed
inbound route compares the static shared ``EXA_MONITOR_WEBHOOK_SECRET``. The
adapter returns EXA's created document untouched (nothing persists the remote
secret yet); reconciling the two is the live-pin follow-up's call, not a silent
guess here.

Translation (``exa_run_to_monitor_run``): a ``completed`` payload with a
non-empty ``newResults`` list is ``ok``; ``completed`` with empty/absent
``newResults`` is ``no_change``; ``failed``/``error`` is ``failed`` with the
payload ``error`` passed through. Result containers must be lists of objects
when present: a present-but-malformed container (or a present ``null``) is
``exa_payload_invalid``, never silently coerced to empty — coercing would read
as ``no_change`` and skip delivery. ``dedup_stats`` reflects EXA's remote dedup
over ``len(results)`` vs ``len(newResults)``: ``new`` counts ``newResults`` and
``seen``/``unchanged`` count the remote-filtered remainder (clamped at 0),
while ``changed`` stays 0 — EXA reports only new-vs-already-seen, never a
changed bucket. ``costDollars`` is advisory passthrough when it is a mapping,
else ``None``. ``backend="exa"`` and ``trigger="exa_webhook"`` are fixed; EXA's
own run fields (``id``, ``trigger``) are preserved in ``run_id`` /
``query_snapshot``.

``create_exa_monitor`` runs the landed :func:`validate_delivery` gate FIRST, so
a webhook EXA would reject (missing, non-https, or private target) fails before
any EXA call is spent; a remote 4xx body naming ``[webhook…]`` is re-raised
with the verbatim message. ``delete_exa_monitor`` is the matching teardown.

The webhook route (``server.py``) resolves the target watch by matching the
payload's ``monitorId`` against ``Watch.exa_monitor_id`` in the landed store —
the minimal derivation that needs no new store API; ambiguity (two watches
sharing one remote id) resolves newest-updated first and the follow-up pin can
tighten it.
"""

from __future__ import annotations

import os
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
    "exa_monitor_id_from_payload",
    "exa_run_to_monitor_run",
]

_EXA_MONITORS_PATH = "/monitors"

_RunStatus = Literal["ok", "no_change", "failed"]

_COMPLETED = "completed"
_FAILED_STATUSES = frozenset({"failed", "error"})

# Stable status text recorded when EXA fails a run without an error message.
_EXA_RUN_FAILED = "exa_run_failed"

# Default trigger period for the EXPERIMENTAL create helper (see docstring).
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


def exa_run_to_monitor_run(*, watch_id: str, exa_payload: dict[str, Any]) -> MonitorRun:
    """Translate one EXA run payload into the canonical ``MonitorRun`` envelope.

    Translation table and ``dedup_stats`` derivation are pinned in the module
    docstring. Raises :class:`ExaAdapterError` (``exa_payload_invalid`` /
    ``exa_run_status_unknown``) for a payload that is not a finished run, and
    never falls back to an OSS interpretation.
    """
    status = exa_payload.get("status")
    if not isinstance(status, str) or not status.strip():
        raise ExaAdapterError("exa_payload_invalid", "EXA run payload has no status.")
    normalized = status.strip().lower()

    results_all = _result_dicts(exa_payload, "results")
    results_new = _result_dicts(exa_payload, "newResults")

    if normalized == _COMPLETED:
        run_status: _RunStatus = "ok" if results_new else "no_change"
        error: str | None = None
    elif normalized in _FAILED_STATUSES:
        run_status = "failed"
        raw_error = exa_payload.get("error")
        error = str(raw_error) if raw_error not in (None, "") else _EXA_RUN_FAILED
    else:
        raise ExaAdapterError("exa_run_status_unknown", f"Unknown EXA run status: {status!r}.")

    # EXA dedups remotely: `results` is what the run saw, `newResults` is what
    # survived. seen/unchanged share the filtered remainder (OSS semantics let
    # a seen result be counted in both); there is no changed bucket remotely.
    filtered = max(0, len(results_all) - len(results_new))
    dedup_stats = {"seen": filtered, "new": len(results_new), "changed": 0, "unchanged": filtered}

    now = datetime.now(UTC)
    raw_run_id = exa_payload.get("id")
    snapshot: dict[str, Any] = {"query": str(exa_payload.get("query") or "")}
    if isinstance(raw_run_id, str) and raw_run_id.strip():
        snapshot["exa_run_id"] = raw_run_id
    exa_trigger = exa_payload.get("trigger")
    if isinstance(exa_trigger, str) and exa_trigger.strip():
        snapshot["exa_trigger"] = exa_trigger

    cost = exa_payload.get("costDollars")
    run_id = (
        str(raw_run_id).strip()
        if isinstance(raw_run_id, str) and raw_run_id.strip()
        else new_ulid()
    )

    return MonitorRun(
        run_id=run_id,
        watch_id=watch_id,
        backend="exa",
        status=run_status,
        trigger="exa_webhook",
        started_at=_parse_timestamp(exa_payload.get("createdAt")) or now,
        finished_at=_parse_timestamp(exa_payload.get("completedAt")) or now,
        query_snapshot=snapshot,
        results_all=results_all,
        results_new=results_new,
        dedup_stats=dedup_stats,
        cost_dollars=cost if isinstance(cost, dict) else None,
        error=error,
    )


def exa_monitor_id_from_payload(exa_payload: dict[str, Any]) -> str:
    """Return the EXA monitor id a webhook delivery is about (fail closed).

    The route matches this id against stored ``Watch.exa_monitor_id`` values;
    a payload without one cannot be routed and must not be guessed at.
    """
    value = exa_payload.get("monitorId")
    if not isinstance(value, str) or not value.strip():
        raise ExaAdapterError(
            "exa_monitor_id_missing",
            "EXA webhook payload has no monitorId — cannot resolve the target watch.",
        )
    return value.strip()


def create_exa_monitor(
    *,
    query: str,
    webhook_url: str,
    schedule: str = _DEFAULT_SCHEDULE,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create a remote EXA monitor and return EXA's created-monitor document.

    EXPERIMENTAL: request/response shapes are provisional (see module
    docstring). ``validate_delivery`` runs first — a webhook EXA would reject
    fails before any EXA call is spent — then the key is resolved (explicit
    argument → ``EXA_API_KEY`` → fail closed). ``schedule`` is the EXA interval
    period (``"1d"``, ``"7d"``, …).
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

    EXPERIMENTAL: shapes are provisional (see module docstring). Returns
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


def _result_dicts(exa_payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Read a result container: absent → empty, present-but-malformed → error.

    An absent key is the brief-pinned "no results" case. A present container
    that is not a list of objects is shape drift and must fail closed:
    coercing it to ``[]`` would read as ``no_change`` and silently skip
    delivery, contradicting the module's fail-closed posture.
    """
    if field not in exa_payload:
        return []
    value = exa_payload[field]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ExaAdapterError(
            "exa_payload_invalid",
            f"EXA run payload field {field!r} must be a list of objects.",
        )
    return list(value)


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
        # ``[webhook.url]: ...localhost...``. Preserved verbatim.
        raise ExaAdapterError("exa_webhook_rejected", body)
    raise ExaAdapterError("exa_api_error", f"EXA {context} failed (HTTP {status}): {body[:500]}")
