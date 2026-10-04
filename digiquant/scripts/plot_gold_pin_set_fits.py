#!/usr/bin/env python3
"""Chart the gold indicator fits against BOTH gold pin sets, one pair per indicator (#4804).

Plan 22's last piece, visual. Reads ``digiquant/.scratch/gold_pin_set_fits.json``
— written by ``run_gold_pin_set_fits.py`` — and draws what that run decided. It
recomputes no verdict: every separation, direction, capture and keep list is read
off the artifact, so the figure cannot disagree with the numbers in the report.

One SVG, hand-rolled stdlib only (no matplotlib / numpy / pandas / nautilus —
none is installed and none is needed for a horizontal bar chart). It mirrors the
``_text`` / ``_backed_text`` / ``_wrap`` / hatch-pattern pattern of
``plot_gold_sensitivity_consolidation.py`` so the family of gold charts reads as
one family.

The panel is HORIZONTAL and signed around zero, because direction is the read:
a leg's bar runs RIGHT when it votes the expected polarity (rich at the peaks,
cheap at the troughs) and LEFT when it is inverted, and the bar's length is
``|separation|``. So an expected leg and a mirrored leg of the same depth are the
same length on opposite sides, and the two pin sets of one indicator sit adjacent
for direct comparison. Inverted bars are hatched as well as recoloured, so the
distinction survives greyscale and colour-vision deficiency.

The frozen 0.5 capture bar is drawn on BOTH sides of zero (the bar is read on
magnitude), a capturing leg gets a filled diamond at its tip, and the greedy keep
list is annotated — EMPTY on both pin sets, which is the result worth seeing.

Layout note, learned by rendering: the header is a two-column block (prose wrapped
to a fixed character width on the left, the pin-set inset in its own column on the
right) and the panel top is computed from the wrapped text, so a longer run pushes
the panel down instead of drawing the inset on top of a sentence.

Usage:

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/plot_gold_pin_set_fits.py
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / ".scratch" / "gold_pin_set_fits.json"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"
SVG_NAME = "gold_pin_set_fits.svg"

W = 1680
MARGIN_L, MARGIN_R = 214, 250

# Panel geometry. One row per indicator, TWO bars per row (gold_v1 over gold_v2),
# so a pair is read without moving the eye off the row.
ROW_H = 34
BAR_H = 12
BAR_GAP = 34
FOOTER_GAP = 40

INK = "#1c1c1c"
MUTED = "#5f5f5f"
GRID = "#ececec"
BOX = "#dcdcdc"
BAND_BG = "#fbfbfb"
# Expected polarity (+1, trough-high / peak-low): the reading the composite is
# built to produce, so it is the "normal" one — solid, saturated, to the right.
EXPECTED_COL = "#2e7d32"
# Inverted (-1, rich at the bottoms): to the LEFT and hatched, never only
# recoloured, so the distinction survives greyscale and colour-blindness.
INVERTED_COL = "#c62828"
VERDICT_COL = "#1565c0"
CAPTURE_COL = "#6a1b9a"

TITLE = (
    "Gold indicator fits against BOTH approved gold pin sets — Set A (gold_v1, 6 pins) "
    "vs the algorithmic 20 (gold_v2, 15%)"
)
FOOTER_LABEL = (
    "IN-SAMPLE — a scoring target only, NOT a performance claim. Every separation is the "
    "MAXIMUM over a frozen grid, scored against cycle windows derived from the SAME price "
    "history the z-series are built from, so capture counts and depths are a "
    "partly-selected UPPER BOUND. No return / Sharpe / trade count is claimed on this figure."
)
PIN_SETS_NOTE = (
    "gold_v1 ⊂ gold_v2 (same turns, same kinds): gold_v2 REFINES the same target by "
    "interpolating the turns between Set A's picks, so a separation that moves between the "
    "two is the granularity speaking, not a contradiction. A window is a scoring target, not "
    "an execution period — no exposure floor, no perfect-strategy oracle."
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
    """A wrapped paragraph at a fixed CHARACTER width; returns its bottom y.

    Wrapping by characters rather than trusting the pixel width is what keeps a
    long sentence out of the neighbouring column: at these sizes the column is
    known to the line, and a fixed column is the only way two columns coexist.
    """
    lines = _wrap(text, width)
    svg = "\n".join(
        _text(x, y + index * lead, line, size=size, fill=fill, weight=weight)
        for index, line in enumerate(lines)
    )
    return svg, y + len(lines) * lead + gap


HATCH_ID = "hatch-inverted"
HATCH_FILL = f"url(#{HATCH_ID})"


def _hatch_def(col: str) -> str:
    """The diagonal hatch an inverted bar carries, as an SVG ``<pattern>``.

    Texture as well as hue, so "inverted" survives greyscale printing and
    colour-vision deficiency — and so the left/right geometry is not the only
    cue. A pattern (rather than hand-clipped segments) keeps the file small and
    the geometry exact at every bar length.
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
            f"{JSON_PATH} is missing — run run_gold_pin_set_fits.py first. This script "
            "draws that run's verdicts; it never recomputes them."
        )
    return json.loads(JSON_PATH.read_text())


def _labels(run: dict) -> list[str]:
    """The two pin-set labels, in the artifact's order."""
    return list(run["sets"])


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value:+.4f}"


INSET_X0 = 812
INSET_W = W - MARGIN_R - INSET_X0
COL_CHARS = 100
INSET_CHARS = 60


def _inset(run: dict, labels: list[str]) -> tuple[str, float]:
    """The pin-set inset: pins, window-day share, captures/depth, greedy keep list.

    Its own column on the right. The first version floated it over the prose and
    the two collided — rendering, not reading, is what caught that.
    """
    top = 74.0
    box_h = 40.0 + len(labels) * 52.0
    parts = [
        f'<rect x="{INSET_X0}" y="{top}" width="{INSET_W}" height="{box_h:.0f}" '
        f'fill="{BAND_BG}" stroke="{BOX}"/>',
        _text(
            INSET_X0 + 14,
            top + 22,
            "PIN-SET INSET — windows asked about, what survived",
            size=11,
            weight="bold",
        ),
    ]
    y = top + 44
    for label in labels:
        entry = run["sets"][label]
        svg, y = _block(
            INSET_X0 + 14,
            y,
            f"{label} ({entry['factory'].split('.')[-2]}) — {entry['pins']} pins "
            f"({entry['peaks']} peak / {entry['troughs']} trough) · window-day share "
            f"{entry['window_day_share']:.4f} = {entry['window_days']} days, "
            f"{entry['overlap_days']} overlapping",
            size=10,
            width=INSET_CHARS,
            lead=13,
            gap=2,
        )
        parts.append(svg)
        kept = entry["greedy_kept"]
        svg, y = _block(
            INSET_X0 + 14,
            y,
            f"captures {entry['capture_count']} · depth {entry['capture_depth']:.4f} · "
            f"greedy keep {list(kept) if kept else 'EMPTY (anchor-only)'} · anchor "
            f"{_signed(entry['anchor_separation'])} → {_signed(entry['greedy_final_separation'])}",
            size=10,
            width=INSET_CHARS,
            fill=MUTED,
            lead=13,
            gap=10,
        )
        parts.append(svg)
    return "\n".join(parts), top + box_h


def _header(run: dict, labels: list[str]) -> tuple[str, float]:
    """Two columns of prose plus the inset; returns the y the panel starts below."""
    first, second = labels
    verdict = run["comparison"]["verdict"]
    flips = run["comparison"]["flips"]
    kept_first = run["sets"][first]["greedy_kept"]
    kept_second = run["sets"][second]["greedy_kept"]
    degenerate = [
        name for name, read in run["sets"][first]["indicator_reads"].items() if read["degenerate"]
    ]
    parts = [
        _text(W / 2, 26, TITLE, size=15, weight="bold", anchor="middle"),
        _text(
            W / 2,
            44,
            f"{run['symbol']} · {run['calendar']} · capture bar {run['capture_bar']} z-units on "
            f"|separation| · dead zone ±{run['degenerate_mean_abs']} · ±45d windows "
            "(all frozen; nothing tuned after seeing output)",
            size=10,
            fill=MUTED,
            anchor="middle",
        ),
        _text(
            MARGIN_L,
            76,
            f"HORIZONTAL BARS — one pair per indicator: {first} on TOP, {second} BELOW",
            size=12,
            weight="bold",
        ),
    ]
    y = 96.0
    for text, size, fill, weight in (
        (
            "Length = |separation|. RIGHT of zero = expected polarity (+1), LEFT and hatched = "
            "inverted (-1); both bars of a pair are ONE indicator against the two approved "
            "pin sets. The grids, the 0.5 capture bar, the 0.06 dead zone, the separation "
            "formula and the ±45d half-window are IDENTICAL between the runs — only the window "
            "set differs.",
            10,
            MUTED,
            "normal",
        ),
        (
            f"VERDICT: {verdict['better_label']} fits BETTER — capture depth "
            f"{run['sets'][first]['capture_depth']:.4f} vs {run['sets'][second]['capture_depth']:.4f} "
            f"(margin {_signed(verdict['depth_margin'])}) on identical headcount "
            f"({run['sets'][first]['capture_count']} vs {run['sets'][second]['capture_count']}). "
            "Depth, not headcount, is the ranking key.",
            11,
            VERDICT_COL,
            "bold",
        ),
        (
            "VERDICT FLIPS between the pin sets: "
            + (
                ", ".join(
                    f"{entry['name']} ({'+'.join(entry['changes'])}: "
                    f"{_signed(entry[f'{first}_separation'])} → "
                    f"{_signed(entry[f'{second}_separation'])})"
                    for entry in flips
                )
                if flips
                else "none"
            )
            + " — a flip is a change of capture or of fitted direction; a separation that "
            "merely moved is not a flip.",
            10,
            INK if flips else MUTED,
            "normal",
        ),
        (
            f"GREEDY EQUAL-WEIGHT KEEP LIST: {first} "
            f"{list(kept_first) if kept_first else 'EMPTY (anchor-only)'} · {second} "
            f"{list(kept_second) if kept_second else 'EMPTY (anchor-only)'} — every candidate "
            "made the anchor's own aggregate separation worse, so the frozen rule keeps none of "
            "them on either pin set.",
            10,
            MUTED,
            "normal",
        ),
        (
            "degenerate legs (excluded from every keep list): "
            + ", ".join(degenerate)
            + " — a pass resting on a dead side is not a pass, however deep it reads.",
            10,
            MUTED,
            "normal",
        ),
        (
            "A filled diamond at a bar tip marks a CAPTURING leg; a hollow tip marks one that "
            "does not clear the capture bar or rests on a dead side. The dashed vertical rules "
            "are the bar, drawn on both sides because it is read on |separation|.",
            10,
            MUTED,
            "normal",
        ),
    ):
        svg, y = _block(
            MARGIN_L, y, text, size=size, width=COL_CHARS, fill=fill, weight=weight, lead=14, gap=8
        )
        parts.append(svg)
    inset_svg, inset_bottom = _inset(run, labels)
    parts.append(inset_svg)
    return "\n".join(parts), max(y, inset_bottom)


def _bar_panel(run: dict, labels: list[str], bar_top: float) -> str:
    rows = run["comparison"]["rows"]
    first, second = labels
    bar_value = run["capture_bar"]
    peak = max(
        (
            abs(read["separation"])
            for row in rows
            for read in row["by_set"].values()
            if read["separation"] is not None
        ),
        default=1.0,
    )
    top_val = max(peak * 1.08, bar_value * 1.3)
    plot_w = W - MARGIN_L - MARGIN_R
    zero_x = MARGIN_L + plot_w / 2
    val_to_w = (plot_w / 2) / top_val
    panel_h = ROW_H * len(rows)

    parts: list[str] = []
    for step in range(-6, 7):
        value = top_val * step / 6
        if abs(value) < top_val / 12:
            continue
        x = zero_x + value * val_to_w
        parts.append(
            f'<line x1="{x:.1f}" y1="{bar_top:.1f}" x2="{x:.1f}" '
            f'y2="{bar_top + panel_h:.1f}" stroke="{GRID}"/>'
        )
        parts.append(_text(x, bar_top - 8, f"{value:+.1f}", size=9, fill=MUTED, anchor="middle"))
    for sign in (1, -1):
        x = zero_x + sign * bar_value * val_to_w
        parts.append(
            f'<line x1="{x:.1f}" y1="{bar_top:.1f}" x2="{x:.1f}" '
            f'y2="{bar_top + panel_h:.1f}" stroke="{CAPTURE_COL}" stroke-width="1.5" '
            f'stroke-dasharray="7 4"/>'
        )
        parts.append(
            _backed_text(
                x,
                bar_top + panel_h + 16,
                f"capture bar ±{bar_value:g}",
                size=9,
                fill=CAPTURE_COL,
                anchor="middle",
            )
        )
    parts.append(
        _text(
            zero_x,
            bar_top - 24,
            "separation (z), signed — the sign IS the direction",
            size=10,
            fill=MUTED,
            anchor="middle",
        )
    )
    parts.append(
        _text(
            MARGIN_L + 4,
            bar_top - 24,
            "inverted (−1) ←",
            size=9,
            fill=INVERTED_COL,
        )
    )
    parts.append(
        _text(
            W - MARGIN_R - 4,
            bar_top - 24,
            "→ expected (+1)",
            size=9,
            fill=EXPECTED_COL,
            anchor="end",
        )
    )

    for index, row in enumerate(rows):
        top = bar_top + index * ROW_H
        if index % 2 == 0:
            parts.append(
                f'<rect x="{MARGIN_L}" y="{top:.1f}" width="{plot_w}" '
                f'height="{ROW_H:.1f}" fill="{BAND_BG}"/>'
            )
        parts.append(
            _text(
                MARGIN_L - 14,
                top + ROW_H / 2 + 4,
                row["name"] + ("  FLIP" if row["flipped"] else ""),
                size=10,
                fill=VERDICT_COL if row["flipped"] else INK,
                anchor="end",
                weight="bold" if row["flipped"] else "normal",
            )
        )
        for slot, read in enumerate((row["by_set"][first], row["by_set"][second])):
            separation = read["separation"]
            bar_y = top + 3 + slot * (BAR_H + 3)
            if separation is None:
                parts.append(
                    _text(
                        zero_x + 10,
                        bar_y + BAR_H - 2,
                        f"unscored against {labels[slot]}",
                        size=9,
                        fill=MUTED,
                    )
                )
                continue
            direction = read["direction"]
            length = abs(separation) * val_to_w
            col = EXPECTED_COL if direction == 1 else INVERTED_COL
            x = zero_x if direction == 1 else zero_x - length
            tip = zero_x + length if direction == 1 else zero_x - length
            if direction == 1:
                parts.append(
                    f'<rect x="{x:.1f}" y="{bar_y:.1f}" width="{length:.1f}" '
                    f'height="{BAR_H}" fill="{col}" fill-opacity="0.85"/>'
                )
            else:
                parts.append(
                    f'<rect x="{x:.1f}" y="{bar_y:.1f}" width="{length:.1f}" '
                    f'height="{BAR_H}" fill="{HATCH_FILL}" stroke="{col}" stroke-width="1.2"/>'
                )
            if read["captures"]:
                parts.append(
                    f'<polygon points="{tip:.1f},{bar_y + BAR_H / 2:.1f} '
                    f"{tip + (5 if direction == 1 else -5):.1f},{bar_y + BAR_H / 2 - 4:.1f} "
                    f'{tip + (5 if direction == 1 else -5):.1f},{bar_y + BAR_H / 2 + 4:.1f}" '
                    f'fill="{CAPTURE_COL}"/>'
                )
            else:
                parts.append(
                    f'<circle cx="{tip:.1f}" cy="{bar_y + BAR_H / 2:.1f}" r="2.4" '
                    f'fill="white" stroke="{MUTED}" stroke-width="1.1"/>'
                )
            label = (
                f"{_signed(separation)} w{read['window_days']} "
                f"{'CAP' if read['captures'] else 'no'}"
            )
            # The longest bar's label would otherwise run out through the right
            # margin, so a label that does not FIT beyond its tip is drawn INSIDE
            # the bar end instead — the read is unchanged, the overflow is not.
            label_w = 0.56 * 9 * len(label) + 4
            outside = (tip + 9 + label_w) if direction == 1 else (tip - 9 - label_w)
            fits = outside <= W - MARGIN_R if direction == 1 else outside >= MARGIN_L
            # An inside label sits ON the bar — solid or hatched — so it gets a
            # white backing; an outside label is on bare canvas and does not need one.
            label_x = (
                tip + (9 if direction == 1 else -9) if fits else tip + (-9 if direction == 1 else 9)
            )
            label_anchor = "start" if (direction == 1) == fits else "end"
            render = _backed_text if not fits else _text
            parts.append(
                render(
                    label_x,
                    bar_y + BAR_H - 2,
                    label,
                    size=9,
                    fill=CAPTURE_COL if read["captures"] else MUTED,
                    anchor=label_anchor,
                    weight="normal",
                )
            )

    parts.append(
        f'<line x1="{zero_x:.1f}" y1="{bar_top:.1f}" x2="{zero_x:.1f}" '
        f'y2="{bar_top + panel_h:.1f}" stroke="{INK}" stroke-width="1.3"/>'
    )
    parts.append(
        f'<rect x="{MARGIN_L}" y="{bar_top:.1f}" width="{plot_w}" height="{panel_h:.1f}" '
        f'fill="none" stroke="{BOX}"/>'
    )
    return "\n".join(parts)


def _footer(run: dict, labels: list[str], top: float) -> tuple[str, float]:
    """The how-to-read block, the set-inclusion note and the IN-SAMPLE box.

    Laid out by MEASURING the wrapped lines first and drawing the frame before
    its contents — the frame last meant a filled rect painted over the prose,
    which is why the bullets and the note are positioned, not appended.
    """
    plot_w = W - MARGIN_L - MARGIN_R
    bullets = [
        "Both bars of a pair are ONE indicator scored against the two approved gold pin sets. "
        "The frozen grids, the 0.5 capture bar, the 0.06 dead zone, the separation formula and "
        "the ±45d half-window are IDENTICAL between the runs; only the window set differs.",
        "The bar that speaks for an indicator is the grid row with the largest |separation| "
        "(ties to the shorter window), so the DIRECTION shown is FITTED from that row's sign, "
        "never imposed — and that same |separation| is what the capture bar is read on.",
        "A leg CAPTURES iff |separation| >= 0.5 AND neither window side's mean is inside the "
        "+/-0.06 dead zone. Capturing legs carry a filled diamond; degenerate legs cannot "
        "capture however deep they read.",
        "WHICH SET FITS BETTER is decided by summed capture DEPTH, not headcount, with ties to "
        "the coarser (fewer-pin) set. Both greedy equal-weight keep lists are EMPTY: every "
        "candidate made the anchor's own aggregate separation worse, so the frozen rule keeps "
        "none of them.",
    ]
    bullet_lines = [_wrap(line, 126) for line in bullets]
    note_lines = _wrap(PIN_SETS_NOTE, 126)
    footer_lines = _wrap(FOOTER_LABEL, 150)

    frame_top = top - 26.0
    y = top + 40
    for lines in bullet_lines:
        y += len(lines) * 14 + 4
    note_y = y + 4
    y = note_y + len(note_lines) * 14 + 12
    box_top = y
    box_h = 18.0 + len(footer_lines) * 15
    frame_bottom = box_top + box_h + 16

    parts = [
        f'<rect x="{MARGIN_L}" y="{frame_top:.1f}" width="{plot_w}" '
        f'height="{frame_bottom - frame_top:.1f}" fill="{BAND_BG}" stroke="{BOX}"/>',
        _text(MARGIN_L + 12, top + 20, "HOW TO READ THIS", size=12, weight="bold"),
        _text(
            W - MARGIN_R - 12,
            top + 20,
            f"source: {run['sets'][labels[0]]['factory']} and "
            f"{run['sets'][labels[1]]['factory']} / {run['symbol']} close column / "
            f"{run['calendar']}",
            size=10,
            fill=MUTED,
            anchor="end",
        ),
    ]
    y = top + 40
    for lines in bullet_lines:
        parts.append(f'<circle cx="{MARGIN_L + 18:.1f}" cy="{y - 4:.1f}" r="2.4" fill="{INK}"/>')
        for index, line in enumerate(lines):
            parts.append(_text(MARGIN_L + 30, y + index * 14, line, size=10, fill=INK))
        y += len(lines) * 14 + 4
    for index, line in enumerate(note_lines):
        parts.append(_text(MARGIN_L + 30, note_y + index * 14, line, size=10, fill=MUTED))
    parts.append(
        f'<rect x="{MARGIN_L + 18}" y="{box_top:.1f}" width="{plot_w - 36}" '
        f'height="{box_h:.0f}" fill="#ffffff" stroke="{INVERTED_COL}" stroke-width="1.4"/>'
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
    return "\n".join(parts), frame_bottom


def build_svg(run: dict) -> str:
    labels = _labels(run)
    header_svg, header_bottom = _header(run, labels)
    bar_top = header_bottom + BAR_GAP
    panel_svg = _bar_panel(run, labels, bar_top)
    panel_bottom = bar_top + ROW_H * len(run["comparison"]["rows"])
    footer_svg, total_h = _footer(run, labels, panel_bottom + 30)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h:.0f}" '
        f'viewBox="0 0 {W} {total_h:.0f}" font-family="Helvetica, Arial, sans-serif">',
        "<title>" + escape(TITLE) + "</title>",
        "<desc>" + escape(FOOTER_LABEL) + "</desc>",
        f'<rect x="0" y="0" width="{W}" height="{total_h:.0f}" fill="white"/>',
        f"<defs>{_hatch_def(INVERTED_COL)}</defs>",
        header_svg,
        panel_svg,
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
