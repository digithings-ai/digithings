#!/usr/bin/env python3
"""Compare the Pine-faithful backtest against a TradingView "List of Trades" export.

This is the trade-level parity oracle: it runs ``pine_backtest.run_backtest`` on the
same OHLCV the TradingView chart used (Coinbase daily), then matches our entries to
TradingView's entry rows by date + direction. Results are broken down by signal family
(MR vs Trend vs Reversal) so an indicator regression is easy to localize — e.g. a DPSD
divergence shows up as missed *Trend* entries while MR entries stay matched.

Usage:
    python scripts/validation/compare_tv.py <strategy> <ohlcv_csv> <tv_export_csv> [start_date]

Example:
    python scripts/validation/compare_tv.py btc_slapper \
        digiquant/data/price-history/BTC-USD.csv \
        ~/Downloads/BTC_Slapper_COINBASE_BTCUSD_2026-06-24_3891a.csv
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pine_backtest import SlapperParams, run_backtest  # noqa: E402


def parse_tv_entries(path: str | Path) -> list[dict]:
    """Return one dict per ENTRY row: {date, direction, signal}.

    TradingView lists every trade as an Exit row followed by an Entry row; we keep
    only entries. The BOM-prefixed header is handled via utf-8-sig.
    """
    entries: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            typ = (r.get("Type") or "").strip().lower()
            if not typ.startswith("entry"):
                continue
            entries.append(
                {
                    "date": (r.get("Date and time") or "").strip()[:10],
                    "direction": "long" if "long" in typ else "short",
                    "signal": (r.get("Signal") or "").strip(),
                }
            )
    return entries


def _family(label: str) -> str:
    low = label.lower()
    if "reversal" in low:
        return "reversal"
    if "trend" in low and "mr" in low:
        return "mr+trend"
    if "trend" in low:
        return "trend"
    return "mr"


def compare(strategy: str, ohlcv_csv: str | Path, tv_export_csv: str | Path,
            start_date: str | None = None) -> dict:
    """Run the parity check and return a structured result (no printing).

    Keys: strategy, tv_entries, our_entries, matched, match_pct, wrong_direction,
    tv_only (missed) and ours_only (extra), each as a list of {date,direction,signal}.
    """
    out = run_backtest(strategy, ohlcv_csv, start_date=start_date)
    ours = [{"date": t.entry_date, "direction": t.direction, "signal": t.entry_label} for t in out.trades]
    tv_entries = parse_tv_entries(tv_export_csv)
    ours_by_date = {e["date"]: e for e in ours}
    tv_by_date = {e["date"]: e for e in tv_entries}

    matched, wrong_dir = [], []
    for d, tv_e in tv_by_date.items():
        if d in ours_by_date:
            (matched if ours_by_date[d]["direction"] == tv_e["direction"] else wrong_dir).append(d)

    tv_only = sorted(d for d in tv_by_date if d not in ours_by_date)
    ours_only = sorted(d for d in ours_by_date if d not in tv_by_date)
    return {
        "strategy": strategy,
        "tv_entries": len(tv_entries),
        "our_entries": len(ours),
        "matched": len(matched),
        "match_pct": round(len(matched) / len(tv_entries) * 100, 2) if tv_entries else 0.0,
        "wrong_direction": wrong_dir,
        "tv_only": [tv_by_date[d] for d in tv_only],
        "ours_only": [ours_by_date[d] for d in ours_only],
    }


def main() -> None:
    if len(sys.argv) < 4:
        print("usage: compare_tv.py <strategy> <ohlcv_csv> <tv_export_csv> [start_date]")
        raise SystemExit(2)
    strategy, ohlcv, tv = sys.argv[1], sys.argv[2], sys.argv[3]
    start_date = sys.argv[4] if len(sys.argv) > 4 else None

    p = SlapperParams.from_registry(strategy)
    print(
        f"resolved params: dema_length={p.dpsd_dema_length} src={p.dpsd_dema_src} "
        f"pct={p.dpsd_percentile_type} sd={p.dpsd_sd_length} ema={p.dpsd_ema_length} "
        f"adf_lookback={p.adf_lookback} adf_ma={p.adf_ma_type} bb_len={p.bb_length}"
    )
    r = compare(strategy, ohlcv, tv, start_date)
    print(f"\n{strategy}: TV entries={r['tv_entries']}  ours={r['our_entries']}")
    print(f"  matched (date+dir): {r['matched']}/{r['tv_entries']} = {r['match_pct']:.1f}%")
    if r["wrong_direction"]:
        print(f"  same date, wrong direction: {len(r['wrong_direction'])} -> {r['wrong_direction']}")
    miss_fam = Counter(e["signal"] for e in r["tv_only"])
    extra_fam = Counter(e["signal"] for e in r["ours_only"])
    print(f"  TV-only (we missed): {len(r['tv_only'])} by signal -> {dict(miss_fam)}")
    for e in r["tv_only"]:
        print(f"      - {e['date']}  {e['direction']:5s}  {e['signal']}")
    print(f"  ours-only (extra): {len(r['ours_only'])} by signal -> {dict(extra_fam)}")
    for e in r["ours_only"]:
        print(f"      + {e['date']}  {e['direction']:5s}  {e['signal']}")


if __name__ == "__main__":
    main()
