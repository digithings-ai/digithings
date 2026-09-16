"""Watch creation with fail-closed remote EXA provisioning (#4184, #4065).

The HTTP create route delegates here so the OSS path stays byte-for-byte what
it always was while ``backend="exa"`` watches are provisioned REMOTE FIRST:

- ``backend="oss"`` (default): local mint — ``store.create_watch`` then a
  server-generated ``secrets.token_hex(32)`` delivery secret. No adapter call.
- ``backend="exa"``: the remote monitor is created before anything is
  persisted, because EXA returns the per-monitor ``webhookSecret`` exactly once
  and only at create. Order: schedule/period/webhook-target validation → remote
  ``create_exa_monitor`` → require a non-blank ``webhookSecret`` and ``id``
  (best-effort remote delete on either miss) → persist the watch with
  ``exa_monitor_id`` + the REMOTE secret → return both. A local persist failure
  is compensated by deleting the just-created remote monitor and the original
  error is re-raised, so a broken store can never leave an orphan monitor.

Failures surface as :class:`WatchProvisioningError` (``status_code`` + stable
``code``) which the route renders through the shared monitor error envelope.
``ExaAdapterError`` is mapped deterministically: ``exa_request_invalid`` (local
caller input) → 422, any other adapter failure → 502 ``exa_api_error``.
"""

from __future__ import annotations

import logging
import secrets

from digisearch.monitors.exa_adapter import (
    ExaAdapterError,
    create_exa_monitor,
    delete_exa_monitor,
    exa_monitor_secret_from_response,
)
from digisearch.monitors.models import Watch
from digisearch.monitors.store import MonitorStore

__all__ = ["WatchProvisioningError", "create_watch_provisioned"]

logger = logging.getLogger(__name__)

_HTTP_UNPROCESSABLE = 422
_HTTP_BAD_GATEWAY = 502

_SECONDS_PER_DAY = 86400
_SECONDS_PER_HOUR = 3600
_SECONDS_PER_MINUTE = 60

# EXA interval units, largest first: exact divisibility only (never round).
_PERIOD_UNITS = (
    (_SECONDS_PER_DAY, "d"),
    (_SECONDS_PER_HOUR, "h"),
    (_SECONDS_PER_MINUTE, "m"),
)


class WatchProvisioningError(RuntimeError):
    """A create-path failure carrying its API-facing ``status_code`` and ``code``."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def create_watch_provisioned(
    store: MonitorStore, watch: Watch, *, api_key: str | None = None
) -> tuple[Watch, str]:
    """Create *watch*, provisioning a remote EXA monitor when ``backend="exa"``.

    Returns ``(created_watch, delivery_secret)``. On the OSS path the secret is
    a locally minted ``secrets.token_hex(32)``; on the EXA path it is the
    remote monitor's one-time ``webhookSecret``, persisted with the watch.
    """
    if watch.backend == "exa":
        return _create_exa_watch(store, watch, api_key=api_key)
    created = store.create_watch(watch)
    secret = secrets.token_hex(32)
    store.set_delivery_secret(created.watch_id, secret)
    return created, secret


def _create_exa_watch(
    store: MonitorStore, watch: Watch, *, api_key: str | None
) -> tuple[Watch, str]:
    """Remote-first EXA provisioning (see module docstring for the ordering)."""
    if watch.schedule.mode == "cron":
        raise WatchProvisioningError(
            _HTTP_UNPROCESSABLE,
            "exa_schedule_unsupported",
            "EXA interval triggers cannot express a cron schedule; "
            "use mode='interval' with a supported interval_seconds.",
        )
    webhook_url = _webhook_target_url(watch)
    period = _exa_period(watch.schedule.interval_seconds)

    try:
        created_remote = create_exa_monitor(
            query=watch.query,
            webhook_url=webhook_url,
            schedule=period,
            api_key=api_key,
        )
    except ExaAdapterError as exc:
        if exc.code == "exa_request_invalid":
            raise WatchProvisioningError(_HTTP_UNPROCESSABLE, exc.code, str(exc)) from exc
        raise WatchProvisioningError(_HTTP_BAD_GATEWAY, "exa_api_error", str(exc)) from exc

    monitor_id = _non_blank_string(created_remote.get("id"))
    secret = exa_monitor_secret_from_response(created_remote)
    if secret is None:
        _compensate(exa_monitor_id=monitor_id, api_key=api_key)
        raise WatchProvisioningError(
            _HTTP_BAD_GATEWAY,
            "exa_webhook_secret_missing",
            "EXA monitor create returned no webhookSecret; the delivery cannot be verified.",
        )
    if monitor_id is None:
        raise WatchProvisioningError(
            _HTTP_BAD_GATEWAY,
            "exa_monitor_id_missing",
            "EXA monitor create returned no id; the watch cannot be linked to the monitor.",
        )

    try:
        created = store.create_watch(watch.model_copy(update={"exa_monitor_id": monitor_id}))
        store.set_delivery_secret(created.watch_id, secret)
    except Exception:
        _compensate(exa_monitor_id=monitor_id, api_key=api_key)
        raise
    return created, secret


def _webhook_target_url(watch: Watch) -> str:
    """First deliverable webhook target URL, else 422 ``exa_webhook_target_missing``."""
    for target in watch.delivery.targets:
        if target.kind != "webhook":
            continue
        url = _non_blank_string(target.url)
        if url is not None:
            return url
    raise WatchProvisioningError(
        _HTTP_UNPROCESSABLE,
        "exa_webhook_target_missing",
        "EXA watches need a delivery webhook target; EXA returns the per-monitor "
        "webhookSecret only for a remote monitor with a webhook URL.",
    )


def _exa_period(interval_seconds: int | None) -> str:
    """Map ``interval_seconds`` to an EXA interval period by exact divisibility.

    ``86400`` → ``"1d"``, ``3600`` → ``"1h"``, ``7200`` → ``"2h"``, ``120`` →
    ``"2m"``. Anything not evenly divisible by a supported unit (``90``, ``61``)
    is ``exa_schedule_unsupported`` — EXA periods are exact units only, never
    rounded.
    """
    if interval_seconds is None or interval_seconds <= 0:
        raise WatchProvisioningError(
            _HTTP_UNPROCESSABLE,
            "exa_schedule_unsupported",
            "EXA watches need an interval schedule (interval_seconds).",
        )
    for unit_seconds, suffix in _PERIOD_UNITS:
        if interval_seconds % unit_seconds == 0:
            return f"{interval_seconds // unit_seconds}{suffix}"
    raise WatchProvisioningError(
        _HTTP_UNPROCESSABLE,
        "exa_schedule_unsupported",
        f"interval_seconds={interval_seconds} is not an exact EXA period unit "
        "(days, hours, or minutes).",
    )


def _non_blank_string(value: object) -> str | None:
    """Strip a value that is a string, else ``None`` (never coerce)."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _compensate(*, exa_monitor_id: str | None, api_key: str | None) -> None:
    """Best-effort remote delete; never mask the failure being compensated."""
    if not exa_monitor_id:
        return
    try:
        delete_exa_monitor(exa_monitor_id=exa_monitor_id, api_key=api_key)
    except Exception:
        logger.warning(
            "failed to delete orphaned EXA monitor %s during compensation",
            exa_monitor_id,
            exc_info=True,
        )
