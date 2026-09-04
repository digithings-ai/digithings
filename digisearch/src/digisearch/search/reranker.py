"""Reranker - cross-encoder second pass. Cohere, BGE, CrossEncoder."""

from __future__ import annotations

import logging

from digisearch.core.models import Result

logger = logging.getLogger(__name__)

# Multilingual BGE cross-encoder (ADR-0025 Phase 4 / #2441).
BGE_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class Reranker:
    """Rerank initial results with cross-encoder."""

    def __init__(self, provider: str = "cohere", top_n: int | None = None) -> None:
        self.provider = provider
        # None = no silent default cap; callers should pass top_n / use query.top_k.
        self.top_n = top_n
        self._model: object | None = None

    def rerank(self, query: str, results: list[Result], top_n: int | None = None) -> list[Result]:
        if not results:
            return []
        if top_n is not None:
            n = top_n
        elif self.top_n is not None:
            n = self.top_n
        else:
            n = len(results)
        if self.provider == "cohere":
            return self._rerank_cohere(query, results, n)
        if self.provider == "bge":
            return self._rerank_bge(query, results, n)
        return results[:n]

    def _rerank_cohere(self, query: str, results: list[Result], n: int) -> list[Result]:
        try:
            import os

            import cohere

            client = cohere.Client(os.environ.get("COHERE_API_KEY", ""))
            docs = [r.chunk.content for r in results]
            r = client.rerank(
                query=query, documents=docs, top_n=n, model="rerank-multilingual-v3.0"
            )
            out: list[Result] = []
            for i, idx in enumerate(r.results):
                orig = results[idx.index]
                out.append(Result(chunk=orig.chunk, score=idx.relevance_score, rank=i + 1))
            return out
        except Exception as exc:
            logger.warning("Cohere rerank failed (%s); falling back to original order", exc)
            return results[:n]

    def _rerank_bge(self, query: str, results: list[Result], n: int) -> list[Result]:
        try:
            from sentence_transformers import CrossEncoder

            if self._model is None:
                self._model = CrossEncoder(BGE_RERANKER_MODEL)
            pairs = [(query, r.chunk.content) for r in results]
            scores = self._model.predict(pairs)
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
            return [
                Result(chunk=results[i].chunk, score=float(scores[i]), rank=j + 1)
                for j, i in enumerate(ranked)
            ]
        except Exception as exc:
            logger.warning("BGE rerank failed (%s); falling back to original order", exc)
            return results[:n]
