"""Research retrieval retries disconnect / PGRST002 / 502 (#3299)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from digiquant.olympus.research_retrieval.queries import query_research

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit


class _FlakyDocuments:
    def __init__(self, inner: FakeSupabaseClient, *, fails: int, err: Exception) -> None:
        self._inner = inner
        self._fails = fails
        self._err = err
        self.calls = 0

    def table(self, name: str) -> object:
        if name != "documents":
            return self._inner.table(name)
        query = self._inner.table(name)
        original = query.execute

        def execute() -> object:
            self.calls += 1
            if self.calls <= self._fails:
                raise self._err
            return original()

        query.execute = execute  # type: ignore[method-assign]
        return query


def test_query_research_retries_pgrst002_then_succeeds() -> None:
    inner = FakeSupabaseClient(
        canned_reads={
            "documents": [
                {
                    "date": "2026-08-29",
                    "document_key": "macro",
                    "payload": {"headline": "ok"},
                }
            ]
        }
    )
    client = _FlakyDocuments(
        inner,
        fails=2,
        err=RuntimeError("PGRST002: Could not query the database for the schema cache."),
    )
    with patch("digiquant.olympus.transient.time.sleep"):
        out = query_research(
            client,  # type: ignore[arg-type]
            run_date=date(2026, 8, 29),
            document_key="macro",
            as_of_date=date(2026, 8, 29),
        )
    assert out["payload"]["headline"] == "ok"
    assert client.calls == 3


def test_query_research_returns_error_after_retries_fail() -> None:
    inner = FakeSupabaseClient(canned_reads={"documents": []})
    client = _FlakyDocuments(
        inner,
        fails=5,
        err=ConnectionError("Server disconnected"),
    )
    with patch("digiquant.olympus.transient.time.sleep"):
        out = query_research(
            client,  # type: ignore[arg-type]
            run_date=date(2026, 8, 29),
            document_key="macro",
            as_of_date=date(2026, 8, 29),
        )
    assert "error" in out
    assert "Server disconnected" in out["error"]
    assert client.calls == 3
