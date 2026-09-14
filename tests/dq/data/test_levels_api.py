"""Tests for the levels JSON contract + MCP/orchestrator wiring (E4, #137)."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.history_cache import save_cached
from digiquant.data.prices.levels import LevelsConfig, LevelsError
from digiquant.data.prices.levels_api import (
    compute_payload,
    config_from_json,
    levels_for_ticker,
    levels_json,
    parse_ohlc,
)
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest

pytestmark = pytest.mark.unit


def _bars(n: int = 60) -> list[dict]:
    rows: list[dict] = []
    price = 100.0
    for i in range(n):
        amp = 2.0 if i % 40 < 20 else 5.0
        price += amp * math.sin(i / 4.0)
        rows.append(
            {
                "timestamp": (date(2024, 1, 1) + timedelta(days=i)).isoformat(),
                "open": price - 0.2,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1_000_000.0,
            }
        )
    return rows


def _frame(n: int = 60) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)],
            "open": [100.0] * n,
            "high": [100.6] * n,
            "low": [99.4] * n,
            "close": [100.0] * n,
            "volume": [1.0] * n,
            "symbol": ["EUR-USD"] * n,
        }
    ).select(list(OHLCV_COLUMNS))


# ─── parse / config ──────────────────────────────────────────────────────────


def test_parse_ohlc_builds_a_frame() -> None:
    df = parse_ohlc(json.dumps(_bars(30)))
    assert df.height == 30
    assert {"open", "high", "low", "close"} <= set(df.columns)


def test_parse_ohlc_rejects_malformed_input() -> None:
    with pytest.raises(LevelsError, match="valid JSON"):
        parse_ohlc("{not json")
    with pytest.raises(LevelsError, match="non-empty"):
        parse_ohlc("[]")
    with pytest.raises(LevelsError, match="non-empty"):
        parse_ohlc("{}")


def test_config_from_json_defaults_and_overrides() -> None:
    assert config_from_json(None) == LevelsConfig()
    cfg = config_from_json('{"atr_len": 21, "tp_rmultiples": [1, 4], "k_regime_bounds": [0.5, 2]}')
    assert cfg.atr_len == 21
    assert cfg.tp_rmultiples == (1.0, 4.0)
    assert cfg.k_regime_bounds == (0.5, 2.0)


def test_config_from_json_rejects_unknown_fields() -> None:
    with pytest.raises(LevelsError, match="unknown LevelsConfig"):
        config_from_json('{"nope": 1}')


# ─── contract ────────────────────────────────────────────────────────────────


def test_compute_payload_contract_shape() -> None:
    payload = compute_payload(_frame(), "long", pair="EUR/USD", computed_at="2026-09-13T00:00:00Z")
    assert set(payload) >= {
        "pair",
        "direction",
        "entry",
        "sl",
        "tp_ladder",
        "trail_policy",
        "source_ref",
        "computed_at",
    }
    assert payload["pair"] == "EUR/USD"
    assert set(payload["entry"]) == {"low", "high", "ref"}
    assert payload["tp_ladder"] and set(payload["tp_ladder"][0]) == {"r", "price", "src"}
    assert payload["computed_at"] == "2026-09-13T00:00:00Z"


def test_levels_json_is_full_precision() -> None:
    from digiquant.data.prices.levels import compute_levels

    result = compute_levels(_frame(), "long", pair="EUR/USD")
    payload = json.loads(levels_json(_frame(), "long", pair="EUR/USD"))
    # Values must be the raw engine floats — never safe_float()-rounded to 4dp.
    assert payload["atr"] == result.atr
    assert payload["sl"] == result.sl
    assert payload["entry"]["ref"] == result.entry_ref
    assert payload["k_eff"] == result.k_eff


def test_levels_json_source_ref_grammar() -> None:
    payload = json.loads(levels_json(_frame(), "short", pair="EUR/USD"))
    src = payload["source_ref"]
    assert src.startswith("computed:atr14@")
    assert src.endswith("|src=base")
    assert "|k=" in src and "|reg=" in src and "|br=" in src and "|piv=" in src and "|rr=" in src


# ─── ticker convenience ────────────────────────────────────────────────────────


def test_levels_for_ticker_reads_cache(tmp_path) -> None:
    bars = _frame(220)
    save_cached("EUR-USD", bars, tmp_path)
    payload = json.loads(levels_for_ticker("EUR-USD", "long", cache_dir=tmp_path))
    assert payload["pair"] == "EUR-USD"
    assert "error" not in payload


def test_levels_for_ticker_missing_is_fail_soft(tmp_path) -> None:
    payload = json.loads(levels_for_ticker("NOPE-USD", "long", cache_dir=tmp_path))
    assert "error" in payload


# ─── MCP function + manifest + dispatch ───────────────────────────────────────


def test_mcp_function_prefers_caller_frame() -> None:
    from digiquant.mcp_server import digiquant_get_trade_levels

    payload = json.loads(
        digiquant_get_trade_levels(
            direction="long", ohlc_json=json.dumps(_bars(60)), pair="EUR/USD"
        )
    )
    assert "error" not in payload
    assert payload["direction"] == "long"
    assert payload["pair"] == "EUR/USD"


def test_mcp_function_requires_a_data_source() -> None:
    from digiquant.mcp_server import digiquant_get_trade_levels

    payload = json.loads(digiquant_get_trade_levels(direction="long"))
    assert "error" in payload


def test_mcp_function_surfaces_bad_input_as_error() -> None:
    from digiquant.mcp_server import digiquant_get_trade_levels

    payload = json.loads(digiquant_get_trade_levels(direction="long", ohlc_json="[]"))
    assert "error" in payload


def test_trade_levels_tool_is_read_scope() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server

    server = create_mcp_server(scope="read")
    names = {t.name for t in server._tool_manager.list_tools()}
    assert "digiquant_get_trade_levels" in names
    assert "digiquant_get_trade_levels" in READ_SCOPE_TOOLS


def test_orchestrator_manifest_includes_trade_levels() -> None:
    manifest = build_orchestrator_tool_manifest()
    tool = next(row for row in manifest if row["function"]["name"] == "digiquant_get_trade_levels")
    params = tool["function"]["parameters"]
    assert params["required"] == ["direction"]
    assert params["properties"]["direction"]["enum"] == ["long", "short"]
    assert "ohlc_json" in params["properties"]
    assert "never" in tool["function"]["description"].lower()


def test_orchestrator_invoke_dispatches_trade_levels() -> None:
    pytest.importorskip("fastapi")
    from digiquant.server import OrchestratorInvokeRequest, v1_orchestrator_invoke

    resp = v1_orchestrator_invoke(
        OrchestratorInvokeRequest(
            tool="digiquant_get_trade_levels",
            arguments={"direction": "long", "ohlc_json": json.dumps(_bars(60)), "pair": "EUR/USD"},
        )
    )
    assert resp["ok"] is True
    assert resp["data"]["direction"] == "long"


def test_orchestrator_invoke_trade_levels_errors_surface() -> None:
    pytest.importorskip("fastapi")
    from digiquant.server import OrchestratorInvokeRequest, v1_orchestrator_invoke

    resp = v1_orchestrator_invoke(
        OrchestratorInvokeRequest(
            tool="digiquant_get_trade_levels",
            arguments={"direction": "long", "ohlc_json": "[]"},
        )
    )
    assert resp["ok"] is False
    assert "error" in resp
