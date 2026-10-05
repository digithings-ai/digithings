"""Gold-set recall harness for semantic ticket search (issue #4756)."""

from __future__ import annotations


def compute_recall(
    results_by_query: dict[str, list[int]],
    gold: list[dict],
    k: int = 5,
) -> dict:
    per_query: dict[str, bool] = {}
    for pair in gold:
        hits = results_by_query.get(pair["query"], [])[:k]
        per_query[pair["query"]] = any(t in hits for t in pair["expected_ticket_ids"])
    score = sum(per_query.values()) / len(per_query) if per_query else 0.0
    return {f"recall@{k}": score, "per_query": per_query}
