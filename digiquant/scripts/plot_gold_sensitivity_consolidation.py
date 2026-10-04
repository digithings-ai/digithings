#!/usr/bin/env python3
"""Draw the Engine-2 sensitivity consolidation on GLD as one stdlib SVG (#4804).

Owner standing rule: every iteration ships a visual. This one answers the two
questions the consolidation raises on a real run, in one figure:

    (1) GROUPED BARS, one group per indicator, one bar per level. Only
        indicators that capture at SOME level are drawn — the point of the panel
        is who is carrying the vote, so a leg that never captures is not in it.
        Every bar's HEIGHT is |separation| (the bar is read on magnitude) and
        its DIRECTION is drawn, not stated: an expected-polarity bar (+1,
        trough-high / peak-low) rises above the axis, an INVERTED one (-1, rich
        at the bottoms) is drawn below it and hatched, so the sign mix of a level
        is visible before any number is read. The 0.5 capture bar is a labelled
        rule across the panel, and the per-level window-day share is in the
        subtitle.

    (2) CAPTURE DEPTH per level — the summed |separation| of that level's
        captures, the ranking key the choice was actually made on, with the
        chosen level marked and each bar's split into expected / inverted shown.

    (3) An explicit IN-SAMPLE footer. Every separation here is fit against the
        same detected turns it is measured on. This is a scoring-target read, not
        a performance claim, and nothing in this figure is out-of-sample.

**Hand-rolled SVG, stdlib only.** No matplotlib (not installed in this env), no
numpy, no pandas, no nautilus. The drawing mirrors the pattern already in
``plot_gold_pin_set_options.py``: build the SVG as text and write it. Reads the
JSON the run wrote; it re-implements NO verdict — every number it draws is
``choice`` / ``level_summaries`` output from
``digiquant.strategies.sdca.sensitivity_consolidate``, and it refuses to draw if
that file is missing rather than recomputing anything.

Writes ``apps/digiquant-web/public/gold_charts/gold_sensitivity_consolidation.svg``
(served at ``/gold_charts/gold_sensitivity_consolidation.svg``) and a copy under
``digiquant/.scratch/gold_pngs/``. Both are untracked research output.

Usage (from the worktree root):
    .venv/bin/python digiquant/scripts/plot_gold_sensitivity_consolidation.py
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / ".scratch" / "gold_sensitivity_consolidation.json"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_sensitivity_consolidation.svg"

W = 1680
MARGIN_L, MARGIN_R = 132, 132

# Panel geometry. Panel 1's plot area spans the full symmetric range so an
# inverted bar below the axis is the same visual length as an expected one
# above it — the axis is the direction read, not a truncated baseline.
BAR_TOP, BAR_H = 128, 356
DEPTH_TOP, DEPTH_H = BAR_TOP + BAR_H + 138, 168
# The depth legend and the chosen-level sentence sit between the panels; the
# footer clears both, so nothing is drawn on top of anything else.
FOOTER_GAP = 128
NOTE_H = 252
TOTAL_H = DEPTH_TOP + DEPTH_H + FOOTER_GAP + NOTE_H + 26

INK = "#1c1c1c"
MUTED = "#5f5f5f"
GRID = "#e8e8e8"
BOX = "#dcdcdc"
BAND_BG = "#fbfbfb"
# Expected polarity (+1, trough-high / peak-low): the reading the composite is
# built to produce, so it is the "normal" one — solid, saturated.
EXPECTED_COL = "#2e7d32"
# Inverted (-1, rich at the bottoms): drawn below the axis and hatched, never
# only recoloured, so the distinction survives greyscale and colour-blindness.
INVERTED_COL = "#c62828"
CHOSEN_COL = "#1565c0"
BAR_COL = "#90a4ae"

TITLE = (
    "Gold sensitivity consolidation (Plan 22 Engine 2) — capture DEPTH decides, direction is fitted"
)
FOOTER_LABEL = (
    "IN-SAMPLE — scoring target only, NOT a performance claim. Every separation is fit against the same "
    "detected turns it is measured on, at every bar with a valid z. This calibrates indicator windows to "
    "detected history; it is NOT out-of-sample predictive skill, the holdout stays spent, and no return / "
    "Sharpe / trade count is claimed anywhere here."
)
WINDOWS_LABEL = (
    "Detector turns -> ±45d cycle windows. A SCORING TARGET only: no exposure floor, no execution "
    "period, no perfect-strategy oracle."
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


def _backed_text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 11,
    fill: str = INK,
    weight: str = "normal",
    anchor: str = "start",
) -> str:
    width = 0.56 * size * len(text) + 8
    pad_x = x - width + 4 if anchor == "end" else x - 4
    return (
        f'<rect x="{pad_x:.1f}" y="{y - size + 1:.1f}" width="{width:.1f}" '
        f'height="{size + 4}" fill="white" fill-opacity="0.88"/>'
        + _text(x, y, text, size=size, fill=fill, weight=weight, anchor=anchor)
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


HATCH_ID = "hatch-inverted"
HATCH_FILL = f"url(#{HATCH_ID})"


def _hatch_def(col: str) -> str:
    """The diagonal hatch an inverted bar is filled with, as an SVG ``<pattern>``.

    Hatching rather than just recolouring is the point: a level's sign mix has to
    survive greyscale printing and colour-vision deficiency, so "inverted" is
    carried by texture as well as by hue. A pattern (rather than hand-drawn
    clipped line segments) also keeps the file small and the geometry exact at
    every bar size.
    """
    return (
        f'<pattern id="{HATCH_ID}" width="6" height="6" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{col}" stroke-width="2.2" '
        f'stroke-opacity="0.85"/></pattern>'
    )


def load_run() -> dict:
    if not JSON_PATH.exists():
        raise SystemExit(
            f"{JSON_PATH} is missing — run run_gold_sensitivity_consolidation.py first. "
            "This script draws the run's verdicts; it never recomputes them."
        )
    return json.loads(JSON_PATH.read_text())


def _level_order(run: dict) -> list[float]:
    return [level["min_move_pct"] for level in run["levels"]]


def _capture_map(run: dict) -> dict[str, dict[float, tuple[float, int]]]:
    """``{indicator: {min_move_pct: (|separation|, fitted direction)}}`` for every capturing leg.

    Read off the JSON's own settled fields: ``level_summaries``-derived
    ``capturing`` membership, the row flagged ``selected``, its separation and its
    fitted direction. No verdict is taken here — the run already made every one.
    """
    out: dict[str, dict[float, tuple[float, int]]] = {}
    for level in run["levels"]:
        pct = level["min_move_pct"]
        names = set(level["capturing"])
        for row in level["indicators"]:
            if not row.get("selected") or row["name"] not in names or row["separation"] is None:
                continue
            out.setdefault(row["name"], {})[pct] = (abs(row["separation"]), row["direction"])
    return out


def _indicator_order(run: dict) -> list[str]:
    """Indicator order as the run listed them (the level's selected rows)."""
    seen: list[str] = []
    for row in run["levels"][0]["indicators"]:
        if row.get("selected") and row["name"] not in seen:
            seen.append(row["name"])
    return seen


def _bar_panel(run: dict, capturing: dict[str, dict[float, tuple[float, int]]]) -> str:
    """Grouped bars: one group per capturing indicator, one bar per level."""
    names = [name for name in _indicator_order(run) if name in capturing]
    pcts = _level_order(run)
    shares = {level["min_move_pct"]: level["window_day_share"] for level in run["levels"]}
    chosen = run["choice"]["chosen_min_move_pct"]
    bar_value = run["choice"]["capture_bar"]
    unstable = set(run["choice"]["direction_unstable"])

    peak = max(
        (leg[0] for legs in capturing.values() for leg in legs.values()),
        default=1.0,
    )
    top_val = max(peak * 1.12, bar_value * 1.35)
    plot_w = W - MARGIN_L - MARGIN_R
    mid_y = BAR_TOP + BAR_H / 2
    val_to_h = (BAR_H / 2) / top_val

    parts: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = BAR_TOP + BAR_H * (1.0 - frac)
        parts.append(
            f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{W - MARGIN_R}" y2="{y:.1f}" stroke="{GRID}"/>'
        )
        # The axis is SYMMETRIC about zero at one scale, because the panel plots
        # the SIGNED separation and direction is carried by geometry. So the tick
        # labels are signed too: the bottom edge is -top_val, not zero (zero is the
        # middle rule), and labelling it 0.00 would read as "nothing goes negative".
        value = top_val * (2.0 * frac - 1.0)
        label = "0" if abs(frac - 0.5) < 1e-9 else f"{value:+.2f}"
        parts.append(_text(MARGIN_L - 8, y + 3, label, size=10, fill=MUTED, anchor="end"))
    parts.append(
        _text(
            MARGIN_L - 8, BAR_TOP - 8, "separation (z), signed", size=10, fill=MUTED, anchor="end"
        )
    )

    # The frozen capture bar: drawn on BOTH sides of the axis, because the bar is
    # read on magnitude now — a -1.2 leg clears it as surely as a +1.2 one.
    for sign in (1, -1):
        y = mid_y - sign * bar_value * val_to_h
        parts.append(
            f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{W - MARGIN_R}" y2="{y:.1f}" '
            f'stroke="{CHOSEN_COL}" stroke-width="1.6" stroke-dasharray="7 4"/>'
        )
    # The tag lives in the right margin, not on the rule: the rule crosses the
    # valuation/sma_band bars, and an unreadable label on the bar line is worse
    # than a label beside the panel.
    parts.append(
        _text(
            W - MARGIN_R + 8,
            mid_y - bar_value * val_to_h + 3,
            "capture bar",
            size=10,
            fill=CHOSEN_COL,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R + 8,
            mid_y - bar_value * val_to_h + 15,
            f"{bar_value:g} z-units",
            size=10,
            fill=CHOSEN_COL,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R + 8,
            mid_y - bar_value * val_to_h + 27,
            "(on |separation|)",
            size=9,
            fill=MUTED,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R + 8,
            mid_y + 3 + 12,
            "expected (+1)",
            size=9,
            fill=EXPECTED_COL,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R + 8,
            mid_y + 3 + 24,
            "inverted (-1)",
            size=9,
            fill=INVERTED_COL,
        )
    )

    group_w = plot_w / max(len(names), 1)
    inner = group_w * 0.72
    slot = inner / max(len(pcts), 1)
    for gi, name in enumerate(names):
        gx = MARGIN_L + gi * group_w
        for li, pct in enumerate(pcts):
            leg = capturing[name].get(pct)
            if leg is None:
                continue
            value, direction = leg
            w = slot * 0.72
            x = gx + (group_w - inner) / 2 + li * slot + (slot - w) / 2
            h = value * val_to_h
            col = EXPECTED_COL if direction == 1 else INVERTED_COL
            if direction == 1:
                y = mid_y - h
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                    f'fill="{col}" fill-opacity="0.85"/>'
                )
            else:
                y = mid_y
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                    f'fill="{HATCH_FILL}" stroke="{col}" stroke-width="1.3"/>'
                )
            # A marker on the chosen level's bar for that indicator, so the level
            # that was chosen is legible without following the panel 2 highlight.
            if pct == chosen:
                parts.append(
                    f'<circle cx="{x + w / 2:.1f}" cy="{mid_y + (-h - 9 if direction == 1 else h + 9):.1f}" '
                    f'r="2.6" fill="{CHOSEN_COL}"/>'
                )
        label = f"{name} [UNSTABLE]" if name in unstable else name
        parts.append(_text(gx + group_w / 2, BAR_TOP + BAR_H + 16, label, size=9, anchor="middle"))

    parts.append(
        f'<line x1="{MARGIN_L}" y1="{mid_y:.1f}" x2="{W - MARGIN_R}" y2="{mid_y:.1f}" '
        f'stroke="{INK}" stroke-width="1.2"/>'
    )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{BAR_TOP}" width="{plot_w}" height="{BAR_H}" '
        f'fill="none" stroke="{BOX}"/>'
    )

    parts.append(
        _text(
            MARGIN_L,
            BAR_TOP - 30,
            "GROUPED BARS — one group per capturing indicator",
            size=12,
            weight="bold",
        )
    )
    parts.append(
        _text(
            MARGIN_L + plot_w / 2,
            BAR_TOP - 12,
            "each bar is that indicator's selected frozen-grid row at that level: "
            "height = |separation|, ABOVE the axis = expected polarity (+1), "
            "BELOW and hatched = inverted (-1)",
            size=10,
            fill=MUTED,
            anchor="middle",
        )
    )
    parts.append(
        _text(
            W - MARGIN_R,
            BAR_TOP - 30,
            "window-day share  " + " | ".join(f"@{pct:g}% {shares[pct]:.4f}" for pct in pcts),
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    parts.append(
        _text(
            MARGIN_L,
            BAR_TOP + BAR_H + 34,
            "only indicators capturing at SOME level are drawn · the circle marks the chosen "
            "level's bar · a leg vetoed for a direction flip is labelled [UNSTABLE]",
            size=10,
            fill=MUTED,
        )
    )
    return "\n".join(parts)


def _depth_panel(run: dict) -> str:
    """Capture depth per level — the ranking key — with the chosen level marked."""
    summaries = run["choice"]["level_summaries"]
    chosen = run["choice"]["chosen_min_move_pct"]
    plot_w = W - MARGIN_L - MARGIN_R
    top = DEPTH_TOP
    peak = max(s["capture_depth"] for s in summaries) or 1.0
    top_val = peak * 1.5
    col_w = plot_w / max(len(summaries), 1)
    bar_w = col_w * 0.44

    parts: list[str] = [
        _text(
            MARGIN_L, top - 30, "CAPTURE DEPTH per level — the ranking key", size=12, weight="bold"
        ),
        _text(
            MARGIN_L,
            top - 12,
            "summed |separation| of that level's captures. Depth, not headcount, is what the choice"
            " is made on; a knife-edge leg cannot hand the decision to a different granularity.",
            size=10,
            fill=MUTED,
        ),
    ]
    for frac in (0.0, 0.5, 1.0):
        y = top + DEPTH_H * (1.0 - frac)
        parts.append(
            f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{W - MARGIN_R}" y2="{y:.1f}" stroke="{GRID}"/>'
        )
        parts.append(
            _text(MARGIN_L - 8, y + 3, f"{top_val * frac:.2f}", size=10, fill=MUTED, anchor="end")
        )
    parts.append(_text(MARGIN_L - 8, top - 12, "capture depth", size=10, fill=MUTED, anchor="end"))

    for i, summary in enumerate(summaries):
        pct = summary["min_move_pct"]
        cx = MARGIN_L + col_w * (i + 0.5)
        h = summary["capture_depth"] / top_val * DEPTH_H
        x = cx - bar_w / 2
        y = top + DEPTH_H - h
        n_total = summary["capture_count"]
        n_exp = summary["expected_direction_count"]
        n_inv = summary["inverted_direction_count"]
        exp_h = h * (n_exp / n_total) if n_total else 0.0
        inv_h = h - exp_h
        if exp_h > 0.5:
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{exp_h:.1f}" '
                f'fill="{EXPECTED_COL}" fill-opacity="0.85"/>'
            )
        if inv_h > 0.5:
            parts.append(
                f'<rect x="{x:.1f}" y="{y + exp_h:.1f}" width="{bar_w:.1f}" height="{inv_h:.1f}" '
                f'fill="{HATCH_FILL}" stroke="{INVERTED_COL}" stroke-width="1.3"/>'
            )
        is_chosen = pct == chosen
        if is_chosen:
            parts.append(
                f'<rect x="{x - 9:.1f}" y="{top:.1f}" width="{bar_w + 18:.1f}" height="{DEPTH_H:.1f}" '
                f'fill="none" stroke="{CHOSEN_COL}" stroke-width="2.2"/>'
            )
        parts.append(
            _text(
                cx,
                y - 34,
                f"depth {summary['capture_depth']:.4f}",
                size=11,
                weight="bold",
                anchor="middle",
            )
        )
        parts.append(
            _text(cx, y - 20, f"{n_total} capturing", size=10, fill=MUTED, anchor="middle")
        )
        parts.append(
            _text(
                cx,
                y - 7,
                f"sign mix {n_exp}+ / {n_inv}-",
                size=10,
                fill=MUTED,
                anchor="middle",
            )
        )
        parts.append(
            _text(cx, top + DEPTH_H + 16, f"@{pct:g}%", size=11, anchor="middle", weight="bold")
        )
        parts.append(
            _text(
                cx,
                top + DEPTH_H + 30,
                f"{summary['n_turns']} turns · share {summary['window_day_share']:.4f}"
                f" · {'CHOSEN' if is_chosen else ('qualifies' if summary['qualifies'] else 'loses')}",
                size=10,
                fill=CHOSEN_COL if is_chosen else MUTED,
                anchor="middle",
                weight="bold" if is_chosen else "normal",
            )
        )

    # Legend for the depth stack, and the verdict sentence.
    lx = MARGIN_L
    ly = top + DEPTH_H + 52
    for col, fill, text in (
        (EXPECTED_COL, EXPECTED_COL, "expected polarity (+1), trough-high / peak-low"),
        (INVERTED_COL, HATCH_FILL, "inverted (-1), rich at the bottoms"),
    ):
        parts.append(
            f'<rect x="{lx:.1f}" y="{ly - 9:.1f}" width="11" height="11" fill="{fill}" '
            f'stroke="{col}" stroke-width="1"/>'
        )
        parts.append(_text(lx + 16, ly, text, size=10, fill=MUTED))
        lx += 0.56 * 10 * len(text) + 60
    unstable = run["choice"]["direction_unstable"]
    # Two full-width wrapped lines: this verdict is the longest string on the
    # canvas, and an unwrapped one runs off the right edge (it did).
    line_a = (
        f"chosen: min_move_pct={run['choice']['chosen_min_move_pct']:g} — "
        + run["choice"]["rationale"]
    )
    line_b = (
        f"direction_unstable: {', '.join(unstable)} — captures nowhere, flip recorded as evidence"
        if unstable
        else "direction_unstable: none — every fitting leg reads the same way at every level it "
        "clears the bar at (a flip would be vetoed)"
    )
    wrapped_a = _wrap(line_a, 148)
    for i, chunk in enumerate(wrapped_a):
        parts.append(_text(MARGIN_L, ly + 20 + i * 14, chunk, size=11))
    parts.append(
        _text(
            MARGIN_L,
            ly + 20 + len(wrapped_a) * 14 + 4,
            line_b,
            size=10,
            fill=INVERTED_COL if unstable else MUTED,
        )
    )
    return "\n".join(parts)


def _footer(run: dict) -> str:
    top = DEPTH_TOP + DEPTH_H + FOOTER_GAP
    plot_w = W - MARGIN_L - MARGIN_R
    parts = [
        f'<rect x="{MARGIN_L}" y="{top:.1f}" width="{plot_w}" height="{NOTE_H}" '
        f'fill="{BAND_BG}" stroke="{BOX}"/>',
        _text(MARGIN_L + 12, top + 22, "HOW TO READ THIS", size=12, weight="bold"),
    ]
    bullets = [
        "Grid-row selection maximises |separation| (ties to the shorter window), so an indicator's "
        "direction is FITTED from the sign of its winning row, never imposed.",
        "A row CAPTURES a level iff |separation| >= the bar AND neither window side's mean is "
        "inside the +/-0.06 dead zone. abs() is applied to the bar — a mirrored leg is recorded, "
        "not refused.",
        "DIRECTION STABILITY (veto): a leg capturing at more than one level must carry the same "
        "fitted direction at each; a flip is flagged direction_unstable, captures nowhere, and is "
        "recorded as evidence. A single-level capture carries no such obligation.",
        "A level QUALIFIES iff its capture count loses nothing against EVERY coarser level; among "
        "qualifiers the largest capture DEPTH wins, ties to the coarser rung.",
    ]
    y = top + 42
    for line in bullets:
        parts.append(f'<circle cx="{MARGIN_L + 18:.1f}" cy="{y - 4:.1f}" r="2.4" fill="{INK}"/>')
        wrapped = _wrap(line, 132)
        for i, chunk in enumerate(wrapped):
            parts.append(_text(MARGIN_L + 30, y + i * 14, chunk, size=10, fill=INK))
        y += len(wrapped) * 14 + 4
    parts.append(_text(MARGIN_L + 12, y + 8, WINDOWS_LABEL, size=10, fill=MUTED))
    parts.append(
        f'<rect x="{MARGIN_L + 12}" y="{top + NOTE_H - 52}" width="{plot_w - 24}" height="42" '
        f'fill="#ffffff" stroke="{INVERTED_COL}" stroke-width="1.4"/>'
    )
    parts.append(
        _text(
            MARGIN_L + 22, top + NOTE_H - 36, FOOTER_LABEL[:150], size=11, fill=INK, weight="bold"
        )
    )
    parts.append(_text(MARGIN_L + 22, top + NOTE_H - 21, FOOTER_LABEL[150:], size=10, fill=INK))
    # Source sits on the header line, right-aligned, ABOVE the frame — parked at
    # the box's bottom edge it printed across the IN-SAMPLE box's own border.
    parts.append(
        _text(
            W - MARGIN_R - 12,
            top + 22,
            f"source: {run['source']} close column / {run['bars']} rows / "
            f"{run['first_date']} -> {run['last_date']}",
            size=10,
            fill=MUTED,
            anchor="end",
        )
    )
    return "\n".join(parts)


def build_svg(run: dict) -> str:
    capturing = _capture_map(run)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{TOTAL_H}" '
        f'viewBox="0 0 {W} {TOTAL_H}" font-family="Helvetica, Arial, sans-serif">',
        "<title>" + escape(TITLE) + "</title>",
        "<desc>" + escape(FOOTER_LABEL) + "</desc>",
        f'<rect x="0" y="0" width="{W}" height="{TOTAL_H}" fill="white"/>',
        f"<defs>{_hatch_def(INVERTED_COL)}</defs>",
        _text(W / 2, 24, TITLE, size=15, weight="bold", anchor="middle"),
        _text(
            W / 2,
            42,
            f"{run['symbol']} · crank {run['grid']['min_move_pct_levels']} · "
            f"min_separation_days {run['grid']['min_separation_days']} · "
            f"windows ±{run['grid']['window_half_width_days']}d · bar "
            f"{run['choice']['capture_bar']} z · dead zone ±{run['frozen_inputs']['degenerate_mean_abs']}"
            " (all frozen, nothing tuned after seeing output)",
            size=10,
            fill=MUTED,
            anchor="middle",
        ),
        _bar_panel(run, capturing),
        _depth_panel(run),
        _footer(run),
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

    choice = run["choice"]
    capturing = _capture_map(run)
    print(f"wrote {OUT_DIR / SVG_NAME}")
    if wrote_public:
        print(f"wrote {PUBLIC_DIR / SVG_NAME}")
    print(f"bytes: {(OUT_DIR / SVG_NAME).stat().st_size}")
    print(f"indicators capturing at some level: {len(capturing)} ({', '.join(capturing)})")
    print(
        f"chosen: min_move_pct={choice['chosen_min_move_pct']:g}, depth {choice['capture_depth']:.4f}"
    )
    for summary in choice["level_summaries"]:
        print(
            f"  @{summary['min_move_pct']:>4g}% depth {summary['capture_depth']:>8.4f}  "
            f"{summary['capture_count']:>2} capturing  "
            f"mix {summary['expected_direction_count']}+/{summary['inverted_direction_count']}-  "
            f"qualifies={summary['qualifies']}"
        )
    print(f"direction_unstable: {choice['direction_unstable'] or 'none'}")
    print("IN-SAMPLE — scoring target only, not a performance claim")


if __name__ == "__main__":
    main()
