"""Cost/latency accounting for the Phase B web research branch (#4064)."""

from __future__ import annotations

import pytest
from digisearch.web.accounting import (
    estimate_cost,
    finalize_usage,
    record_stage,
    start_clock,
)


@pytest.mark.unit
def test_stages_sum_to_total():
    t = start_clock()
    record_stage(t, "search_ms", 120)
    record_stage(t, "fetch_ms", 300)
    u = finalize_usage(t, searches=1, pages_fetched=5, pages_cited=3, llm_calls=1)
    assert u.search_ms == 120
    assert u.total_ms == 420
    assert u.pages_cited == 3


@pytest.mark.unit
def test_cost_shape_is_advisory_only():
    c = estimate_cost(searches=1, pages_fetched=5, llm_calls=1)
    assert c.total == 0.0
    assert c.provider == "web-oss"
    assert c.breakdown == {"searches": 1, "pages_fetched": 5, "llm_calls": 1}
    assert "digillm" in c.note


@pytest.mark.unit
def test_record_stage_accumulates_repeats():
    t = start_clock()
    record_stage(t, "search_ms", 40)
    record_stage(t, "search_ms", 80)
    u = finalize_usage(t)
    assert u.search_ms == 120
    assert u.total_ms == 120


@pytest.mark.unit
def test_finalize_usage_maps_every_stage_and_defaults_absent_to_zero():
    t = start_clock()
    for name, ms in [("search_ms", 1), ("fetch_ms", 2), ("rerank_ms", 3), ("synthesis_ms", 4)]:
        record_stage(t, name, ms)
    u = finalize_usage(t)
    assert (u.search_ms, u.fetch_ms, u.rerank_ms, u.synthesis_ms) == (1, 2, 3, 4)
    assert u.total_ms == 10
    empty = finalize_usage(start_clock())
    assert empty.total_ms == 0
    assert (empty.search_ms, empty.fetch_ms, empty.rerank_ms, empty.synthesis_ms) == (0, 0, 0, 0)


@pytest.mark.unit
def test_cost_breakdown_always_carries_llm_calls_key():
    c = estimate_cost(searches=0, pages_fetched=0, llm_calls=0)
    assert set(c.breakdown) == {"searches", "pages_fetched", "llm_calls"}
    assert c.breakdown["llm_calls"] == 0  # gates branch on this key, so it must always exist


@pytest.mark.unit
def test_usage_and_cost_dump_exa_mirror_keys():
    from digisearch.web.grounding_models import TurnCost, TurnUsage

    t = start_clock()
    record_stage(t, "search_ms", 5)
    usage = finalize_usage(t)
    cost = estimate_cost(searches=1, pages_fetched=5, llm_calls=1)
    assert isinstance(usage, TurnUsage)  # landed shapes, never a fork
    assert isinstance(cost, TurnCost)
    assert {"searches", "pages_fetched", "total_ms"} <= set(usage.model_dump())
    assert {"total", "provider", "breakdown", "note"} <= set(cost.model_dump())


@pytest.mark.unit
def test_accounting_never_imports_a_clock():
    import ast
    import inspect

    from digisearch.web import accounting as acc

    tree = ast.parse(inspect.getsource(acc))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert not roots & {"time", "datetime"}  # callers measure; these functions stay pure
