"""HybridSearcher - RRF fusion of keyword + vector."""

from __future__ import annotations

import logging
import time

from digisearch.core.models import Query, Result

logger = logging.getLogger(__name__)


def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion."""
    return 1.0 / (k + rank)


class HybridSearcher:
    """Runs keyword and vector search, merges with RRF."""

    def __init__(
        self,
        keyword_searcher: object,
        vector_searcher: object,
        alpha: float = 0.6,
    ) -> None:
        self.keyword = keyword_searcher
        self.vector = vector_searcher
        self.alpha = alpha

    def search(self, query: Query, top_k: int | None = None) -> list[Result]:
        start = time.perf_counter()
        k = top_k or query.top_k
        try:
            expand_q = Query(text=query.text, top_k=k * 2, mode=query.mode)
            kw_results = (
                self.keyword.search(expand_q, top_k=k * 2)
                if hasattr(self.keyword, "search")
                else []
            )
            vec_results = self.vector.search(expand_q) if hasattr(self.vector, "search") else []
            vec_results = list(vec_results)[: k * 2] if vec_results else []
            seen: dict[str, float] = {}
            for r in kw_results:
                cid = r.chunk.id
                score = (1 - self.alpha) * _rrf_score(r.rank)
                seen[cid] = seen.get(cid, 0) + score
            for r in vec_results:
                cid = r.chunk.id
                score = self.alpha * _rrf_score(r.rank)
                seen[cid] = seen.get(cid, 0) + score
            ranked = sorted(seen.items(), key=lambda x: x[1], reverse=True)[:k]
            out: list[Result] = []
            all_results = {r.chunk.id: r for r in kw_results + vec_results}
            for i, (cid, score) in enumerate(ranked):
                if cid in all_results:
                    r = all_results[cid]
                    out.append(Result(chunk=r.chunk, score=score, rank=i + 1))
        except Exception:
            logger.exception(
                "hybrid search failed",
                extra={
                    "operation": "hybrid_search",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "top_k": k,
                },
            )
            raise
        logger.info(
            "hybrid search done",
            extra={
                "operation": "hybrid_search",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "top_k": k,
                "result_count": len(out),
                "kw_count": len(kw_results),
                "vec_count": len(vec_results),
            },
        )
        return out
