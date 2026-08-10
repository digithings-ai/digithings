"""BM25Searcher, TFIDFSearcher - keyword search."""

from __future__ import annotations

import logging
import time
from collections import Counter

from digisearch.core.models import Chunk, Query, Result

logger = logging.getLogger(__name__)

try:
    from rank_bm25 import BM25Okapi

    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


class BM25Searcher:
    """BM25 scoring over corpus. Uses rank_bm25."""

    def __init__(self, corpus: list[str]) -> None:
        if not _BM25_AVAILABLE:
            raise ImportError("Install rank_bm25 for BM25 search")
        tokenized = [doc.lower().split() for doc in corpus]
        self._bm25 = BM25Okapi(tokenized)
        self._corpus = corpus

    def search(self, query: Query, top_k: int | None = None) -> list[Result]:
        start = time.perf_counter()
        k = top_k or query.top_k
        tokens = query.text.lower().split()
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out: list[Result] = []
        for i, idx in enumerate(ranked[:k]):
            if scores[idx] <= 0:
                break
            chunk = Chunk(
                id=str(idx),
                content=self._corpus[idx],
                doc_id=str(idx),
                embedding=None,
                metadata={},
            )
            out.append(Result(chunk=chunk, score=float(scores[idx]), rank=i + 1))
        logger.info(
            "bm25 search done",
            extra={
                "operation": "bm25_search",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "top_k": k,
                "corpus_size": len(self._corpus),
                "result_count": len(out),
            },
        )
        return out


class TFIDFSearcher:
    """TF-IDF scoring. Simple implementation."""

    def __init__(self, corpus: list[str]) -> None:
        from math import log

        docs = [doc.lower().split() for doc in corpus]
        n = len(docs)
        df: Counter[str] = Counter()
        for d in docs:
            for t in set(d):
                df[t] += 1
        self._idf = {t: log(n / (df[t] + 1) + 1) for t in df}
        self._docs = docs
        self._corpus = corpus

    def search(self, query: Query, top_k: int | None = None) -> list[Result]:
        from math import log

        start = time.perf_counter()
        k = top_k or query.top_k
        q_tokens = query.text.lower().split()
        scores: list[tuple[int, float]] = []
        for i, doc in enumerate(self._docs):
            tf = Counter(doc)
            score = sum(
                (1 + log(tf.get(t, 0) + 1)) * self._idf.get(t, 0) for t in q_tokens if t in doc
            )
            scores.append((i, score))
        ranked = sorted(scores, key=lambda x: x[1], reverse=True)
        out: list[Result] = []
        for rank, (idx, score) in enumerate(ranked[:k], 1):
            if score <= 0:
                break
            chunk = Chunk(
                id=str(idx),
                content=self._corpus[idx],
                doc_id=str(idx),
                embedding=None,
                metadata={},
            )
            out.append(Result(chunk=chunk, score=float(score), rank=rank))
        logger.info(
            "tfidf search done",
            extra={
                "operation": "tfidf_search",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "top_k": k,
                "corpus_size": len(self._corpus),
                "result_count": len(out),
            },
        )
        return out
