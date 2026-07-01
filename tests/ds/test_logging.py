"""Tests for DigiSearch structured JSON logging (#215)."""

from __future__ import annotations

import io
import json
import logging

import pytest

from digibase.http import _REQUEST_ID_CTX  # type: ignore[attr-defined]
from digisearch.logging import _HANDLER_MARKER, configure_logging

pytestmark = pytest.mark.unit


def _digi_handler() -> logging.Handler | None:
    for h in logging.getLogger().handlers:
        if getattr(h, _HANDLER_MARKER, False):
            return h
    return None


def _swap_to_stream(stream: io.StringIO) -> None:
    """Point the installed DigiSearch JSON handler at *stream* for capture."""
    h = _digi_handler()
    assert h is not None, "configure_logging() must install the DigiSearch JSON handler"
    h.stream = stream  # type: ignore[attr-defined]


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    configure_logging()
    configure_logging()
    handlers = [h for h in logging.getLogger().handlers if getattr(h, _HANDLER_MARKER, False)]
    assert len(handlers) == 1, "re-calling configure_logging() must not stack handlers"


def test_emits_valid_json_with_required_keys() -> None:
    configure_logging()
    buf = io.StringIO()
    _swap_to_stream(buf)

    logging.getLogger("digisearch.test").info(
        "chunk done",
        extra={"operation": "chunk_fixed", "duration_ms": 7, "outcome": "ok"},
    )
    _digi_handler().flush()  # type: ignore[union-attr]

    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    for key in (
        "timestamp",
        "level",
        "service",
        "request_id",
        "operation",
        "duration_ms",
        "outcome",
    ):
        assert key in payload, f"missing required key {key!r}: {payload}"
    assert payload["service"] == "digisearch"
    assert payload["level"] == "INFO"
    assert payload["operation"] == "chunk_fixed"
    assert payload["duration_ms"] == 7
    assert payload["outcome"] == "ok"


def test_request_id_defaults_to_dash_outside_request() -> None:
    configure_logging()
    buf = io.StringIO()
    _swap_to_stream(buf)

    # Make sure we aren't inside a request context.
    token = _REQUEST_ID_CTX.set("")
    try:
        logging.getLogger("digisearch.test").info(
            "bare", extra={"operation": "x", "duration_ms": 0, "outcome": "ok"}
        )
    finally:
        _REQUEST_ID_CTX.reset(token)
    _digi_handler().flush()  # type: ignore[union-attr]

    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert payload["request_id"] == "-"


def test_request_id_flows_from_context() -> None:
    configure_logging()
    buf = io.StringIO()
    _swap_to_stream(buf)

    token = _REQUEST_ID_CTX.set("req-abc-123")
    try:
        logging.getLogger("digisearch.test").info(
            "in-request",
            extra={"operation": "query_index", "duration_ms": 12, "outcome": "ok"},
        )
    finally:
        _REQUEST_ID_CTX.reset(token)
    _digi_handler().flush()  # type: ignore[union-attr]

    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert payload["request_id"] == "req-abc-123"


def test_hot_path_logs_do_not_leak_user_content() -> None:
    """Running actual hot paths must never echo raw query or doc bodies."""
    configure_logging()
    buf = io.StringIO()
    _swap_to_stream(buf)

    from digisearch.ingestion.chunkers.fixed import FixedSizeChunker
    from digisearch.ingestion.parsers.plaintext import PlainTextParser

    secret_query = "SECRET_USER_QUERY_PATTERN_4242"
    secret_body = "SECRET_DOC_BODY_CONTENT_9999 " * 20
    doc = PlainTextParser().parse(secret_body.encode("utf-8"))
    chunks = FixedSizeChunker(chunk_size=64).chunk(doc)
    assert len(chunks) > 0

    # Also exercise the keyword searcher — the other main PII source.
    try:
        from digisearch.core.models import Query
        from digisearch.search.keyword import TFIDFSearcher

        TFIDFSearcher(["alpha beta gamma"]).search(Query(text=secret_query, top_k=3))
    except Exception:
        pass  # non-fatal — we're only checking logs

    _digi_handler().flush()  # type: ignore[union-attr]
    raw = buf.getvalue()
    assert raw, "hot paths emitted no logs"
    assert secret_query not in raw, "INFO log leaked user query"
    assert "SECRET_DOC_BODY_CONTENT" not in raw, "INFO log leaked document body"


def test_error_outcome_on_exception() -> None:
    configure_logging()
    buf = io.StringIO()
    _swap_to_stream(buf)

    log = logging.getLogger("digisearch.test")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception(
            "op failed",
            extra={"operation": "embed_batch", "duration_ms": 3, "outcome": "error"},
        )
    _digi_handler().flush()  # type: ignore[union-attr]

    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert payload["outcome"] == "error"
    assert payload["level"] == "ERROR"
