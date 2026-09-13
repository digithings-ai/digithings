"""JSON contract + data access for the causal trade-levels engine (E4, #137).

The caller-supplied OHLC frame is the primary data path (lead ruling): the MCP
tool accepts a JSON array of bars, so a twelve-x caller can pass the exact
window it already holds. A ticker lookup over the local history cache is a
non-blocking convenience — it never fetches from the network here.

Read-only by construction: this module computes *candidate* entry/stop/target
levels and serialises them. It never sizes orders, places orders, or writes to
any store.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from digiquant.data.prices.levels import LevelsConfig, LevelsError, compute_levels

_CONFIG_FIELDS = frozenset(f.name for f in dataclasses.fields(LevelsConfig))


def parse_ohlc(ohlc_json: str) -> pl.DataFrame:
    """Parse a JSON array of bar objects into a Polars frame.

    Accepts ``[{"timestamp": ..., "open": ..., "high": ..., "low": ...,
    "close": ..., "volume": ...}, ...]`` (column names are lower-cased by the
    engine). Raises :class:`LevelsError` on malformed input.
    """
    try:
        records = json.loads(ohlc_json)
    except json.JSONDecodeError as exc:
        raise LevelsError(f"ohlc_json is not valid JSON: {exc}") from exc
    if not isinstance(records, list) or not records:
        raise LevelsError("ohlc_json must be a non-empty JSON array of bar objects")
    try:
        return pl.DataFrame(records)
    except Exception as exc:  # polars raises a variety of types on bad shapes
        raise LevelsError(f"could not build an OHLC frame from ohlc_json: {exc}") from exc


def config_from_json(config_json: str | None) -> LevelsConfig:
    """Build a :class:`LevelsConfig` from an optional JSON override object."""
    if not config_json:
        return LevelsConfig()
    try:
        raw = json.loads(config_json)
    except json.JSONDecodeError as exc:
        raise LevelsError(f"config_json is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise LevelsError("config_json must be a JSON object")
    unknown = set(raw) - _CONFIG_FIELDS
    if unknown:
        raise LevelsError(f"unknown LevelsConfig fields: {sorted(unknown)}")
    kwargs = dict(raw)
    if "tp_rmultiples" in kwargs:
        kwargs["tp_rmultiples"] = tuple(float(v) for v in kwargs["tp_rmultiples"])
    if "k_regime_bounds" in kwargs:
        kwargs["k_regime_bounds"] = tuple(float(v) for v in kwargs["k_regime_bounds"])
    try:
        return LevelsConfig(**kwargs)
    except (TypeError, ValueError) as exc:
        raise LevelsError(f"invalid config_json: {exc}") from exc


def _now() -> str:
    return datetime.now(UTC).isoformat()


def compute_payload(
    df: pl.DataFrame,
    direction: str,
    *,
    pair: str = "UNKNOWN",
    cfg: LevelsConfig | None = None,
    computed_at: str | None = None,
) -> dict:
    """Return the JSON-ready contract dict (full-precision floats)."""
    result = compute_levels(
        df,
        direction,
        cfg,
        pair=pair,
        computed_at=computed_at or _now(),
    )
    return result.as_dict()


def levels_json(
    df: pl.DataFrame,
    direction: str,
    *,
    pair: str = "UNKNOWN",
    cfg: LevelsConfig | None = None,
    computed_at: str | None = None,
) -> str:
    """Serialise the levels contract for a caller-supplied frame."""
    payload = compute_payload(df, direction, pair=pair, cfg=cfg, computed_at=computed_at)
    return json.dumps(payload)


def levels_for_ticker(
    ticker: str,
    direction: str,
    *,
    cache_dir: Path | str | None = None,
    cfg: LevelsConfig | None = None,
    pair: str | None = None,
    computed_at: str | None = None,
) -> str:
    """Convenience path: compute levels from a locally cached ticker CSV.

    Returns a JSON ``{"error": ...}`` envelope (never raises) when the ticker is
    not cached, so an agent can fall back to supplying ``ohlc_json`` itself.
    """
    from digiquant.data.prices.history_cache import load_cached

    df = load_cached(ticker, cache_dir) if cache_dir is not None else load_cached(ticker)
    if df is None:
        return json.dumps({"error": f"no cached OHLC for {ticker!r}; pass ohlc_json instead"})
    return levels_json(
        df,
        direction,
        pair=pair or ticker,
        cfg=cfg,
        computed_at=computed_at,
    )


__all__ = [
    "compute_payload",
    "config_from_json",
    "levels_for_ticker",
    "levels_json",
    "parse_ohlc",
]
