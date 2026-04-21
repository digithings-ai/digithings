"""Structured JSON logging for DigiSearch.

Single source of truth for the process-wide logging config. Every entrypoint
(:mod:`digisearch.server`, :mod:`digisearch.mcp_server`, :mod:`digisearch.ingest_worker`)
calls :func:`configure_logging` at startup so that operators get the same shape
on stdout regardless of how DigiSearch is invoked.

Record shape (all keys present on every INFO/WARNING/ERROR record):

* ``timestamp`` — ISO-ish ``asctime`` (renamed from ``%(asctime)s``).
* ``level`` — ``INFO`` / ``WARNING`` / ``ERROR`` (renamed from ``levelname``).
* ``service`` — always ``"digisearch"`` (injected by :class:`_ServiceFilter`).
* ``request_id`` — value from :mod:`digibase.http` ``X-Request-ID`` ContextVar,
  or ``"-"`` outside a request. Provided by ``install_request_id_logging`` (#213).
* ``operation`` — set by call sites via ``extra={"operation": ...}``.
* ``duration_ms`` — set by call sites; integer milliseconds.
* ``outcome`` — ``"ok"`` or ``"error"``; set by call sites.
* ``name`` — logger name (module).
* ``message`` — human-readable summary (no raw user queries or doc bodies).

Config:

* Level from ``DIGI_LOG_LEVEL`` (default ``INFO``). Accepts standard names.
* Idempotent — safe to call on hot-reload; only the DigiSearch JSON handler is
  replaced, other test/framework handlers (e.g. pytest's ``caplog``) are kept.
"""

from __future__ import annotations

import logging
import os

from digibase.http import RequestIdLogFilter, install_request_id_logging
from pythonjsonlogger import jsonlogger

_SERVICE = "digisearch"
_HANDLER_MARKER = "_digi_json_handler"


class _ServiceFilter(logging.Filter):
    """Stamp every record with ``service='digisearch'`` so the JSON formatter has it."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        record.service = _SERVICE
        return True


def _build_formatter() -> jsonlogger.JsonFormatter:
    """JSON formatter emitting the fields required by #215's acceptance criteria."""
    fmt = (
        "%(asctime)s %(levelname)s %(name)s %(service)s %(request_id)s "
        "%(operation)s %(duration_ms)s %(outcome)s %(message)s"
    )
    return jsonlogger.JsonFormatter(
        fmt,
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )


def configure_logging() -> None:
    """Install the DigiSearch JSON handler + request-id filter on the root logger.

    Idempotent. Re-entrant calls replace only the DigiSearch handler so tests
    that use ``caplog`` (which adds its own handler) remain functional.
    """
    level_name = os.environ.get("DIGI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove only our previous handler, if any — leave pytest/caplog alone.
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)

    handler = logging.StreamHandler()
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(_build_formatter())
    # Attach filters to the handler, not the logger: logger-level filters only
    # run for records *originated* on that logger, so filters on the root
    # logger wouldn't fire for records from child loggers. Handler-level
    # filters run for every record that reaches the handler.
    handler.addFilter(_ServiceFilter())
    handler.addFilter(RequestIdLogFilter())
    root.addHandler(handler)

    # Also attach the request-id filter to the root logger itself so other
    # handlers (e.g. pytest's caplog, OTel bridges) can reference
    # ``%(request_id)s`` without KeyError.
    install_request_id_logging(root)


__all__ = ["configure_logging"]
