"""Offline checks for the semantic ticket-search gold set (#4756).

The live recall leg runs against a populated occ_tickets index by the
operator (see scripts/zammad_mcp/README.md); these tests pin the harness
math and the gold-file shape with no network, weights, or secrets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.zammad_mcp.eval import compute_recall

pytestmark = pytest.mark.unit

GOLD_PATH = Path(__file__).parent / "data" / "zammad_semantic_gold.json"
RECALL_BAR = 0.8


def test_compute_recall_all_hits() -> None:
    gold = [{"query": "q", "expected_ticket_ids": [1, 2]}]
    got = compute_recall({"q": [2, 9, 8, 7, 6]}, gold, k=5)
    assert got["recall@5"] == pytest.approx(1.0)


def test_compute_recall_partial_credit() -> None:
    gold = [
        {"query": "a", "expected_ticket_ids": [1]},
        {"query": "b", "expected_ticket_ids": [2]},
    ]
    got = compute_recall({"a": [1], "b": [9]}, gold, k=5)
    assert got["recall@5"] == pytest.approx(0.5)
    assert got["per_query"] == {"a": True, "b": False}


def test_gold_file_valid() -> None:
    gold = json.loads(GOLD_PATH.read_text())
    assert len(gold) >= 24
    for pair in gold:
        assert pair["query"].strip()
        assert pair["lang"] in ("de", "en")
        assert len(pair["expected_ticket_ids"]) >= 1
