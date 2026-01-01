def _exploding_sentence_transformers(monkeypatch):
    import sys
    import types

    class _ExplodingCrossEncoder:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("cross-encoder load failed")

    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = _ExplodingCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)


def _results():
    from digisearch.core.models import Chunk, Result

    return [
        Result(chunk=Chunk(id=str(i), content=f"content-{i}", doc_id="doc"), score=1.0, rank=i + 1)
        for i in range(3)
    ]


def test_strict_bge_reranker_reraises_instead_of_falling_back(monkeypatch):
    import pytest

    from digisearch.search.reranker import Reranker

    _exploding_sentence_transformers(monkeypatch)
    reranker = Reranker(provider="bge", strict=True)
    assert reranker.strict is True

    with pytest.raises(RuntimeError, match="cross-encoder load failed"):
        reranker.rerank("q", _results(), top_n=2)


def test_default_bge_reranker_keeps_fail_open_fallback(monkeypatch, caplog):
    import logging

    from digisearch.search.reranker import Reranker

    _exploding_sentence_transformers(monkeypatch)
    results = _results()
    reranker = Reranker(provider="bge")  # default strict=False preserves landed behavior
    assert reranker.strict is False

    with caplog.at_level(logging.WARNING, logger="digisearch.search.reranker"):
        out = reranker.rerank("q", results, top_n=2)

    assert out == results[:2]  # original order fallback, unchanged
    assert "BGE rerank failed" in caplog.text
