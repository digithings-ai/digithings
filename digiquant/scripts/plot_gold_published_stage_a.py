#!/usr/bin/env python3
"""Chart the PUBLISHED gold Stage A keep/drop against the deployed floor and dd cap (#4804).

Reads ``digiquant/.scratch/gold_published_stage_a.json`` — written by
``run_gold_published_stage_a.py`` — and draws what that run decided. It recomputes no
verdict and no metric: every number is read off the artifact, so the figure cannot
disagree with the report.

One SVG, hand-rolled stdlib only (no matplotlib / numpy / pandas — none is installed and
none is needed for a bar chart). It mirrors the ``_text`` / ``_wrap`` / ``_block`` /
hatch-pattern pattern of ``plot_gold_pin_set_fits.py`` so the gold chart family reads as
one family.

**Four panels, and the separation between them is the point of the chart:**

1. **Keep/drop per extra** — horizontal, signed around the valuation-only baseline, with
   a bar RIGHT meaning the leg beat valuation-only in-sample and a bar LEFT meaning it did
   not. Kept legs are solid, no-keep legs are hatched as well as recoloured, so the
   distinction survives greyscale and colour-vision deficiency.
2. **Deployed capital vs the 10% floor** — the recorded peak-deployed share per fold,
   against the floor drawn as a labelled rule.
3. **Drawdown vs the 50% cap** — the recorded drawdown per fold, against the cap drawn as
   a labelled rule.
4. **Out-of-sample, visually separated** — in its own panel, below a heavy divider and
   under its own heading, because it was REPORTED and never used to select. Sharing an
   axis with the in-sample bars would invite exactly the reading the objective forbids.

**The rank did not gate.** Panels 2 and 3 draw the floor and the cap as RAILS to read
against, not as FILTERS that ran: the shipped Stage A argmax is the plain mean in-sample
vs_flat_dca_pct, so a bar past a rail is a recorded fact, not a vetoed row. The footer
says so in substance.

**No performance claim.** The footer states that every in-sample number is a maximum over
the frozen weight grid scored against the same folds, that nothing here is validated
out-of-sample, and that the figure reports metrics and nothing beyond them. A cycle window
is a scoring target, not an execution period — and in any case this objective consumes no
cycle windows at all.

Usage:

    PYTHONPATH=digiquant/src <venv>/bin/python \\
        digiquant/scripts/plot_gold_published_stage_a.py
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / ".scratch" / "gold_published_stage_a.json"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_published_stage_a.svg"

W = 1680
MARGIN_L, MARGIN_R = 214, 250

ROW_H = 30
BAR_H = 13
PANEL_GAP = 58
PANEL2_GAP = 26
DIVIDER_GAP = 54

INK = "#1c1c1c"
MUTED = "#5f5f5f"
GRID = "#ececec"
BOX = "#dcdcdc"
BAND_BG = "#fbfbfb"
# A leg that beat valuation-only in-sample: to the RIGHT, solid.
KEEP_COL = "#2e7d32"
# A leg that earned no keep: to the LEFT of nothing (it sits AT zero), hatched. It is
# recoloured as well as textured so the distinction is not colour-only.
NOKEEP_COL = "#c62828"
FLOOR_COL = "#1565c0"
CAP_COL = "#ef6c00"
OOS_COL = "#6a1b9a"

TITLE = "Gold PUBLISHED Stage A — in-sample vs-flat-DCA keep/drop (NOT vs-lump, NOT Sharpe)"
OOS_TITLE = "OUT-OF-SAMPLE — REPORTED, NEVER USED FOR SELECTION"

FOOTER_LABEL = (
    "IN-SAMPLE, and a SELECTED UPPER BOUND. Every in-sample figure is the MAXIMUM over the "
    "shipped frozen weight grid, scored against the same in-sample folds it was fitted on. "
    "This chart is NOT a performance claim and NOT a validated result: no return, Sharpe or "
    "edge is asserted beyond the metrics the shipped search returned. OOS is printed for "
    "information only — nothing was selected on it."
)


def _text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 11,
    fill: str = INK,
    anchor: str = "start",
    weight: str = "normal",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{escape(text)}</text>'
    )


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def _block(
    x: float,
    y: float,
    text: str,
    *,
    size: int,
    width: int,
    fill: str = INK,
    weight: str = "normal",
    lead: int = 14,
    gap: int = 6,
) -> tuple[str, float]:
    """A wrapped paragraph at a fixed CHARACTER width; returns its bottom y."""
    lines = _wrap(text, width)
    svg = "\n".join(
        _text(x, y + index * lead, line, size=size, fill=fill, weight=weight)
        for index, line in enumerate(lines)
    )
    return svg, y + len(lines) * lead + gap


HATCH_ID = "hatch-nokeep"


def _hatch_def(col: str) -> str:
    return (
        f'<pattern id="{HATCH_ID}" width="6" height="6" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{col}" stroke-width="2.2" '
        f'stroke-opacity="0.85"/></pattern>'
    )


def load_run() -> dict:
    if not JSON_PATH.exists():
        raise SystemExit(
            f"{JSON_PATH} is missing — run run_gold_published_stage_a.py first. This script "
            "draws that run's verdicts; it never recomputes them."
        )
    return json.loads(JSON_PATH.read_text())


# --------------------------------------------------------------------------- #
# Geometry helpers shared by the three rail panels
# --------------------------------------------------------------------------- #


def _axis(
    x0: float,
    top: float,
    width: float,
    height: float,
    *,
    lo: float,
    hi: float,
    ticks: Sequence[float],
    unit: str,
) -> tuple[list[str], float]:
    """A value axis from ``lo`` to ``hi`` with gridlines and labels above the panel."""
    parts: list[str] = []
    span = hi - lo or 1.0

    def to_x(value: float) -> float:
        return x0 + (value - lo) / span * width

    for value in ticks:
        x = to_x(value)
        if x0 - 1 <= x <= x0 + width + 1:
            parts.append(
                f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" '
                f'y2="{top + height:.1f}" stroke="{GRID}"/>'
            )
            parts.append(_text(x, top - 8, f"{value:g}{unit}", size=9, fill=MUTED, anchor="middle"))
    return parts, to_x


def _rail(
    x: float,
    top: float,
    height: float,
    label: str,
    col: str,
) -> str:
    """A labelled threshold drawn as a RAIL — a thing to read against, not a filter."""
    return "\n".join(
        (
            f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{top + height:.1f}" '
            f'stroke="{col}" stroke-width="1.6" stroke-dasharray="6 4"/>',
            _text(x + 5, top + height - 6, label, size=9, fill=col, weight="bold"),
        )
    )


def _dot(
    x: float,
    y: float,
    col: str,
    *,
    filled: bool,
    r: float = 4.0,
) -> str:
    fill = col if filled else "white"
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" '
        f'stroke="{col}" stroke-width="1.6"/>'
    )


# --------------------------------------------------------------------------- #
# Panel 1 — per-extra keep/drop, signed around the baseline
# --------------------------------------------------------------------------- #


def _decide_panel(run: dict, top: float) -> tuple[str, float]:
    rows = run["per_extra"]
    plot_w = W - MARGIN_L - MARGIN_R
    peak = max((abs(r["delta_is_vs_flat_dca_pct"]) for r in rows), default=1.0)
    top_val = max(peak * 1.15, 1e-6)
    zero_x = MARGIN_L + 120.0
    val_to_w = (plot_w - 260.0) / 2.0 / top_val
    height = ROW_H * len(rows)

    parts = [
        _text(
            MARGIN_L,
            top - 30,
            "1 · KEEP / NO-KEEP PER EXTRA — in-sample vs-flat-DCA, against the valuation-only "
            "baseline (bar RIGHT = the leg beat it)",
            size=12,
            weight="bold",
        )
    ]
    grid, to_x = _axis(
        zero_x - 60,
        top,
        plot_w - 200.0,
        height,
        lo=-top_val,
        hi=top_val,
        ticks=[-top_val, -top_val / 2, 0.0, top_val / 2, top_val],
        unit="",
    )
    parts.extend(grid)
    parts.append(
        f'<line x1="{zero_x:.1f}" y1="{top:.1f}" x2="{zero_x:.1f}" '
        f'y2="{top + height:.1f}" stroke="{INK}" stroke-width="1.2"/>'
    )

    worst = {c["name"]: c["worst_window_null_pct"] for c in run["coverage"]}
    worst_when = {c["name"]: c["worst_window"] for c in run["coverage"]}
    for index, row in enumerate(rows):
        y = top + index * ROW_H + ROW_H / 2
        keep = row["decision"] == "keep"
        delta = row["delta_is_vs_flat_dca_pct"]
        width = abs(delta) * val_to_w
        x = zero_x if delta >= 0 else zero_x - width
        colour = KEEP_COL if keep else NOKEEP_COL
        parts.append(_text(MARGIN_L, y + 4, row["name"], size=11))
        parts.append(
            f'<rect x="{x:.1f}" y="{y - BAR_H / 2:.1f}" width="{max(width, 1.0):.1f}" '
            f'height="{BAR_H}" fill="{colour if keep else f"url(#{HATCH_ID})"}" '
            f'stroke="{colour}" stroke-width="1"/>'
        )
        parts.append(
            _text(
                zero_x + (plot_w - 200.0) / 2 + 12,
                y + 4,
                f"IS {row['mean_is_vs_flat_dca_pct']:+.2f}%  (Δ {delta:+.2f}%)  "
                f"weight {row['best_weight']:g}",
                size=10,
                fill=INK if keep else MUTED,
            )
        )
        flag = "in joint sweep" if row["in_joint_sweep"] else "held out (coverage)"
        mark = "✓" if keep else "·"
        parts.append(
            _text(
                W - MARGIN_R,
                y + 4,
                f"{mark} {row['decision']} · {flag} · worst window "
                f"{worst.get(row['name'], 0.0):.1f}% ({worst_when.get(row['name'], '-')})",
                size=9,
                fill=colour,
                anchor="end",
            )
        )
    note_svg, bottom = _block(
        MARGIN_L,
        top + height + 22,
        "NO-KEEP IS NOT A DROP. A one-name sweep shares its grid with the valuation-only row, "
        "so its best can never fall below the baseline: a leg that actively hurts and a leg "
        "that merely does not help are the same observation here, and both read as 'no keep "
        "earned'. For whether the joint winner actually carries a leg, read panel 5.",
        size=10,
        width=150,
        fill=MUTED,
        lead=13,
        gap=2,
    )
    parts.append(note_svg)
    return "\n".join(parts), bottom


# --------------------------------------------------------------------------- #
# Panels 2 and 3 — deployed capital vs the floor, drawdown vs the cap
# --------------------------------------------------------------------------- #


def _run_label(run: dict, row: dict) -> str:
    extras = row["enabled_extras"]
    if not extras:
        return "valuation-only"
    return "val " + " ".join(f"{n} {w:g}" for n, w in extras.items())


def _deployed_panel(run: dict, top: float) -> tuple[str, float]:
    joint = next((r for r in run["runs"] if r["label"] == "joint_sweep"), run["runs"][-1])
    folds = joint["folds"]
    plot_w = W - MARGIN_L - MARGIN_R
    height = ROW_H * len(folds)
    floor = 10.0
    hi = 105.0

    parts = [
        _text(
            MARGIN_L,
            top - 30,
            "2 · DEPLOYED CAPITAL vs THE 10% FLOOR — peak-deployed share per fold, on the "
            "joint-sweep winner",
            size=12,
            weight="bold",
        )
    ]
    grid, to_x = _axis(
        MARGIN_L + 200,
        top,
        plot_w - 250.0,
        height,
        lo=0.0,
        hi=hi,
        ticks=[0.0, 25.0, 50.0, 75.0, 100.0],
        unit="%",
    )
    parts.extend(grid)
    parts.append(_rail(to_x(floor), top, height, "floor 10%", FLOOR_COL))

    for index, fold in enumerate(folds):
        y = top + index * ROW_H + ROW_H / 2
        for label, metrics, offset in (
            ("in-sample", fold["in_sample"], 0.0),
            ("OOS", fold["out_of_sample"], ROW_H / 2),
        ):
            yy = y + offset
            share = metrics["capital_deployed_peak_pct"]
            parts.append(
                f'<line x1="{MARGIN_L + 200:.1f}" y1="{yy:.1f}" '
                f'x2="{to_x(share):.1f}" y2="{yy:.1f}" stroke="{INK}" stroke-width="3"/>'
            )
            parts.append(_dot(to_x(share), yy, INK, filled=True, r=3.4))
        parts.append(_text(MARGIN_L, y + 8, f"fold {fold['fold']}", size=11))
        parts.append(
            _text(
                MARGIN_L + 60,
                y + 8,
                f"IS {fold['in_sample']['capital_deployed_peak_pct']:.1f}% / OOS "
                f"{fold['out_of_sample']['capital_deployed_peak_pct']:.1f}%",
                size=9,
                fill=MUTED,
            )
        )
        parts.append(
            _text(
                W - MARGIN_R,
                y + 8,
                f"feasible flag {fold['feasible']} (recorded, not enforced at Stage A)",
                size=9,
                fill=MUTED,
                anchor="end",
            )
        )
    svg, bottom = _block(
        MARGIN_L,
        top + height + 20,
        "The 10% floor is a RAIL to read against, not a filter that ran: the shipped Stage A "
        "rank is the plain mean in-sample vs_flat_dca_pct and does not gate on it. A fold left "
        "of the rail is a recorded fact, not a vetoed row.",
        size=10,
        width=150,
        fill=MUTED,
        lead=13,
        gap=2,
    )
    parts.append(svg)
    return "\n".join(parts), bottom


def _drawdown_panel(run: dict, top: float) -> tuple[str, float]:
    joint = next((r for r in run["runs"] if r["label"] == "joint_sweep"), run["runs"][-1])
    folds = joint["folds"]
    plot_w = W - MARGIN_L - MARGIN_R
    height = ROW_H * len(folds)
    cap = 50.0
    hi = 55.0

    parts = [
        _text(
            MARGIN_L,
            top - 30,
            "3 · DRAWDOWN vs THE 50% CAP — per fold, on the joint-sweep winner",
            size=12,
            weight="bold",
        )
    ]
    grid, to_x = _axis(
        MARGIN_L + 200,
        top,
        plot_w - 250.0,
        height,
        lo=0.0,
        hi=hi,
        ticks=[0.0, 10.0, 25.0, 50.0],
        unit="%",
    )
    parts.extend(grid)
    parts.append(_rail(to_x(cap), top, height, "cap 50%", CAP_COL))

    for index, fold in enumerate(folds):
        y = top + index * ROW_H + ROW_H / 2
        for metrics, offset in (
            (fold["in_sample"], 0.0),
            (fold["out_of_sample"], ROW_H / 2),
        ):
            yy = y + offset
            value = metrics["max_drawdown_pct"]
            parts.append(
                f'<line x1="{MARGIN_L + 200:.1f}" y1="{yy:.1f}" '
                f'x2="{to_x(value):.1f}" y2="{yy:.1f}" stroke="{CAP_COL}" stroke-width="3"/>'
            )
            parts.append(_dot(to_x(value), yy, CAP_COL, filled=value <= cap, r=3.4))
        parts.append(_text(MARGIN_L, y + 8, f"fold {fold['fold']}", size=11))
        parts.append(
            _text(
                MARGIN_L + 60,
                y + 8,
                f"IS {fold['in_sample']['max_drawdown_pct']:.2f}% / OOS "
                f"{fold['out_of_sample']['max_drawdown_pct']:.2f}%",
                size=9,
                fill=MUTED,
            )
        )
    svg, bottom = _block(
        MARGIN_L,
        top + height + 20,
        "The 50% cap is likewise a rail, not a Stage A filter. Both rails are drawn because the "
        "objective is DEFINED with them, and they are drawn because a reader should be able to "
        "see the margin — not because any row was rejected for crossing one.",
        size=10,
        width=150,
        fill=MUTED,
        lead=13,
        gap=2,
    )
    parts.append(svg)
    return "\n".join(parts), bottom


# --------------------------------------------------------------------------- #
# Panel 4 — OOS, visually separate
# --------------------------------------------------------------------------- #


def _oos_panel(run: dict, top: float) -> tuple[str, float]:
    rows = run["per_extra"]
    plot_w = W - MARGIN_L - MARGIN_R
    height = ROW_H * len(rows)
    peak = max((abs(r["delta_oos_vs_flat_dca_pct"]) for r in rows), default=1.0)
    top_val = max(peak * 1.15, 1e-6)
    zero_x = MARGIN_L + 120.0
    val_to_w = (plot_w - 260.0) / 2.0 / top_val
    void = run.get("oos_is_degenerate", False)

    parts = [
        f'<line x1="{MARGIN_L - 20}" y1="{top - 46:.1f}" x2="{W - MARGIN_R + 20}" '
        f'y2="{top - 46:.1f}" stroke="{OOS_COL}" stroke-width="2.4"/>',
        _text(MARGIN_L, top - 30, OOS_TITLE, size=13, fill=OOS_COL, weight="bold"),
    ]
    if void:
        parts.append(
            _text(
                W - MARGIN_R,
                top - 30,
                "*** VOID — every window below deployed ZERO capital, so these bars are one "
                "all-cash book repeated ***",
                size=12,
                fill=NOKEEP_COL,
                weight="bold",
                anchor="end",
            )
        )
    grid, _ = _axis(
        zero_x - 60,
        top,
        plot_w - 200.0,
        height,
        lo=-top_val,
        hi=top_val,
        ticks=[-top_val, 0.0, top_val],
        unit="",
    )
    parts.extend(grid)
    parts.append(
        f'<line x1="{zero_x:.1f}" y1="{top:.1f}" x2="{zero_x:.1f}" '
        f'y2="{top + height:.1f}" stroke="{INK}" stroke-width="1.2"/>'
    )
    for index, row in enumerate(rows):
        y = top + index * ROW_H + ROW_H / 2
        delta = row["delta_oos_vs_flat_dca_pct"]
        width = abs(delta) * val_to_w
        x = zero_x if delta >= 0 else zero_x - width
        parts.append(_text(MARGIN_L, y + 4, row["name"], size=11, fill=MUTED))
        parts.append(
            f'<rect x="{x:.1f}" y="{y - BAR_H / 2:.1f}" width="{max(width, 1.0):.1f}" '
            f'height="{BAR_H}" fill="{OOS_COL}" fill-opacity="0.45" stroke="{OOS_COL}" '
            f'stroke-width="1"/>'
        )
        parts.append(
            _text(
                zero_x + (plot_w - 200.0) / 2 + 12,
                y + 4,
                f"OOS {row['mean_oos_vs_flat_dca_pct']:+.2f}%  (Δ {delta:+.2f}%)",
                size=10,
                fill=MUTED,
            )
        )
    note = (
        "THIS PANEL IS VOID AND THE BARS MUST NOT BE READ AS EVIDENCE. Every out-of-sample "
        "window in this run deployed zero capital: the shipped no-trend rolling-z rails are "
        "refit on each fold's in-sample window, and RollingZRiskModel.rails() left-joins a "
        "stored (date, mu, sigma) table, so every date outside that fit window comes back "
        "null. Null rails give null risk, null risk gives no trades, and the fold is all "
        "cash. A trend rail would extrapolate and this would not. The in-sample panels above "
        "are unaffected — in-sample dates are inside the fit window. Stage B must score these "
        "folds through the concatenated-history rolling loop the gold curve search already "
        "carries, or use rails that extrapolate."
        if void
        else "This panel is deliberately SEPARATE and deliberately below a rule. The in-sample "
        "bars above chose the weights; these did not, could not, and must not be read as "
        "validating them. Where a leg's OOS bar runs opposite its in-sample bar, that is the "
        "gap between fitting the fold and predicting it — reported, not resolved."
    )
    svg, bottom = _block(
        MARGIN_L,
        top + height + 22,
        note,
        size=10,
        width=150,
        fill=NOKEEP_COL if void else MUTED,
        lead=13,
        gap=2,
    )
    parts.append(svg)
    return "\n".join(parts), bottom


# --------------------------------------------------------------------------- #
# Panel 5 — the winner's shape vs the published btc_sdca reference
# --------------------------------------------------------------------------- #


def _shape_panel(run: dict, top: float) -> tuple[str, float]:
    joint = next((r for r in run["runs"] if r["label"] == "joint_sweep"), run["runs"][-1])
    weights = joint["weights"]
    extras = joint["enabled_extras"]
    reference = run["btc_sdca_reference_shape"]
    partial = sum(1 for w in list(extras.values()) + [reference.get("valuation", 1.0)] if w < 1.0)

    parts = [
        _text(
            MARGIN_L,
            top - 30,
            "5 · THE WINNER'S SHAPE vs the published btc_sdca reference — shape comparison "
            "only, not a tuning target",
            size=12,
            weight="bold",
        )
    ]
    lines = [
        f"gold joint-sweep winner: valuation {weights['valuation']:g}"
        + (
            " (valuation-only — no extra earned a keep)"
            if not extras
            else " + " + ", ".join(f"{n} {w:g}" for n, w in extras.items())
        ),
        "published btc_sdca reference: " + ", ".join(f"{n} {w:g}" for n, w in reference.items()),
        f"legs: gold {1 + len(extras)} vs btc_sdca {len(reference) + 0}"
        f" · partial-weight legs: gold {partial} vs btc_sdca 4 "
        "(0.5 / 0.5 / 0.5 / 0.25)",
        "The reference is the precedent for what a real multi-leg composite looks like. It is "
        "reported here for shape only: nothing was copied from it, tuned toward it, or "
        "benchmarked against it.",
    ]
    y = top + 6
    for index, line in enumerate(lines):
        svg, y = _block(
            MARGIN_L,
            y,
            line,
            size=11 if index < 3 else 10,
            width=150,
            fill=INK if index < 3 else MUTED,
            weight="bold" if index < 3 else "normal",
            lead=14,
            gap=6,
        )
        parts.append(svg)
    return "\n".join(parts), y


# --------------------------------------------------------------------------- #
# Header + footer
# --------------------------------------------------------------------------- #


def _header(run: dict) -> tuple[str, float]:
    joint = next((r for r in run["runs"] if r["label"] == "joint_sweep"), run["runs"][-1])
    plan = run["search_plan"]
    parts = [
        _text(W / 2, 26, TITLE, size=15, weight="bold", anchor="middle"),
        _text(
            W / 2,
            44,
            f"{run['symbol']} · objective: mean IN-SAMPLE vs_flat_dca_pct · "
            f"floor {run['frozen_knobs']['capital_deployed_floor_pct'] if 'capital_deployed_floor_pct' in run['frozen_knobs'] else 10.0:g}% "
            f"deployed, cap 50% drawdown · curve {run['curve_preset']} · rails rolling_z 90d/z1.0",
            size=10,
            fill=MUTED,
            anchor="middle",
        ),
        _text(
            MARGIN_L,
            76,
            "4 PANELS — keep/drop, the two rails, then OOS BELOW A RULE — plus the shape "
            "comparison",
            size=12,
            weight="bold",
        ),
    ]
    y = 96.0
    for text, size, fill, weight in (
        (
            f"JOINT SWEEP searched {len(plan['search_names'])} of "
            f"{len(run['allowlist'])} allowlist names in {joint['num_evaluations']:,} "
            f"evaluations on the SHIPPED frozen grids. FEASIBILITY CALL: the full allowlist "
            f"projects to {run['projected_full_cost']['evaluations']:,} evaluations at the "
            f"measured {run['projected_full_cost']['ms_per_eval']:.1f} ms/eval = "
            f"{run['projected_full_cost']['hours']:.1f} h, which does not fit a session. The "
            f"narrowing is a COVERAGE budget, a data property, never a score.",
            10,
            INK,
            "normal",
        ),
        (
            "THE OBJECTIVE CONSUMES NO CYCLE WINDOWS — it cuts its own folds from the calendar, "
            "so this is ONE run, and the gold pin sets are not an input. The preceding "
            "diagnostic scored cycle-window overlap instead: a DIFFERENT OBJECTIVE, and the two "
            "results must not be blended into a single claim.",
            10,
            INK,
            "normal",
        ),
        (
            run["rank_not_gated_label"],
            10,
            MUTED,
            "normal",
        ),
    ):
        svg, y = _block(
            MARGIN_L, y, text, size=size, width=150, fill=fill, weight=weight, lead=13, gap=6
        )
        parts.append(svg)
    if run.get("oos_is_degenerate"):
        svg, y = _block(
            MARGIN_L,
            y,
            "OUT-OF-SAMPLE IS VOID IN THIS RUN — every OOS window deployed zero capital, so "
            "every OOS figure is the same all-cash book. The shipped no-trend rolling-z rails "
            "are refit per fold on the in-sample window, and RollingZRiskModel.rails() "
            "left-joins a stored history, so every later date returns null rails, null risk "
            "and no trades. A trend rail would extrapolate; this one cannot. In-sample panels "
            "are unaffected. Panel 4 says so at the point of use.",
            size=10,
            width=150,
            fill=NOKEEP_COL,
            lead=13,
            gap=6,
        )
        parts.append(svg)
    return "\n".join(parts), y


def _footer(run: dict, top: float) -> tuple[str, float]:
    plan = run["search_plan"]
    exclusions = plan["exclusions"]
    bullets = [
        "BARS LENGTH = the change in in-sample vs_flat_dCA_pct against the valuation-only "
        "baseline, on the same folds. A leg that cannot beat valuation-only alone reads as "
        "'no keep' — not as a drop, because a one-name sweep shares its grid with the baseline "
        "row and so can never score below it.",
        "THE RAILS DID NOT GATE. The 10% floor and the 50% cap define the objective and are "
        "drawn so the margin is visible, but the shipped Stage A rank is the plain mean "
        "in-sample vs_flat_dCA_pct and vetoes nothing. The per-fold feasible flag is recorded, "
        "not enforced.",
        "OOS IS IN ITS OWN PANEL BELOW A RULE because it was reported and never used to select. "
        "Nothing on this figure was chosen by an out-of-sample number.",
        f"FEASIBILITY: {len(plan['search_names'])} of {len(run['allowlist'])} names in the joint "
        f"sweep; every excluded name is named with its measured coverage in the console and the "
        "JSON, and every allowlist name still carries a single-leg probe row — so no name is "
        "silently absent.",
        "NO GOLD PROFILE EXISTS in asset_profile.py; this run builds one from the module's own "
        "public surface and edits no source file. The rails are the shipped no-trend rolling-z "
        "anchor; the curve is the shipped gold_reselect preset resolved by name. No power-law "
        "and no generic log-linear / log-quadratic steer for gold appears anywhere.",
    ]
    lines = [_wrap(line, 148) for line in bullets]
    footer_lines = _wrap(FOOTER_LABEL, 150)
    y = top
    for block in lines:
        y += len(block) * 13 + 4
    box_top = y + 6
    box_h = 18.0 + len(footer_lines) * 15
    frame_bottom = box_top + box_h + 14
    plot_w = W - MARGIN_L - MARGIN_R

    parts = [
        f'<rect x="{MARGIN_L}" y="{top - 24:.1f}" width="{plot_w}" '
        f'height="{frame_bottom - (top - 24):.1f}" fill="{BAND_BG}" stroke="{BOX}"/>',
        _text(MARGIN_L + 12, top - 6, "HOW TO READ THIS", size=12, weight="bold"),
    ]
    y = top + 14
    for block in lines:
        parts.append(f'<circle cx="{MARGIN_L + 18:.1f}" cy="{y - 4:.1f}" r="2.4" fill="{INK}"/>')
        for index, line in enumerate(block):
            parts.append(_text(MARGIN_L + 30, y + index * 13, line, size=10, fill=INK))
        y += len(block) * 13 + 4
    parts.append(
        f'<rect x="{MARGIN_L + 18}" y="{box_top:.1f}" width="{plot_w - 36}" '
        f'height="{box_h:.0f}" fill="#ffffff" stroke="{NOKEEP_COL}" stroke-width="1.4"/>'
    )
    for index, line in enumerate(footer_lines):
        parts.append(
            _text(
                MARGIN_L + 30,
                box_top + 21 + index * 15,
                line,
                size=11 if index == 0 else 10,
                fill=INK,
                weight="bold" if index == 0 else "normal",
            )
        )
    held = ", ".join(e["name"] for e in exclusions) or "none"
    parts.append(
        _text(
            W - MARGIN_R + 14,
            top - 6,
            f"held out of the joint sweep: {held}",
            size=9,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts), frame_bottom


def build_svg(run: dict) -> str:
    header_svg, header_bottom = _header(run)
    y = header_bottom + 16

    panel_svg, y = _decide_panel(run, y)
    y += PANEL_GAP
    dep_svg, y = _deployed_panel(run, y)
    y += PANEL2_GAP
    dd_svg, y = _drawdown_panel(run, y)
    y += PANEL_GAP
    shape_svg, y = _shape_panel(run, y)
    y += DIVIDER_GAP
    oos_svg, y = _oos_panel(run, y)
    footer_svg, total_h = _footer(run, y + 6)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h:.0f}" '
        f'viewBox="0 0 {W} {total_h:.0f}" font-family="Helvetica, Arial, sans-serif">',
        "<title>" + escape(TITLE) + "</title>",
        "<desc>" + escape(FOOTER_LABEL) + "</desc>",
        f'<rect x="0" y="0" width="{W}" height="{total_h:.0f}" fill="white"/>',
        f"<defs>{_hatch_def(NOKEEP_COL)}</defs>",
        header_svg,
        panel_svg,
        dep_svg,
        dd_svg,
        shape_svg,
        oos_svg,
        footer_svg,
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    run = load_run()
    svg = build_svg(run)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / SVG_NAME).write_text(svg)
    wrote_public = False
    if PUBLIC_DIR.parent.exists():
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DIR / SVG_NAME).write_text(svg)
        wrote_public = True
    print(f"wrote {OUT_DIR / SVG_NAME} ({len(svg)} bytes)")
    if wrote_public:
        print(f"wrote {PUBLIC_DIR / SVG_NAME}")
    print("URL: http://127.0.0.1:4011/gold_charts/" + SVG_NAME)


if __name__ == "__main__":
    main()
