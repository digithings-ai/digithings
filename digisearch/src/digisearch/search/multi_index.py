"""MultiIndexSearcher - fan-out to multiple indexes, merge results."""

from __future__ import annotations

from digisearch.core.models import Query, Result
from digisearch.indexes.base import DigiIndex


def _rrf_merge(results_list: list[list[Result]], k: int = 60) -> list[Result]:
    """Merge multiple result lists with RRF."""
    scores: dict[str, tuple[Result, float]] = {}
    for results in results_list:
        for r in results:
            cid = r.chunk.id
            s = 1.0 / (k + r.rank)
            if cid in scores:
                old_r, old_s = scores[cid]
                scores[cid] = (old_r, old_s + s)
            else:
                scores[cid] = (r, s)
    ranked = sorted(scores.values(), key=lambda x: x[1], reverse=True)
    return [Result(chunk=r.chunk, score=s, rank=i + 1) for i, (r, s) in enumerate(ranked)]


class MultiIndexSearcher:
    """Fan-out query to multiple indexes, merge with RRF."""

    def __init__(self, indexes: list[DigiIndex]) -> None:
        self.indexes = indexes

    def search(self, query: Query, top_k: int | None = None) -> list[Result]:
        k = top_k or query.top_k
        all_results = [idx.query(query) for idx in self.indexes]
        merged = _rrf_merge(all_results)
        return merged[:k]
