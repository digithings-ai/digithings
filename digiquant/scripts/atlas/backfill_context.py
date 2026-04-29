#!/usr/bin/env python3
"""
backfill_context.py — Generate structured "as-of date" research context from Supabase.

Outputs a JSON object with prices, technicals, macro data, and prior snapshot
context that an agent can use as numerical ground-truth for a historical
simulation, WITHOUT forward-looking data contamination.

All queries are bounded to date <= AS_OF_DATE so the agent sees exactly what
would have been available in the DB at close of business on that date.

Usage:
    python3 scripts/backfill_context.py --date 2026-04-07
    python3 scripts/backfill_context.py --date 2026-04-07 --out data/backfill-context/2026-04-07.json
    python3 scripts/backfill_context.py --date 2026-04-07 --print-prompt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

ROOT = Path(__file__).parent.parent

# Key portfolio tickers to always include
CORE_TICKERS = ["SPY", "QQQ", "IWM", "GLD", "IAU", "BIL", "SHY", "TLT",
                "XLE", "XLP", "XLV", "XLK", "XLF", "XLI", "XLC", "XLU",
                "XLB", "XLRE", "XLY", "DBO", "HYG", "UUP", "EEM", "EFA",
                "IBIT", "VIX"]


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL + SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def fetch_context(as_of_date: str) -> dict[str, Any]:
    sb = _sb()

    # ── 1. Latest price_technicals on or before as_of_date ────────────────────
    # Anchor on SPY to find the latest US equity trading day (avoids crypto-only weekend dates)
    res = (
        sb.table("price_technicals")
        .select("date")
        .lte("date", as_of_date)
        .eq("ticker", "SPY")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    latest_price_date = None
    rows = getattr(res, "data", None) or []
    if rows:
        latest_price_date = str(rows[0]["date"])[:10]
    else:
        # Fallback: any ticker
        res2 = (
            sb.table("price_technicals")
            .select("date")
            .lte("date", as_of_date)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        r2 = getattr(res2, "data", None) or []
        if r2:
            latest_price_date = str(r2[0]["date"])[:10]

    prices: list[dict] = []
    if latest_price_date:
        res2 = (
            sb.table("price_history")
            .select("ticker,date,open,high,low,close,volume")
            .eq("date", latest_price_date)
            .in_("ticker", CORE_TICKERS)
            .execute()
        )
        ph_rows = {r["ticker"]: r for r in (getattr(res2, "data", None) or [])}

        res3 = (
            sb.table("price_technicals")
            .select("ticker,date,sma_20,sma_50,sma_200,rsi_14,macd,macd_signal,macd_hist,"
                    "roc_5,roc_21,bb_pct_b,zscore_50,zscore_200,atr_pct,hist_vol_21,adx_14")
            .eq("date", latest_price_date)
            .in_("ticker", CORE_TICKERS)
            .execute()
        )
        for r in getattr(res3, "data", None) or []:
            tk = r["ticker"]
            ph = ph_rows.get(tk, {})
            prices.append({
                "ticker": tk,
                "date": str(r["date"])[:10],
                "close": ph.get("close"),
                "open": ph.get("open"),
                "high": ph.get("high"),
                "low": ph.get("low"),
                "volume": ph.get("volume"),
                "sma_20": r.get("sma_20"),
                "sma_50": r.get("sma_50"),
                "sma_200": r.get("sma_200"),
                "rsi_14": r.get("rsi_14"),
                "macd": r.get("macd"),
                "macd_signal": r.get("macd_signal"),
                "roc_5": r.get("roc_5"),
                "roc_21": r.get("roc_21"),
                "bb_pct_b": r.get("bb_pct_b"),
                "zscore_50": r.get("zscore_50"),
                "atr_pct": r.get("atr_pct"),
                "hist_vol_21": r.get("hist_vol_21"),
            })
    prices.sort(key=lambda x: x["ticker"])

    # ── 2. Macro series (FRED, Frankfurter, crypto F&G, Treasury) ─────────────
    macro_series: dict[str, Any] = {}
    res4 = (
        sb.table("macro_series_observations")
        .select("series_id,source,obs_date,value,unit,meta")
        .lte("obs_date", as_of_date)
        .order("obs_date", desc=True)
        .limit(300)
        .execute()
    )
    seen: set[str] = set()
    for r in getattr(res4, "data", None) or []:
        key = f"{r['source']}:{r['series_id']}"
        if key not in seen:
            seen.add(key)
            macro_series[key] = {
                "series_id": r["series_id"],
                "source": r["source"],
                "obs_date": str(r["obs_date"])[:10],
                "value": r["value"],
                "unit": r.get("unit"),
                "meta": r.get("meta"),
            }

    # ── 3. Prior snapshot (for continuity / delta chaining) ───────────────────
    prior_snapshot: dict | None = None
    prior_date: str | None = None
    res5 = (
        sb.table("daily_snapshots")
        .select("date,run_type,baseline_date,snapshot")
        .lt("date", as_of_date)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    prior_rows = getattr(res5, "data", None) or []
    if prior_rows:
        prior_date = str(prior_rows[0]["date"])[:10]
        prior_snapshot = prior_rows[0].get("snapshot")

    # ── 4. Latest baseline for the week ──────────────────────────────────────
    baseline_snapshot: dict | None = None
    baseline_date: str | None = None
    res6 = (
        sb.table("daily_snapshots")
        .select("date,snapshot")
        .eq("run_type", "baseline")
        .lte("date", as_of_date)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    bl_rows = getattr(res6, "data", None) or []
    if bl_rows:
        baseline_date = str(bl_rows[0]["date"])[:10]
        baseline_snapshot = bl_rows[0].get("snapshot")

    return {
        "as_of_date": as_of_date,
        "latest_price_date": latest_price_date,
        "prior_snapshot_date": prior_date,
        "baseline_date": baseline_date,
        "prices": prices,
        "macro_series": macro_series,
        "prior_snapshot": prior_snapshot,
        "baseline_snapshot": baseline_snapshot,
    }


def _format_price_table(prices: list[dict]) -> str:
    lines = ["| Ticker | Close | RSI14 | SMA20 | SMA50 | SMA200 | MACD | ROC5% | ROC21% | ZScore50 |"]
    lines.append("|--------|-------|-------|-------|-------|--------|------|-------|--------|----------|")
    for p in prices:
        def _f(v, fmt=".2f"):
            return f"{float(v):{fmt}}" if v is not None else "—"
        lines.append(
            f"| {p['ticker']} | {_f(p['close'])} | {_f(p['rsi_14'])} | "
            f"{_f(p['sma_20'])} | {_f(p['sma_50'])} | {_f(p['sma_200'])} | "
            f"{_f(p['macd'])} | {_f(p['roc_5'])} | {_f(p['roc_21'])} | {_f(p['zscore_50'])} |"
        )
    return "\n".join(lines)


def _format_macro_section(macro_series: dict) -> str:
    lines: list[str] = []
    # Treasury yields
    treasury_keys = [(k, v) for k, v in macro_series.items()
                     if v["source"] in ("us_treasury", "treasury_market")]
    if treasury_keys:
        lines.append("**Treasury Yields (as-of):**")
        for _, v in sorted(treasury_keys, key=lambda x: x[0]):
            lines.append(f"  {v['series_id']} ({v['source']}): {v['value']} — {v['obs_date']}")
    # FRED
    fred_keys = [(k, v) for k, v in macro_series.items() if v["source"] == "fred"]
    if fred_keys:
        lines.append("\n**FRED series (latest obs on/before as-of date):**")
        for _, v in sorted(fred_keys, key=lambda x: x[1]["series_id"]):
            lines.append(f"  {v['series_id']}: {v['value']} {v.get('unit','') or ''} — {v['obs_date']}")
    # FX
    fx_keys = [(k, v) for k, v in macro_series.items() if v["source"] == "frankfurter"]
    if fx_keys:
        lines.append("\n**FX rates vs USD (Frankfurter):**")
        for _, v in sorted(fx_keys, key=lambda x: x[1]["series_id"]):
            lines.append(f"  {v['series_id']}: {v['value']} — {v['obs_date']}")
    # Crypto F&G
    fng_keys = [(k, v) for k, v in macro_series.items() if v["source"] == "crypto_fear_greed"]
    if fng_keys:
        lines.append("\n**Crypto Fear & Greed:**")
        for _, v in fng_keys:
            meta = v.get("meta") or {}
            label = meta.get("value_classification", "") if isinstance(meta, dict) else ""
            lines.append(f"  F&G Index: {v['value']} ({label}) — {v['obs_date']}")
    return "\n".join(lines)


def build_agent_prompt(ctx: dict) -> str:
    """Build the Claude-style research prompt for a backfill day."""
    as_of = ctx["as_of_date"]
    from datetime import date as _date
    d = _date.fromisoformat(as_of)
    dow = d.strftime("%A")  # Monday, Tuesday, ...
    run_type = "WEEKLY BASELINE" if dow == "Sunday" else "DAILY DELTA"
    baseline = ctx.get("baseline_date") or "none"
    prior_d = ctx.get("prior_snapshot_date") or "none"

    lines = [
        f"# digiquant-atlas — Backfill Research Session",
        f"",
        f"**Simulated date:** {as_of} ({dow})",
        f"**Run type:** {run_type}",
        f"**Prior snapshot:** {prior_d}",
        f"**Week baseline anchor:** {baseline}",
        f"",
        f"## ⚠️  As-of Date Constraints (MANDATORY)",
        f"",
        f"This is a **historical simulation** placed at {as_of}.",
        f"You MUST treat today as {as_of} and apply these constraints:",
        f"",
        f"1. **Prices / technicals / macro**: use only the data provided in the",
        f"   \"Supabase Data Layer\" section below (already filtered to <= {as_of}).",
        f"   Do NOT query live prices or technicals from Supabase directly.",
        f"",
        f"2. **Web research**: when searching for news, catalysts, or analyst opinions,",
        f"   **add a date bound to every search query**:",
        f"   - Preferred: `before:{as_of}` or `until:{as_of}` syntax",
        f"   - Accept only articles/sources with clear publication dates <= {as_of}",
        f"   - Flag any source without a clear timestamp as *low-confidence* and",
        f"     exclude forward-looking content (e.g. earnings previews for dates > {as_of})",
        f"",
        f"3. **Continuity context**: the prior snapshot (below) is your ONLY source of",
        f"   carry-forward state. Do not load the current Supabase `daily_snapshots` table.",
        f"",
        f"4. **Memory files**: use memory/*.ROLLING.md entries with dates <= {as_of} only.",
        f"",
        f"## Supabase Data Layer (as of {ctx.get('latest_price_date', as_of)})",
        f"",
        f"*(All values sourced from price_history + price_technicals filtered to",
        f"latest available date on/before {as_of})*",
        f"",
        f"### Price & Technical Indicators",
        f"",
        _format_price_table(ctx.get("prices", [])),
        f"",
        f"### Macro Series",
        f"",
        _format_macro_section(ctx.get("macro_series", {})),
        f"",
        f"## Prior Snapshot Context ({prior_d})",
        f"",
    ]

    prior = ctx.get("prior_snapshot")
    if prior and isinstance(prior, dict):
        r = prior.get("regime", {})
        p = prior.get("portfolio", {})
        lines += [
            f"**Prior regime:** {r.get('bias','?')} — {r.get('label','?')}",
            f"**Prior posture:** {p.get('posture','?')} / Cash: {p.get('cash_pct','?')}%",
            f"**Prior positions:**",
        ]
        for pos in p.get("positions", []):
            lines.append(f"  - {pos.get('ticker')} {pos.get('weight_pct')}% — {pos.get('action')} ({pos.get('rationale','')})")
        lines.append(f"**Prior theses:**")
        for th in prior.get("theses", []):
            lines.append(f"  - {th.get('id')} {th.get('name')} [{th.get('status')}]")
        lines.append("")
        lines.append("**Prior actionable items:**")
        for item in prior.get("actionable", [])[:5]:
            lines.append(f"  - {item}")
    else:
        lines.append("*(No prior snapshot found — this is the first run)*")

    lines += [
        f"",
        f"## Task",
        f"",
    ]
    if run_type == "WEEKLY BASELINE":
        lines += [
            f"Follow `cowork/tasks/research-weekly-baseline.md` for {as_of}.",
            f"Read `skills/weekly-baseline/SKILL.md` and run the full baseline pipeline.",
            f"Produce a complete digest snapshot JSON matching `templates/digest-snapshot-schema.json`.",
            f"",
            f"Then follow `cowork/tasks/portfolio-pm-rebalance.md` for {as_of}.",
            f"Publish all Track B artifacts to Supabase with the standard document keys.",
            f"",
            f"Close out: `python3 scripts/run_db_first.py --date {as_of} --validate-mode pm`",
        ]
    else:
        lines += [
            f"Follow `cowork/tasks/research-daily-delta.md` for {as_of}.",
            f"Load the baseline snapshot from {baseline} and produce a delta-request JSON.",
            f"Materialize with `scripts/materialize_snapshot.py --date {as_of} --baseline-date {prior_d} --ops-json ...`",
            f"",
            f"Then follow `cowork/tasks/portfolio-pm-rebalance.md` for {as_of}.",
            f"Publish all Track B artifacts to Supabase with the standard document keys.",
            f"",
            f"Close out: `python3 scripts/run_db_first.py --date {as_of} --validate-mode pm`",
        ]
    lines += [
        f"",
        f"---",
        f"*(End of backfill prompt for {as_of})*",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate as-of date research context from Supabase.")
    ap.add_argument("--date", required=True, help="As-of date (YYYY-MM-DD)")
    ap.add_argument("--out", default=None, help="Write context JSON to file")
    ap.add_argument("--print-prompt", action="store_true", help="Print agent prompt to stdout")
    args = ap.parse_args()

    try:
        ctx = fetch_context(args.date)
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ Context written to {args.out}")

    if args.print_prompt:
        print(build_agent_prompt(ctx))
    elif not args.out:
        print(json.dumps(ctx, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
