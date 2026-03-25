"""Unit tests for quant JSON extraction helpers in research node."""

from __future__ import annotations

import json

import pytest

from digigraph.graph.research import (
    _coerce_symbols_from_llm,
    _parse_llm_json_object,
    _pick_strategy_name,
    _unwrap_quant_payload,
)


@pytest.mark.unit
def test_parse_llm_json_object_preamble() -> None:
    raw = 'Sure thing. {"strategy_name": "ema_cross", "symbols": ["AAPL"]}'
    data = _parse_llm_json_object(raw)
    assert data["strategy_name"] == "ema_cross"
    assert data["symbols"] == ["AAPL"]


@pytest.mark.unit
def test_parse_llm_json_object_nested_braces_in_string() -> None:
    raw = r'{"strategy_name": "x", "symbols": ["AAPL"], "note": "use { curlies }"}'
    data = _parse_llm_json_object(raw)
    assert data["strategy_name"] == "x"


@pytest.mark.unit
def test_coerce_symbols_from_string() -> None:
    assert _coerce_symbols_from_llm("AAPL, MSFT; GOOGL") == ["AAPL", "MSFT", "GOOGL"]


@pytest.mark.unit
def test_unwrap_and_pick_aliases() -> None:
    data = _unwrap_quant_payload(
        {
            "result": {
                "strategy": "bollinger_mr",
                "tickers": ["SPY"],
            }
        }
    )
    assert _pick_strategy_name(data) == "bollinger_mr"
    assert _coerce_symbols_from_llm(data.get("symbols")) == []
    assert _coerce_symbols_from_llm(data.get("tickers")) == ["SPY"]


@pytest.mark.unit
def test_parse_invalid_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        _parse_llm_json_object("not json at all")
