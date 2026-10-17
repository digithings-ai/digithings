#!/usr/bin/env python3
"""OWNER DELIVERABLE — per-indicator z tearsheet + pass list for Plan 19 (#4804).

What this renders (and only this): every wired indicator's **manipulated and
z-scored** series at its own best-fit parameters, plus the plain list of which
indicators passed. It is the visual half of
``.scratch/gold_indicator_fits.json`` (Task 1) and
``.scratch/gold_indicator_selection.json`` (Task 2); **every number printed or
written below is read from those two files or recomputed with the SAME shipped
functions and verified against them** — nothing is retyped from memory. The
recomputation is a VERIFY step, not a second fit: the rebuilt z vectors are
scored with the identical frozen ``separation`` metric and each value is
asserted equal to the stored one before it is rendered.

THE ANSWER (Ruling 2, anchor-inclusive): the equal-weight greedy selection kept
**nothing**. The base is the no-trend anchor ``{valuation: 1.0}`` on rolling90 /
z1.0 rails (separation +3.8113) and every fitted leg's addition LOWERS the
aggregate (-0.21 .. -1.39). So the pass list is one line::

    PASS: valuation anchor only — no indicator added

The book on this tearsheet is therefore the ANCHOR ALONE: equal weight
``{valuation: 1.0}``, no extras. That is the Ruling-2 render — the anchor is
in the aggregate, not excluded from it. No extras-only reading appears anywhere
(it would be a NEW model, not a selection result).

Every fitted indicator still gets a curve, labelled with its own fitted
parameters, its separation, its per-side shares and its verdict, so the owner
can see HOW each leg was manipulated and standardized — including the two
degenerate oscillator passes (listed separately, never in a keep list) and the
two unscoreable credit legs (listed with their reason, never silently skipped).

Windows as markers: the tearsheet schema (1.4) has **no window-overlay slot** —
``fill_markers`` is one marker per actual fill (``daily_trade_usd``), so writing
cycle windows there would be a lie. The pinned ``SdcaCycleWindows.gold_v1()``
±45d windows are shaded in ``plot_gold_indicator_fits.py`` (one panel per leg,
buy/trough green, sell/peak red) and named in the notes here.

Curve shape: the anchor book is run through the shipped CI-only curve
simulator with the v4 gated shape read as-is from
``.scratch/gold_curve_search_v4.json`` (``gated_shape``; NOT re-searched here —
the shape is not this plan's subject). The equity curve is a full-history
diagnostic, not a NautilusTrader ``BacktestResult`` and not an OOS gate.

Research-only. Writes UNTRACKED outputs only:
``.scratch/gold_indicator_tearsheet.json`` plus a public/ copy for the preview
server. Never pushed to Supabase; ``settings.json`` and every validated-candidate
section are untouched.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/build_gold_indicator_tearsheet.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date as date_cls
from pathlib import Path
from typing import Any

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.chart_series import SdcaCurveKnees
from digiquant.strategies.sdca.composite_risk import z_to_risk
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    dca_current_signal,
    tearsheet_overlays,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.walk_forward import shape_from_params
from digiquant.tearsheet_data import from_nautilus_run

# Task 1's harness is a sibling research script (never a package). Put this
# directory on the path so the z vectors and the frozen `separation` metric are
# the SAME code the fits file was produced with — no reimplementation here.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fit_gold_indicators import (  # noqa: E402 — sibling research script, path set above
    DATA_PATH,
    EQUAL_WEIGHT,
    SYMBOL,
    aggregate_z,
    anchor_z,
    build_z,
    separation,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
FITS_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_indicator_fits.json"
SELECTION_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_indicator_selection.json"
SHAPE_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search_v4.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_indicator_tearsheet.json"
PUBLIC_STRATEGIES = DIGIQUANT_ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"

SLUG = "gold_sdca_indicator_fit"
LABEL = "GLD-SDCA (indicator-fit pass list — valuation anchor only)"

# Display constants only -- nothing published is touched by this script.
INITIAL_CASH = 1000.0
TRADE_START = date_cls(2010, 1, 1)

# Ruling 2's verbatim pass list. Single source of truth for this artifact.
PASS_LIST = "PASS: valuation anchor only — no indicator added"

# Frozen-task tolerance: every rebuilt number must equal the stored one to this
# absolute delta or the build REFUSES (a silent drift is the whole risk here).
VERIFY_TOL = 1e-9

_HOLDOUT_ABSENT = (
    "HOLDOUT ABSENT by design: no out-of-sample / Stage-B gate was run, scored or "
    "reported in this artifact. The holdout stays spent and untouched; nothing here "
    "is a performance claim."
)


def _params_text(params: Mapping[str, int]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(params.items()))


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value:+.4f}"


def pinned_windows(fits: Mapping[str, Any], selection: Mapping[str, Any]) -> SdcaCycleWindows:
    """The pinned scoring windows — read off BOTH artifacts, never re-pinned here.

    The files carry the pins as a LABEL, so the label is asserted against the
    factory this plan froze and against each other before the factory is used.
    """
    windows = SdcaCycleWindows.gold_v1()
    label = f"{windows.__class__.__name__}.gold_v1()"
    for artifact, name in ((fits, FITS_PATH.name), (selection, SELECTION_PATH.name)):
        if not str(artifact["windows"]).startswith(label):
            raise AssertionError(
                f"{name} pins are {artifact['windows']!r}, expected {label} — refusing "
                "to render a different pin set than the fits were scored on"
            )
    return windows


def _display_params(fits_row: Mapping[str, Any]) -> tuple[str, Mapping[str, int]]:
    """(label params, params) for one indicator's rendered curve.

    A SCORED leg renders at its ``best_overall`` params (the fitted point, tie
    broken to the shorter window). An UNSCOREABLE leg has no fit at all, so it
    renders at its FIRST grid row and says so — the curve is shown so the owner
    can see the series exists and where it starts, never as a fitted result.
    """
    fit = fits_row
    best = fit.get("best_overall")
    if best is not None:
        return _params_text(best["params"]), dict(best["params"])
    first = (fit.get("rows") or [{}])[0]
    return f"{_params_text(first.get('params') or {})} (FIRST grid row — NO FIT)", dict(
        first.get("params") or {}
    )


def _curve_from_z(
    *,
    name: str,
    display_name: str,
    dates: Sequence[str],
    z_values: Sequence[float | None],
    weight: float,
) -> dict[str, Any]:
    """One ``TearsheetIndicatorCurve`` on the 0–100 risk scale (the schema's map).

    Null z days are dropped rather than zero-filled (same rule as the shipped
    ``indicator_curve_from_z``), so a warm-up gap reads as a gap.
    """
    points: list[dict[str, float | str]] = []
    for day, z in zip(dates, z_values, strict=True):
        if z is None:
            continue
        value = float(z)
        if value != value:  # NaN
            continue
        points.append({"t": day, "v": z_to_risk(value)})
    return {
        "name": name,
        "display_name": display_name,
        "weight": float(weight),
        "in_index": float(weight) > 0.0,
        "points": points,
    }


def _fits_table_lines(fits: Mapping[str, Any]) -> list[str]:
    lines = [
        "FITTED INDICATORS — every wired leg at ITS OWN best-fit parameters "
        "(name | fitted params | separation | shares | verdict):",
    ]
    for name, fit in fits["indicators"].items():
        best = fit.get("best_overall")
        params, _ = _display_params(fit)
        if best is None:
            lines.append(
                f"  {name} | {params} | separation — | shares — | "
                f"{fit['verdict']} ({fit.get('reason')})"
            )
            continue
        shares = (
            f"peak<0 {best['peak_negative_share']:.3f} / "
            f"trough>0 {best['trough_positive_share']:.3f} / "
            f"zero {best['zero_z_share']:.3f}"
        )
        flag = " DEGENERATE" if best.get("degenerate") else ""
        lines.append(
            f"  {name} | {params} | separation {_signed(best['separation'])} | "
            f"{shares} | {fit['verdict']}{flag}"
        )
    return lines


def _delta_table_lines(selection: Mapping[str, Any]) -> list[str]:
    lines = [
        "KEEP/DROP DELTA TABLE — candidate | Δ aggregate separation (frozen rule: "
        "keep iff the aggregate STRICTLY improves):",
    ]
    for step in selection["delta_table"]:
        lines.append(
            f"  {step['name']} ({_params_text(step['params'])}) | individual "
            f"{_signed(step['individual_separation'])} | aggregate "
            f"{_signed(step['aggregate_before'])} -> {_signed(step['aggregate_after'])} | "
            f"delta {_signed(step['delta'])} | scored_days "
            f"{step['scored_days_before']} -> {step['scored_days_after']} "
            f"({step['days_delta']:+d}) | {'KEEP' if step['kept'] else 'DROP'}"
        )
    lines.append(
        f"  anchor alone | aggregate {_signed(selection['anchor']['aggregate_separation'])} "
        f"| scored_days {selection['anchor']['scored_days']} | KEPT BY DEFAULT"
    )
    cross = selection["cross_check"]
    lines.append(
        f"  cross-check (equal weight over anchor + EVERY non-degenerate passer, no "
        f"greedy pruning; report-only) | members {cross['members']} | aggregate "
        f"{_signed(cross['separation'])} | used_for_selection=False"
    )
    return lines


def build_notes(fits: Mapping[str, Any], selection: Mapping[str, Any]) -> list[str]:
    """Every honesty statement this artifact owes the reader, as tearsheet notes."""
    degenerate = [entry["name"] for entry in selection["degenerate_owner_review"]]
    unscoreable = fits["unscoreable"]
    return [
        f"{PASS_LIST} — the equal-weight greedy selection (frozen rule) kept "
        f"{len(selection['kept'])} of {len(selection['delta_table'])} candidate legs. "
        f"Base = the no-trend anchor {{valuation: 1.0}} on rolling90/z1.0 rails, "
        f"separation {_signed(selection['anchor']['aggregate_separation'])}; adding ANY "
        "fitted leg lowers it, so the anchor alone is the book on this tearsheet. "
        "Anchor-inclusive read (Ruling 2): the anchor is IN the aggregate, not "
        "excluded from it; an extras-only composite is NOT reported here because it "
        "would be a NEW model, not a selection result.",
        *_fits_table_lines(fits),
        *_delta_table_lines(selection),
        f"Degenerate oscillator passes, listed SEPARATELY and never counted in a keep "
        f"list without an explicit owner look: {degenerate} — their positive "
        "separation rests on one window side never leaving the +/-0.06 dead zone.",
        "Unscoreable (listed with a reason, never silently skipped): "
        + "; ".join(f"{entry['name']} — {entry['reason']}" for entry in unscoreable),
        fits["in_sample_label"],
        _HOLDOUT_ABSENT,
        f"Metric: {fits['metric']}. {fits['metric_read']}",
        "Windows on this tearsheet: the pinned SdcaCycleWindows.gold_v1() +/-45d "
        "windows are shaded per leg in gold_indicator_fits.svg (green = trough/buy, "
        "red = peak/sell). The tearsheet schema (1.4) has NO window-overlay slot — "
        "fill_markers is one marker per actual fill — so the windows are NOT faked "
        "into it here.",
        f"Curve shape: the v4 gated shape read as-is from {SHAPE_PATH.name} "
        "(buy 35/45, sell 65/10); NOT re-searched — the shape is not this plan's "
        f"subject. Equity curve = full-history shipped curve-simulator diagnostic "
        f"(sdca/backtest.py, CI-only parity harness), initial cash ${INITIAL_CASH:,.0f} "
        f"from {TRADE_START}. Not a NautilusTrader BacktestResult, not an OOS gate.",
        "Research-only. Untracked artifact; never pushed to Supabase; settings.json "
        "and every validated-candidate section untouched. Rule change or a "
        "down-weighted leg is an OWNER call for the later weight-optimization plan.",
    ]


def print_pass_list(fits: Mapping[str, Any], selection: Mapping[str, Any]) -> None:
    """The owner's plain answer, then the fits table, then the drop-delta table."""
    print("")
    print(PASS_LIST)
    print(
        f"kept {len(selection['kept'])} of {len(selection['delta_table'])} candidate "
        f"legs | anchor separation "
        f"{_signed(selection['anchor']['aggregate_separation'])} | final members "
        f"{selection['final']['members']}"
    )
    print("")
    print("FITTED INDICATORS")
    print(
        f"{'indicator':<14} {'fitted params':<40} {'separation':>10} "
        f"{'peak<0':>7} {'trough>0':>9} {'zero':>6}  verdict"
    )
    for name, fit in fits["indicators"].items():
        best = fit.get("best_overall")
        params, _ = _display_params(fit)
        if best is None:
            print(f"{name:<14} {params:<40} {'—':>10} {'—':>7} {'—':>9} {'—':>6}  {fit['verdict']}")
            continue
        print(
            f"{name:<14} {params:<40} {best['separation']:>+10.4f} "
            f"{best['peak_negative_share']:>7.3f} {best['trough_positive_share']:>9.3f} "
            f"{best['zero_z_share']:>6.3f}  {fit['verdict']}"
        )
    print("")
    print("DROP DELTA TABLE (candidate | Δ aggregate)")
    print(
        f"{'#':>2} {'candidate':<13} {'params':<40} {'own_sep':>9} "
        f"{'before':>9} {'after':>9} {'delta':>9} {'days':>12}  verdict"
    )
    for step in selection["delta_table"]:
        print(
            f"{step['step']:>2} {step['name']:<13} {_params_text(step['params']):<40} "
            f"{step['individual_separation']:>+9.4f} "
            f"{_signed(step['aggregate_before']):>9} {_signed(step['aggregate_after']):>9} "
            f"{_signed(step['delta']):>9} "
            f"{step['scored_days_before']:>5}->{step['scored_days_after']:<6}"
            f"  {'KEEP' if step['kept'] else 'DROP'}"
        )
    print("")
    print(fits["in_sample_label"])
    print(_HOLDOUT_ABSENT)


def main() -> int:
    if not FITS_PATH.exists() or not SELECTION_PATH.exists():
        raise FileNotFoundError(
            f"{FITS_PATH} and {SELECTION_PATH} must both exist — run "
            "fit_gold_indicators.py --fit then --select first"
        )
    fits = json.loads(FITS_PATH.read_text())
    selection = json.loads(SELECTION_PATH.read_text())
    shape_doc = json.loads(SHAPE_PATH.read_text())
    shape = shape_from_params(shape_doc["gated_shape"])

    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    windows = pinned_windows(fits, selection)

    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(
        f"pins: {len(windows.troughs())} trough (buy) / {len(windows.peaks())} peak "
        f"(sell) windows, ±45d — {fits['windows']}"
    )

    # ---- rebuild each leg's manipulated z at its fitted params ----------------
    # Rebuild only: the params come from the fits file, and every rebuilt score
    # is asserted against the stored one before anything is rendered.
    indicator_z: dict[str, list[float | None]] = {}
    curves: list[dict[str, Any]] = []
    verification: list[tuple[str, float, float]] = []
    for name, fit in fits["indicators"].items():
        params_label, params = _display_params(fit)
        z = build_z(name, params, date_s, price_s, sources)
        indicator_z[name] = z
        stored = fit.get("best_overall")
        if stored is not None:
            score = separation(dates, z, windows).separation
            verification.append((name, float(stored["separation"]), float(score or 0.0)))
        verdict = fit["verdict"]
        display = f"{name} ({params_label}) — {verdict}"
        if stored is not None:
            display = f"{display} — sep {stored['separation']:+.4f}"
        else:
            display = f"{display} — unscoreable, no fit"
        curves.append(
            _curve_from_z(
                name=name,
                display_name=display,
                dates=[str(day) for day in dates],
                z_values=z,
                # Only the ANCHOR is in the index (Ruling 2: nothing was added).
                weight=EQUAL_WEIGHT if name == "valuation" else 0.0,
            )
        )

    drift = [
        (name, stored, rebuilt)
        for name, stored, rebuilt in verification
        if abs(stored - rebuilt) > VERIFY_TOL
    ]
    if drift:
        raise AssertionError(f"rebuilt separations drifted from the fits file: {drift}")
    print(f"verify: {len(verification)} scored legs rebuilt, separation delta <= {VERIFY_TOL}")

    # ---- the anchor aggregate (what the tearsheet actually trades) -----------
    anchor = anchor_z(date_s, price_s)
    anchor_agg = aggregate_z([("valuation", anchor)])
    anchor_sep = separation(dates, anchor_agg, windows).separation
    stored_anchor = float(selection["anchor"]["aggregate_separation"])
    if abs(anchor_sep - stored_anchor) > VERIFY_TOL:
        raise AssertionError(
            f"anchor aggregate separation drifted: stored {stored_anchor} vs rebuilt {anchor_sep}"
        )
    print(f"verify: anchor aggregate separation {anchor_sep:+.4f} == stored {stored_anchor:+.4f}")

    anchor_curve = _curve_from_z(
        name="valuation",
        display_name=(
            f"valuation ({selection['anchor']['form']} rails, rolling "
            f"{selection['anchor']['rolling_window']}d / z {selection['anchor']['rolling_z']}) "
            "— ANCHOR, the only member in the index"
        ),
        dates=[str(day) for day in dates],
        z_values=anchor_agg,
        weight=EQUAL_WEIGHT,
    )

    # ---- anchor-only book: shipped curve simulator, v4 gated shape ------------
    # The anchor's model + index are rebuilt from the SELECTION file's own
    # literals (form / rolling_window / rolling_z / weight), not from constants
    # typed here — the file and this script cannot disagree about the anchor.
    anchor_spec = selection["anchor"]
    model = resolve_sdca_risk_model(
        anchor_spec["form"],
        dates=date_s,
        price=price_s,
        rolling_window=anchor_spec["rolling_window"],
        rolling_z=anchor_spec["rolling_z"],
    )
    index = build_risk_index(
        date_s, price_s, model, extra_indicators=None, valuation_weight=EQUAL_WEIGHT
    )
    risk_all = index["risk"].to_list()
    idx = [i for i, day in enumerate(dates) if day >= TRADE_START]
    if not idx:
        raise ValueError(f"No bars on/after trade_start={TRADE_START}")
    date_w = date_s[idx]
    price_w = price_s[idx]
    risk_w = pl.Series("risk", [risk_all[i] for i in idx], dtype=pl.Float64)

    curve = AccumDistCurve(shape.to_nodes())
    _report, frame = run_backtest(date_w, price_w, risk_w, curve, INITIAL_CASH)

    date_strs = [str(d) for d in frame["date"].to_list()]
    price_vals = frame["price"].to_list()
    risk_vals = frame["risk"].to_list()
    rate_vals = frame["rate"].to_list()
    daily_trade_usd_vals = frame["daily_trade_usd"].to_list()
    net_deployed_vals = frame["net_deployed"].to_list()
    asset_units_vals = frame["asset_units"].to_list()
    portfolio_values = frame["portfolio_value"].to_list()

    dca_block = breakdown_from_daily(
        prices=price_vals,
        portfolio_values=portfolio_values,
        daily_trade_usd=daily_trade_usd_vals,
        net_deployed=net_deployed_vals,
        asset_units=asset_units_vals,
        risk=risk_vals,
        rate=rate_vals,
        initial_cash=INITIAL_CASH,
    )

    rails = model.rails(date_s)
    rail_tuples = [(rails["low"][i], rails["median"][i], rails["high"][i]) for i in idx]
    # No `weights=` here on purpose: the shipped overlay path would rebuild the
    # fixed catalog labels, and this artifact's curves must carry each leg's
    # FITTED params. The overlays below are the rails/risk/book series only.
    overlays = tearsheet_overlays(
        dates=date_strs,
        prices=price_vals,
        daily_trade_usd=daily_trade_usd_vals,
        net_deployed=net_deployed_vals,
        initial_cash=INITIAL_CASH,
        rails=rail_tuples,
        risk=risk_vals,
        asset_units=asset_units_vals,
    )
    overlays["curve_knees"] = SdcaCurveKnees(
        buy_knee_risk=shape.buy_knee_risk,
        sell_knee_risk=shape.sell_knee_risk,
        preset="gold indicator-fit anchor-only diagnostic (v4 gated shape, read as-is)",
    ).model_dump(mode="json")

    signal = dca_current_signal(
        last_date=date_strs[-1],
        last_price=price_vals[-1],
        last_risk=risk_vals[-1],
        last_rate=rate_vals[-1],
        units_accumulated=dca_block.units_accumulated,
    )

    peak, max_dd = INITIAL_CASH, 0.0
    for value in portfolio_values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value - peak) / peak * 100.0)

    summary = {
        "strategy": SLUG,
        "symbol": SYMBOL,
        "period": f"{date_strs[0]} → {date_strs[-1]}",
        "bars": len(date_strs),
        "initial_capital": INITIAL_CASH,
        "final_equity": portfolio_values[-1],
        "net_profit_pct": (portfolio_values[-1] / INITIAL_CASH - 1.0) * 100.0,
        "max_drawdown_pct": max_dd,
        "all": _EMPTY_METRICS,
        "long": _EMPTY_METRICS,
        "short": _EMPTY_METRICS,
    }

    td = from_nautilus_run(
        summary,
        [],
        list(zip(date_strs, portfolio_values, strict=True)),
        data_source=(
            "GLD daily OHLCV (yfinance) -- anchor-only curve-simulator diagnostic "
            "for the Plan-19 indicator-fit pass list; not published"
        ),
        notes=build_notes(fits, selection),
        dca=dca_block,
        current_signal=signal,
        rails=overlays.get("rails"),
        risk_curve=overlays.get("risk_curve"),
        cost_basis_curve=overlays.get("cost_basis_curve"),
        capital_deployed_curve=overlays.get("capital_deployed_curve"),
        lump_equity_curve=overlays.get("lump_equity_curve"),
        flat_dca_equity_curve=overlays.get("flat_dca_equity_curve"),
        allocated_pct_curve=overlays.get("allocated_pct_curve"),
        fill_markers=overlays.get("fill_markers"),
        indicator_curves=[anchor_curve, *curves],
        indicator_weights={"valuation": EQUAL_WEIGHT},
        curve_knees=overlays.get("curve_knees"),
        label=LABEL,
        kind="dca",
        beats_flat_dca_oos=None,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(td.to_json())
    PUBLIC_STRATEGIES.mkdir(parents=True, exist_ok=True)
    public_path = PUBLIC_STRATEGIES / f"{SLUG}.json"
    public_path.write_text(td.to_json())

    print("")
    print(f"wrote {OUT_PATH}  ({OUT_PATH.stat().st_size} bytes)")
    print(f"wrote {public_path}  ({public_path.stat().st_size} bytes)")
    print(
        f"indicator_curves: {len(td.indicator_curves or [])} (1 anchor + "
        f"{len(curves)} fitted legs)  indicator_weights={{valuation: {EQUAL_WEIGHT}}}  "
        f"bars={len(portfolio_values)}  fill_sell_days={dca_block.fill_sell_days}"
    )
    print("")
    print_pass_list(fits, selection)
    return 0


_EMPTY_METRICS = {
    "trades": 0,
    "net_profit": 0.0,
    "net_profit_pct": 0.0,
    "gross_profit": 0.0,
    "gross_loss": 0.0,
    "percent_profitable": 0.0,
    "profit_factor": None,
    "avg_trade": 0.0,
    "wins": 0,
    "losses": 0,
}


if __name__ == "__main__":
    raise SystemExit(main())
