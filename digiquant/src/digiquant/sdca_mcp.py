"""JSON helpers for SDCA MCP / orchestrator tools (not a second product).

MCP ``mcp_server.py`` and HTTP ``orchestrator_invoke`` both call these so
Stage A, the risk index, and Bitview ingest stay on the same Pydantic path
as ``digiquant_run_optimize``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any  # score:allow untyped any — MCP JSON argument bags

from digiquant.data.onchain.bitview import DEFAULT_CACHE_DIR as BITVIEW_CACHE
from digiquant.data.onchain.bitview import DEFAULT_SERIES, fetch_bitview_series
from digiquant.data.prices.history_cache import DEFAULT_CACHE_DIR, incremental_update, load_cached
from digiquant.strategies.sdca.asset_profile import daily_closes_from_ohlcv
from digiquant.strategies.sdca.fit_weights import (
    fit_sdca_weights_from_cache,
    resolve_sdca_profile,
)
from digiquant.strategies.sdca.indicator_catalog import (
    build_extra_indicators,
    parse_indicator_weights_json,
    sources_from_optional_paths,
)
from digiquant.strategies.sdca.providers import KNOWN_SDCA_RISK_MODELS, resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import (
    RiskIndexBuildResult,
    build_risk_index,
    write_risk_index,
)


def run_fetch_bitview_series(
    *,
    series_ids_json: str = "",
    cache_dir: str | None = None,
    timeout: float = 30.0,
    start: int | None = None,
    end: int | None = None,
    session: Any | None = None,
) -> str:
    """Fail-soft Bitview/BRK fetch. Returns JSON (never raises)."""
    try:
        ids = json.loads(series_ids_json) if series_ids_json.strip() else list(DEFAULT_SERIES)
        if not isinstance(ids, list):
            return json.dumps({"error": "series_ids_json must be a JSON array of series ids"})
        result = fetch_bitview_series(
            [str(s) for s in ids],
            cache_dir=cache_dir or str(BITVIEW_CACHE),
            timeout=timeout,
            session=session,
            start=start,
            end=end,
        )
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return result.model_dump_json(indent=2)


def run_fit_sdca_weights(
    *,
    profile: str = "btc_v1",
    profile_json: str | None = None,
    cache_dir: str | None = None,
    coefficients_path: str | None = None,
    output_path: str | None = None,
    m2_path: str | None = None,
    dxy_path: str | None = None,
    eth_ticker: str = "ETH-USD",
    valuation_form: str = "log_quadratic",
    rolling_window: int = 90,
) -> str:
    """Stage A + regularize. Returns JSON (never raises)."""
    try:
        resolved = resolve_sdca_profile(profile, profile_json=profile_json)
        result = fit_sdca_weights_from_cache(
            resolved,
            cache_dir=cache_dir,
            coefficients_path=coefficients_path,
            m2_path=m2_path,
            dxy_path=dxy_path,
            eth_ticker=eth_ticker,
            valuation_form=valuation_form,
            rolling_window=rolling_window,
            output_path=output_path,
            profile_name=profile,
        )
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return result.model_dump_json(indent=2)


def run_build_sdca_risk_index(
    *,
    ticker: str = "BTC-USD",
    cache_dir: str | None = None,
    refresh: bool = True,
    bulk_period: str = "max",
    risk_model: str = "btc_power_law",
    profile: str | None = None,
    profile_json: str | None = None,
    coefficients_path: str | None = None,
    output_path: str | None = None,
    indicator_weights: str = "{}",
    m2_path: str | None = None,
    dxy_path: str | None = None,
    eth_ticker: str = "ETH-USD",
    valuation_form: str = "log_quadratic",
    rolling_window: int = 90,
) -> str:
    """Build ``date``/``risk`` parquet. Returns JSON (never raises)."""
    try:
        oscillators = None
        allowlist = None
        if profile or (profile_json or "").strip():
            resolved = resolve_sdca_profile(profile or "btc_v1", profile_json=profile_json)
            risk_model = resolved.risk_model
            oscillators = resolved.oscillators
            allowlist = list(resolved.extra_indicators)
        if risk_model not in KNOWN_SDCA_RISK_MODELS:
            return json.dumps({"error": f"unknown risk_model {risk_model!r}"})

        cdir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        if refresh:
            df = incremental_update([ticker], cdir, bulk_period=bulk_period).get(ticker)
        else:
            df = load_cached(ticker, cdir)
        if df is None or df.is_empty():
            return json.dumps({"error": f"no cached price history for {ticker!r}"})

        coeff_path = Path(coefficients_path) if coefficients_path else None
        if coeff_path is not None and not coeff_path.exists():
            return json.dumps({"error": f"coefficients file not found: {coeff_path}"})

        dates, close = daily_closes_from_ohlcv(df)
        model = resolve_sdca_risk_model(
            risk_model,
            dates=dates,
            price=close,
            coefficients_path=coeff_path,
            form=valuation_form,
            rolling_window=rolling_window,
        )
        weights = parse_indicator_weights_json(indicator_weights)
        eth_dates = eth_close = None
        if weights.rs_eth > 0.0:
            eth_df = load_cached(eth_ticker, cdir)
            if eth_df is None or eth_df.is_empty():
                return json.dumps(
                    {"error": f"no cached price history for {eth_ticker!r} (rs_eth weight > 0)"}
                )
            eth_dates, eth_close = daily_closes_from_ohlcv(eth_df)
        extras = build_extra_indicators(
            dates,
            close,
            weights,
            sources_from_optional_paths(
                m2_path=m2_path,
                dxy_path=dxy_path,
                eth_dates=eth_dates,
                eth_close=eth_close,
            ),
            oscillators=oscillators,
            allowlist=allowlist,
        )
        frame = build_risk_index(
            dates,
            close,
            model,
            extra_indicators=extras,
            power_law_weight=weights.power_law,
        )
        dest = Path(output_path) if output_path else Path(f"{ticker}_sdca_risk.parquet")
        path = write_risk_index(frame, dest)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    dates_col = frame["date"]
    result = RiskIndexBuildResult(
        path=str(path),
        row_count=frame.height,
        date_start=dates_col[0],
        date_end=dates_col[-1],
        null_risk_days=int(frame["risk"].null_count()),
    )
    return result.model_dump_json(indent=2)


__all__ = [
    "run_build_sdca_risk_index",
    "run_fetch_bitview_series",
    "run_fit_sdca_weights",
]
