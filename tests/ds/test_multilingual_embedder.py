"""Unit tests for the multilingual embedding provider + occ_tickets backfill (#4756)."""

from __future__ import annotations

import pytest
from digisearch.embedding.factory import (
    _build_raw_provider,
    resolve_embedding_pipeline,
    unwrap_embedding_provider,
)
from digisearch.embedding.providers import multilingual as multilingual_module
from digisearch.embedding.providers.multilingual import (
    MULTILINGUAL_DIMENSIONS,
    MULTILINGUAL_MODEL_ID,
    MultilingualEmbedder,
    get_default_multilingual_embedder,
)

from scripts.index_occ_tickets import SNAPSHOT_DATE, build_ticket_chunks

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_multilingual_singleton():
    multilingual_module._default_multilingual_singleton = None
    try:
        yield
    finally:
        multilingual_module._default_multilingual_singleton = None


def test_multilingual_embedder_reports_model_and_dimensions() -> None:
    provider = MultilingualEmbedder(embed_fn=lambda texts: [[0.5] * MULTILINGUAL_DIMENSIONS])
    assert provider.model_id == MULTILINGUAL_MODEL_ID
    assert provider.dimensions == MULTILINGUAL_DIMENSIONS == 384
    assert provider.embed([]) == []
    vectors = provider.embed(["hello"])
    assert len(vectors) == 1 and len(vectors[0]) == MULTILINGUAL_DIMENSIONS
    assert all(isinstance(x, float) for x in vectors[0])


def test_multilingual_default_singleton_is_shared() -> None:
    assert get_default_multilingual_embedder() is get_default_multilingual_embedder()


def test_factory_builds_multilingual_provider() -> None:
    from digisearch.embedding.providers.multilingual import MULTILINGUAL_MODEL_ID

    # The env var carries the model id itself (lowercased by resolution);
    # the factory literal must stay identical to the canonical constant.
    assert MULTILINGUAL_MODEL_ID.lower() == "xenova/paraphrase-multilingual-minilm-l12-v2"
    provider = _build_raw_provider(MULTILINGUAL_MODEL_ID, None)
    assert isinstance(provider, MultilingualEmbedder)
    provider = _build_raw_provider(MULTILINGUAL_MODEL_ID.lower(), None)
    assert isinstance(provider, MultilingualEmbedder)
    from digisearch.embedding.factory import EmbeddingConfigError

    with pytest.raises(EmbeddingConfigError, match="single model"):
        _build_raw_provider(MULTILINGUAL_MODEL_ID, "some-other-model")


def test_factory_rejects_alias_names_without_model_id() -> None:
    from digisearch.embedding.factory import EmbeddingConfigError

    for alias in ("multilingual", "multi", "paraphrase-multilingual", "minilm-multi"):
        with pytest.raises(EmbeddingConfigError, match="unknown embedding provider"):
            _build_raw_provider(alias, None)


def test_factory_resolves_multilingual_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path=None
) -> None:
    from digisearch.embedding.providers.multilingual import MULTILINGUAL_MODEL_ID

    monkeypatch.setenv("DIGISEARCH_EMBEDDING_PROVIDER", MULTILINGUAL_MODEL_ID)
    monkeypatch.setenv("DIGISEARCH_EMBED_CACHE", "0")
    monkeypatch.delenv("DIGISEARCH_EMBED", raising=False)
    pipeline = resolve_embedding_pipeline()
    assert pipeline is not None
    assert isinstance(unwrap_embedding_provider(pipeline), MultilingualEmbedder)


def test_build_ticket_chunks_masks_identity_and_drops_internal() -> None:
    """DIG-1210: the shipped corpus is masked, not #4756's full metadata.

    The metadata *shape* #4756 pinned still holds — one chunk per article, stable
    ``zammad-<id>-<index>`` ids, the filterable ``customer_id``, the snapshot
    marker and the ``internal`` flag. What changed is that customer identity no
    longer reaches the index and internal staff notes are not indexed at all.
    The demo override that restores the #4756 output is pinned in
    ``tests/scripts/test_index_occ_tickets_privacy.py``.
    """
    ticket = {
        "id": 231,
        "number": "28312",
        "title": "Example ticket subject",
        "state": "open",
        "group": "Sitaas",
        "priority": "2 normal",
        "customer": "jane.doe@example.test",
        "customer_id": 7,
        "owner": "ada",
        "created_at": "2026-09-15T12:00:00.000Z",
        "updated_at": "2026-09-16T12:00:00.000Z",
    }
    articles = [
        {
            "id": 1,
            "sender": "Customer",
            "type": "web",
            "internal": False,
            "from": "jane.doe@example.test",
            "subject": "Login fails",
            "body": "<p>Cannot log in since Monday</p>",
            "created_at": "2026-09-15T12:00:00.000Z",
        },
        {
            "id": 2,
            "sender": "Agent",
            "type": "note",
            "internal": True,
            "from": "support@example.test",
            "body": "<p>internal-only note body</p>",
            "created_at": "2026-09-15T13:00:00.000Z",
        },
    ]
    chunks = build_ticket_chunks(ticket, articles, customer_name="Jane Doe")
    assert len(chunks) == 1
    first = chunks[0]
    assert first.id == "zammad-231-1"
    assert first.doc_id == "zammad-ticket-231"
    # Pseudonym everywhere identity used to sit; the drill-down key survives.
    assert first.metadata["customer"] == "customer #7"
    assert first.metadata["customer_name"] == "customer #7"
    assert first.metadata["customer_id"] == 7
    assert first.metadata["snapshot_date"] == SNAPSHOT_DATE
    assert first.metadata["internal"] is False
    # No customer identity survives in the indexed text or the metadata.
    for secret in ("jane.doe@example.test", "Jane Doe"):
        assert secret not in first.content
        assert secret not in str(first.metadata)
    assert "From:" not in first.content
    # The internal article is not indexed at all, and the gap is stated.
    assert "internal-only note body" not in first.content
    assert "[internal]" not in first.content
    assert "1 internal note(s) withheld" in first.content


def test_embed_onnx_mean_pools_masked_tokens_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    provider = MultilingualEmbedder()

    class _Encoding:
        def __init__(self, ids: list[int]) -> None:
            self.ids = ids
            self.attention_mask = [1] * len(ids)
            self.type_ids = [0] * len(ids)

    class _Tokenizer:
        def encode_batch(self, texts: list[str]) -> list[_Encoding]:
            return [_Encoding([101, 102, 103]) for _ in texts]

        def token_to_id(self, token: str) -> int | None:
            return None

    class _Input:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Session:
        def __init__(self) -> None:
            self.feeds: list[dict] = []

        def get_inputs(self) -> list[_Input]:
            return [_Input("input_ids"), _Input("attention_mask"), _Input("token_type_ids")]

        def run(self, _output_names: object, feed: dict) -> list:
            self.feeds.append(feed)
            hidden = np.zeros((1, 3, MULTILINGUAL_DIMENSIONS))
            hidden[0, 0, 0] = 3.0
            hidden[0, 1, 1] = 4.0
            hidden[0, 2, :] = 99.0  # masked out: must not leak into the pool
            return [hidden]

    session = _Session()
    monkeypatch.setattr(provider, "_load", lambda: (session, _Tokenizer()))
    # Mask the third token out via the attention mask path.
    original_encode = _Tokenizer.encode_batch

    def _masked_encode(self: _Tokenizer, texts: list[str]) -> list[_Encoding]:
        encodings = original_encode(self, texts)
        for encoding in encodings:
            encoding.attention_mask = [1, 1, 0]
        return encodings

    monkeypatch.setattr(_Tokenizer, "encode_batch", _masked_encode)
    vectors = provider.embed(["hello world"])
    assert len(vectors) == 1 and len(vectors[0]) == MULTILINGUAL_DIMENSIONS
    import math

    assert vectors[0][0] == pytest.approx(0.6)
    assert vectors[0][1] == pytest.approx(0.8)
    assert all(v == pytest.approx(0.0) for v in vectors[0][2:])
    assert math.sqrt(sum(v * v for v in vectors[0])) == pytest.approx(1.0)
    assert set(session.feeds[0]) == {"input_ids", "attention_mask", "token_type_ids"}


def test_backfill_dry_run_pins_provider_threads_snapshot_and_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.index_occ_tickets as backfill_module
    from scripts.zammad_mcp import client as zammad_client_module

    ticket = {
        "id": 231,
        "number": "28312",
        "title": "Example ticket subject",
        "state": "open",
        "group": "Sitaas",
        "priority": "2 normal",
        "customer": "jane.doe@example.test",
        "customer_id": 7,
        "owner": "ada",
        "created_at": "2026-09-15T12:00:00.000Z",
        "updated_at": "2026-09-16T12:00:00.000Z",
    }
    articles = [
        {
            "id": 1,
            "sender": "Customer",
            "type": "web",
            "internal": False,
            "from": "jane.doe@example.test",
            "body": "<p>Cannot log in</p>",
            "created_at": "2026-09-15T12:00:00.000Z",
        },
        {
            "id": 2,
            "sender": "Agent",
            "type": "note",
            "internal": False,
            "from": "support@example.test",
            "body": "",
            "created_at": "2026-09-15T13:00:00.000Z",
        },
    ]

    class _FakeClient:
        def list_tickets(self) -> list[dict]:
            return [ticket]

        def get_articles(self, ticket_id: int) -> list[dict]:
            assert ticket_id == 231
            return articles

        def resolve_user(self, user_id: int) -> str:
            assert user_id == 7
            return "Jane Doe"

    monkeypatch.setattr(zammad_client_module, "ZammadClient", _FakeClient)
    monkeypatch.setenv("ZAMMAD_API_TOKEN", "test-token")
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)
    summary = backfill_module.backfill(dry_run=True, snapshot_date="2026-11-01")
    assert summary["tickets_scanned"] == 1
    assert summary["ticket_failures"] == 0
    assert summary["snapshot_date"] == "2026-11-01"
    assert summary["capped_at_500"] is False
    # Empty-body article skipped; snapshot date threads into chunk metadata.
    assert summary["chunks"] == 1
    # Dry run indexes nothing and leaves the process env untouched.
    import os

    assert "DIGISEARCH_EMBEDDING_PROVIDER" not in os.environ
    with pytest.raises(SystemExit):
        backfill_module.backfill(max_tickets=0, dry_run=True)


def test_backfill_indexing_pins_and_restores_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    import scripts.index_occ_tickets as backfill_module
    from scripts.zammad_mcp import client as zammad_client_module

    ticket = {"id": 231, "number": "28312", "title": "Example", "customer_id": 7}
    articles = [
        {
            "id": 1,
            "sender": "Customer",
            "type": "web",
            "internal": False,
            "body": "<p>Cannot log in</p>",
            "created_at": "2026-09-15T12:00:00.000Z",
        },
    ]

    class _FakeClient:
        def list_tickets(self) -> list[dict]:
            return [ticket]

        def get_articles(self, ticket_id: int) -> list[dict]:
            return articles

        def resolve_user(self, user_id: int) -> str:
            return "Jane Doe"

    seen: dict[str, object] = {}

    def _fake_index_chunks(
        index_name: str, chunks: list, embedding_provider: object = None
    ) -> None:
        seen["index"] = index_name
        seen["chunks"] = len(chunks)
        seen["provider_env"] = os.environ.get("DIGISEARCH_EMBEDDING_PROVIDER")

    monkeypatch.setattr(zammad_client_module, "ZammadClient", _FakeClient)
    monkeypatch.setattr("digisearch.pipeline.ingest.index_chunks", _fake_index_chunks)
    monkeypatch.setenv("ZAMMAD_API_TOKEN", "test-token")
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)
    summary = backfill_module.backfill(dry_run=False)
    assert seen["index"] == "occ_tickets"
    assert seen["chunks"] == 1
    # Backend saw the model-id pin during indexing ...
    from digisearch.embedding.providers.multilingual import MULTILINGUAL_MODEL_ID

    assert seen["provider_env"] == MULTILINGUAL_MODEL_ID
    # ... and the process env is restored afterwards (no leakage).
    assert "DIGISEARCH_EMBEDDING_PROVIDER" not in os.environ
    assert summary["chunks"] == 1


def test_backfill_refuses_conflicting_preset_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    import scripts.index_occ_tickets as backfill_module
    from scripts.zammad_mcp import client as zammad_client_module

    class _FakeClient:
        def list_tickets(self) -> list[dict]:
            return [{"id": 231, "number": "1", "title": "t"}]

        def get_articles(self, ticket_id: int) -> list[dict]:
            return [
                {
                    "id": 1,
                    "sender": "Customer",
                    "type": "web",
                    "internal": False,
                    "body": "<p>hi</p>",
                    "created_at": "2026-09-15T12:00:00.000Z",
                }
            ]

        def resolve_user(self, user_id: int) -> str:
            return "Jane Doe"

    monkeypatch.setattr(zammad_client_module, "ZammadClient", _FakeClient)
    monkeypatch.setenv("ZAMMAD_API_TOKEN", "test-token")
    monkeypatch.setenv("DIGISEARCH_EMBEDDING_PROVIDER", "minilm")
    with pytest.raises(SystemExit, match="refusing to index"):
        backfill_module.backfill(dry_run=False)
    # Conflicting preset is left exactly as found.
    assert os.environ["DIGISEARCH_EMBEDDING_PROVIDER"] == "minilm"
