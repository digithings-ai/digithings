"""Chat-visible honest_rate JSON — the text the model actually reads (DIG-474 L4).

`mcp_server.py:702` returns `result.model_dump_json(indent=2)`. That *string* is the
only honest-rate surface the chat model sees, so this file asserts on the string, not
on the model object: a field that survives `model_dump` but is dropped, renamed, moved
or detached during serialization is caught here and nowhere else.

Fixtures are plain realized-PnL series — no Nautilus, no engine, no MCP transport.
"""

from __future__ import annotations

import json

import pytest
from digiquant.models import BacktestResult
from digiquant.nautilus_runner import _build_result
from digiquant.stats import DISCLAIMER, HonestRateBlock

pytestmark = pytest.mark.unit

_T0 = 1_700_000_000_000_000_000
_T1 = 1_700_086_400_000_000_000
_PERF = {"sharpe": 1.25, "max_dd": -12.5}


def _result(pnls, num_trades=None):
    return _build_result(
        "r1", "s", ["EURUSD"], "EURUSD", _T0, _T1, 1234.5, 4.5,
        len(pnls) if num_trades is None else num_trades,
        {**_PERF, "realized_pnls_series": pnls},
    )


def _json(pnls, num_trades=None):
    """The exact string `mcp_server.py:702` hands the chat model."""
    return _result(pnls, num_trades).model_dump_json(indent=2)


def _floats(node):
    """Every float rendered anywhere inside a decoded JSON node."""
    if isinstance(node, dict):
        return [f for v in node.values() for f in _floats(v)]
    if isinstance(node, list):
        return [f for v in node for f in _floats(v)]
    return [node] if isinstance(node, float) else []


def test_serialized_text_carries_rate_denominator_and_both_ci_ends():
    text = _json([10.0 if i % 3 else -5.0 for i in range(60)])
    block = json.loads(text)["honest_rate"]
    assert (block["k"], block["n"]) == (40, 60)
    assert 0.0 < block["ci_lo"] < block["estimate"] < block["ci_hi"] < 1.0
    assert '"ci_lo"' in text and '"ci_hi"' in text and '"honest_rate"' in text


def test_disclaimer_ships_inside_the_block_and_nowhere_else():
    doc = json.loads(_json([10.0 if i % 3 else -5.0 for i in range(60)]))
    assert json.dumps(doc).count(DISCLAIMER) == 1
    assert doc["honest_rate"]["disclaimer"] == DISCLAIMER
    assert "disclaimer" not in doc, "a top-level disclaimer is quotable without the rate"
    for key in ("sharpe_ratio", "total_pnl", "num_trades"):
        assert not isinstance(doc[key], (dict, list, str)), key


def test_refused_sample_states_the_floor_and_nulls_the_whole_rate():
    block = json.loads(_json([10.0 if i % 2 else -5.0 for i in range(6)]))["honest_rate"]
    assert block["refused"] is True and block["refuse_floor"] == 10
    assert block["estimate"] is block["ci_lo"] is block["ci_hi"] is None


@pytest.mark.xfail(
    strict=True,
    reason="L3 gap (DIG-474 L4 finding): stability_split() calls wilson() unguarded, so a "
    "refused block still serializes half-sample rates. Fix belongs in stats/honesty.py, "
    "which this leaf may not touch; strict=True so the fix turns this red.",
)
def test_refused_sample_renders_no_rate_float_anywhere_in_the_text():
    block = json.loads(_json([10.0 if i % 2 else -5.0 for i in range(6)]))["honest_rate"]
    assert _floats(block) == [], f"refused result still renders rates: {_floats(block)}"


def test_reportable_but_small_sample_is_flagged_low_sample():
    block = json.loads(_json([10.0 if i % 3 else -5.0 for i in range(20)]))["honest_rate"]
    assert (block["n"], block["low_sample"], block["refused"]) == (20, True, False)


def test_multi_symbol_text_nulls_the_total_rate_and_blocks_each_symbol():
    text = BacktestResult(
        run_id="r1", strategy_name="s", symbols=["EURUSD", "GBPUSD"],
        start_time="2023-11-14T00:00:00Z", end_time="2023-11-15T00:00:00Z",
        total_pnl=12.0, num_trades=40, honest_rate=None,
        honest_rate_by_symbol={"EURUSD": HonestRateBlock(k=8, n=20),
                               "GBPUSD": HonestRateBlock(k=15, n=30)},
    ).model_dump_json(indent=2)
    doc = json.loads(text)
    assert '"honest_rate": null' in text
    assert sorted(doc["honest_rate_by_symbol"]) == ["EURUSD", "GBPUSD"]
    assert doc["honest_rate_by_symbol"]["EURUSD"]["n"] == 20
    assert doc["honest_rate_by_symbol"]["GBPUSD"]["n"] == 30


def test_fill_count_cannot_be_narrated_as_a_rate():
    doc = json.loads(_json([10.0, -5.0, 20.0], num_trades=7))
    assert doc["num_trades"] == 7
    assert doc["honest_rate"]["n"] == 3, "the denominator is the PnL series, not fills"
    assert _floats(doc["num_trades"]) == []


def test_mcp_tool_returns_the_same_serialized_text(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import create_mcp_server

    from digiquant import service as service_mod

    monkeypatch.setattr(
        service_mod, "service_run_backtest",
        lambda **kw: _result([10.0 if i % 3 else -5.0 for i in range(60)]),
    )
    fn = create_mcp_server()._tool_manager.get_tool("digiquant_run_backtest").fn
    text = fn(strategy_name="s", symbols_json='["EURUSD"]')
    assert '"honest_rate"' in text and '"refuse_floor"' in text and '"n": 60' in text