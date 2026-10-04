"""Unseeded-corpus guard: a corpus that failed to embed must not read as a miss.

#5045. The Chroma seed silently succeeded on an empty corpus because
``digisearch ingest`` exited 0 even when every file failed to embed (fixed in
``af8ab96eb``). ``container/seed_chroma.sh`` now records the failed index names
and ``container/start_digisearch.sh`` exports them as
``DIGISEARCH_UNSEEDED_INDEXES``; ``digisearch.search._stub.guard_unseeded``
turns a query against one of those indexes into an explicit
``CorpusNotSeededError`` rather than a confident empty answer.

Covered here:
  * ``guard_unseeded`` intersection semantics (a partial failure stays scoped).
  * ``unseeded_indexes`` reads the env per call, so it is not import-cached.
  * ``/health`` reports ``degraded`` while unseeded; ``/healthz`` stays ``ok``.
  * ``POST /query`` answers 503 rather than an empty result list.
  * ``/v1/orchestrator_invoke`` answers ``ok=False`` — the shape digigraph's
    ``digisearch_tools.py`` already branches on — rather than a 500.
"""

from __future__ import annotations

import pytest
from digisearch.core.models import Chunk, Query
from digisearch.indexes.backends.backend_errors import CorpusNotSeededError
from digisearch.search import _stub as stub
from digisearch.search import add_chunks
from digisearch.search._stub import guard_unseeded, query_index, unseeded_indexes
from digisearch.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

ENV = "DIGISEARCH_UNSEEDED_INDEXES"

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _offline_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin every query to the in-memory stub — no Chroma, no Vectorize, no state bleed."""
    for name in ("CHROMA_PATH", "CHROMA_HOST", "DIGISEARCH_EMBEDDING_PROVIDER", ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    stub._stub_index.clear()


def _seed_stub(*indexes: str) -> None:
    """Add one real chunk to each named in-memory stub index."""
    for index in indexes:
        add_chunks(
            index,
            [
                Chunk(
                    id=f"{index}-1",
                    content="Quarantäne-Nachrichten werden über die OCC-Hilfe freigegeben.",
                    doc_id=f"{index}-doc",
                    embedding=None,
                    metadata={"title": f"{index} faq", "path": f"{index}.md"},
                )
            ],
        )


def _client() -> TestClient:
    return TestClient(app, headers=auth_headers())


# ── guard_unseeded ────────────────────────────────────────────────────────────


def test_guard_inert_when_env_unset() -> None:
    """No marker (local compose, bare process) must leave behaviour untouched."""
    assert unseeded_indexes() == frozenset()
    guard_unseeded(["occ_help", "occ_tickets"])  # must not raise


@pytest.mark.parametrize("raw", ["occ_tickets", " occ_tickets ", "occ_tickets,", ",occ_tickets"])
def test_env_is_parsed_and_tolerates_padding(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv(ENV, raw)
    assert unseeded_indexes() == frozenset({"occ_tickets"})


def test_env_reads_multiple_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, "occ_help,occ_tickets")
    assert unseeded_indexes() == frozenset({"occ_help", "occ_tickets"})


def test_guard_raises_naming_only_the_unseeded_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial failure must not condemn a healthy sibling corpus."""
    monkeypatch.setenv(ENV, "occ_tickets")
    guard_unseeded(["occ_help"])  # healthy → must not raise

    with pytest.raises(CorpusNotSeededError) as excinfo:
        guard_unseeded(["occ_help", "occ_tickets"])
    assert excinfo.value.indexes == ["occ_tickets"]


def test_guard_raises_on_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, "occ_help")
    with pytest.raises(CorpusNotSeededError) as excinfo:
        guard_unseeded(["occ_help"])
    assert excinfo.value.indexes == ["occ_help"]


def test_env_is_not_import_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A later boot that succeeds must be able to clear the marker."""
    monkeypatch.setenv(ENV, "occ_tickets")
    assert unseeded_indexes() == frozenset({"occ_tickets"})
    monkeypatch.setenv(ENV, "")
    assert unseeded_indexes() == frozenset()


# ── query_index fan-out ───────────────────────────────────────────────────────


def test_fanout_query_errors_when_one_index_unseeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fan-out split means a comma list reaches the guard as one call."""
    _seed_stub("occ_help", "occ_tickets")
    monkeypatch.setenv(ENV, "occ_tickets")

    with pytest.raises(CorpusNotSeededError) as excinfo:
        query_index(Query(text="Quarantäne-Nachricht freigeben"), "occ_help,occ_tickets")
    assert excinfo.value.indexes == ["occ_tickets"]


def test_fanout_query_succeeds_when_all_seeded() -> None:
    _seed_stub("occ_help", "occ_tickets")
    resp = query_index(Query(text="Quarantäne"), "occ_help,occ_tickets")
    assert resp.results


# ── /health + /healthz ────────────────────────────────────────────────────────


def test_health_degraded_while_unseeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, "occ_tickets")
    body = _client().get("/health").json()
    assert body["status"] == "degraded"
    assert body["unseeded_indexes"] == ["occ_tickets"]


def test_health_ok_and_omits_index_list_when_seeded() -> None:
    body = _client().get("/health").json()
    assert body["status"] == "ok"
    assert "unseeded_indexes" not in body


def test_healthz_stays_ok_while_unseeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Liveness probe — AGENTS.md requires it to stay unconditional."""
    monkeypatch.setenv(ENV, "occ_tickets")
    assert _client().get("/healthz").json() == {"ok": True}


# ── POST /query ──────────────────────────────────────────────────────────────


def test_query_endpoint_answers_503_when_unseeded(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_stub("occ_help")
    monkeypatch.setenv(ENV, "occ_help")
    resp = _client().post("/query", json={"text": "Quarantäne", "index_name": "occ_help"})
    assert resp.status_code == 503
    # digibase's handler renders HTTPException.detail verbatim into error.message.
    message = resp.json()["error"]["message"]
    assert "corpus_not_seeded" in message
    assert "occ_help" in message


def test_query_endpoint_still_answers_200_when_seeded() -> None:
    _seed_stub("occ_help")
    resp = _client().post("/query", json={"text": "Quarantäne", "index_name": "occ_help"})
    assert resp.status_code == 200
    assert resp.json()["results"]


# ── /v1/orchestrator_invoke ───────────────────────────────────────────────────


def test_orchestrator_invoke_reports_ok_false_when_unseeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """digisearch_tools.py branches on ``inv["ok"]`` — stay on that shape, not a 500."""
    _seed_stub("occ_tickets")
    monkeypatch.setenv(ENV, "occ_tickets")
    resp = _client().post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch",
            "arguments": {"query": "Quarantäne", "index_name": "occ_tickets"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "corpus_not_seeded" in body["error"]
    assert "occ_tickets" in body["error"]


def test_orchestrator_invoke_succeeds_when_seeded() -> None:
    _seed_stub("occ_tickets")
    resp = _client().post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch",
            "arguments": {"query": "Quarantäne", "index_name": "occ_tickets"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
