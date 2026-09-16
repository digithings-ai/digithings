"""Watch create/update validation shared by the HTTP API and MCP surfaces (#4065).

Extracted from the Task 6 HTTP gate so both surfaces share one decision: the
HTTP create/patch routes and the Task 7 MCP ``monitors_create_watch`` tool call
this module. The gate must run before persistence on every surface: a watch
whose cron does not parse, or whose timezone is unknown, makes ``is_due`` raise
at tick time — and ``tick_due_watches`` deliberately isolates and swallows
per-watch failures (``runner.py``), so such a watch would silently never run.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from digiclaw.cron import parse_cron

from digisearch.monitors.delivery import DeliveryConfigError, validate_delivery
from digisearch.monitors.models import Watch

_HTTP_UNPROCESSABLE = 422

# §5: monitors are OFF end-to-end for the datatap workspace.
DATATAP_WORKSPACE_ID = "datatap"

__all__ = ["DATATAP_WORKSPACE_ID", "watch_config_error"]


def watch_config_error(watch: Watch) -> tuple[int, str, str] | None:
    """Return ``(status_code, code, message)`` for the first violation, else ``None``.

    Checks run in the §4.6 order: datatap workspace off, EXA-local-only options,
    known timezone, parseable cron, deliverable delivery config. HTTP callers
    render the tuple through the shared error envelope; MCP callers flatten it
    into their text convention — both surfaces share this one decision.
    """
    if watch.workspace_id == DATATAP_WORKSPACE_ID:
        return (
            _HTTP_UNPROCESSABLE,
            "datatap_monitors_disabled",
            "Monitors are disabled for the datatap workspace.",
        )
    if watch.backend == "exa" and watch.bridge is not None:
        # EXA watches are remote monitors translated by the webhook adapter;
        # run_watch (the handoff's only caller) never runs them (#4249).
        return (
            _HTTP_UNPROCESSABLE,
            "bridge_exa_unsupported",
            "bridge is OSS-local-only: backend='exa' watches run remote EXA monitors.",
        )
    try:
        ZoneInfo(watch.schedule.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return (
            _HTTP_UNPROCESSABLE,
            "timezone_unknown",
            f"Unknown timezone: {watch.schedule.timezone!r}",
        )
    if watch.schedule.mode == "cron" and watch.schedule.cron:
        try:
            parse_cron(watch.schedule.cron)
        except ValueError:
            # CronParseError subclasses ValueError; the parser also raises a bare
            # ValueError on non-numeric step tokens. Both map to the same 422.
            return (
                _HTTP_UNPROCESSABLE,
                "invalid_cron",
                f"Invalid cron expression: {watch.schedule.cron!r}",
            )
    try:
        validate_delivery(watch.delivery)
    except DeliveryConfigError as exc:
        return (_HTTP_UNPROCESSABLE, exc.code, str(exc))
    return None
