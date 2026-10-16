# score:allow pandas
"""Tearsheet report extraction helpers (Nautilus account/fills → series)."""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Any  # score:allow untyped any — tearsheet HTML assembly

import polars as pl


def _load_logo_base64() -> str:
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        logo_path = repo_root / "assets" / "dg_transparent.png"
        if logo_path.exists():
            data = logo_path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/png;base64,{b64}"
    except OSError:
        pass
    return ""


def _parse_balance(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).strip()
    if " " in s:
        s = s.split()[0]
    s = s.replace("_", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _as_polars_frame(report: Any) -> pl.DataFrame | None:
    """Normalize Nautilus pandas reports to Polars at the tearsheet boundary."""
    if report is None:
        return None
    if isinstance(report, pl.DataFrame):
        return report
    try:
        return pl.from_pandas(report)
    except (TypeError, ValueError, ImportError):
        return None


def _extract_equity_curve(account_report: Any) -> tuple[list[str], list[float]]:
    df = _as_polars_frame(account_report)
    if df is None or df.is_empty():
        return [], []
    timestamps: list[str] = []
    balances: list[float] = []
    balance_col = next((c for c in ("total", "balance", "free") if c in df.columns), None)
    if not balance_col:
        return [], []
    for row in df.iter_rows(named=True):
        ts = row.get("ts_event")
        if ts is not None:
            timestamps.append(str(ts))
        total = _parse_balance(row.get(balance_col))
        balances.append(total)
    return timestamps, balances


def _compute_drawdown(balances: list[float]) -> list[float]:
    if not balances:
        return []
    peak = balances[0]
    dd = []
    for b in balances:
        peak = max(peak, b)
        dd.append(((b - peak) / peak * 100) if peak > 0 else 0.0)
    return dd


def _extract_fill_markers(fills_report: Any) -> tuple[list[str], list[float], list[str]]:
    df = _as_polars_frame(fills_report)
    if df is None or df.is_empty():
        return [], [], []
    ts_col = next((c for c in ("ts_event", "ts_last", "ts_init") if c in df.columns), None)
    px_col = next((c for c in ("avg_px", "last_px", "price") if c in df.columns), None)
    side_col = next((c for c in ("order_side", "side") if c in df.columns), None)
    if not ts_col or not px_col:
        return [], [], []
    timestamps: list[str] = []
    prices: list[float] = []
    sides: list[str] = []
    for row in df.iter_rows(named=True):
        ts = row.get(ts_col)
        if ts is not None:
            timestamps.append(str(ts))
        try:
            px = float(str(row.get(px_col, 0)).replace(",", "").replace("_", ""))
        except (ValueError, TypeError):
            px = 0.0
        prices.append(px)
        side = str(row.get(side_col, "")).upper()
        sides.append(side)
    return timestamps, prices, sides


def _get_stat(pnl_dict: dict, returns_dict: dict, general_dict: dict, key: str) -> float | None:
    for d in (pnl_dict, returns_dict, general_dict):
        if key in d:
            v = d[key]
            if isinstance(v, (int, float)) and not math.isnan(v):
                return float(v)
    return None
