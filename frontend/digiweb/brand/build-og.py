#!/usr/bin/env python3
"""Cut the Open Graph link-preview cards for both sites.

An OG card is the only piece of brand art a person sees *before* they visit the
site — it renders in Slack, iMessage, LinkedIn, X, Discord, WhatsApp — so it is
also the easiest one to leave stale. The card this replaces on digithings.ai had
drifted four ways at once: a capitalised "DigiThings", the superseded tagline "An
open-core agentic stack", a blue frame against a monochrome identity, and no mark
on it at all. digiquant.io had no card image whatsoever.

Everything here is DERIVED, so it cannot drift again:

  * the wordmark is OUTLINED from GeistMono-Regular.ttf (weight 400 — the weight
    `.term-body` actually renders at) using fontTools, and embedded as paths. It is
    NOT SVG <text>: librsvg has no Geist installed, so a <text> element would
    silently rasterise in whatever fallback face the machine has, which is exactly
    how an off-brand card gets shipped without anyone noticing;
  * the block cursor is one character cell — 0.6em wide, which is Geist Mono's
    advance (600/1000 upem, asserted below) — and 0.71em tall, the height of a
    lowercase `d`. Same constants as `TerminalMark` in
    frontend/digiweb/web/src/components/symbols/terminal-marks.tsx;
  * the copy comes from HEADLINES below, which must stay in step with each site's
    own <h1>. The card is not a place to invent a new tagline.

Usage:
    frontend/digiweb/brand/build-og.py           # write both cards
    frontend/digiweb/brand/build-og.py --check    # verify SVGs are in sync
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

BRAND = Path(__file__).resolve().parent
REPO_ROOT = BRAND.parents[2]
FONT = (
    REPO_ROOT / "node_modules" / "geist" / "dist" / "fonts" / "geist-mono" / "GeistMono-Regular.ttf"
)
OUT_DIR = BRAND / "og"

WIDTH, HEIGHT = 1200, 630  # the size every unfurler expects; og.png was already this
BG, INK, MUTE = "#0A0E0C", "#ECEEF0", "#8A9199"

# One character cell, matching TerminalMark's CURSOR constant.
CELL_EM = 0.6
CURSOR_H_EM = 0.71

WORD_EM = 116  # 11 cells at 0.6em = 766px, inside 1200 with room to breathe
LINE_EM = 30
DOMAIN_EM = 22

# Must track each site's own hero. If a hero changes, change this with it.
HEADLINES = {
    "digithings": {
        "word": "digithings",
        "line": "AI infrastructure in a glass box you own.",
        "domain": "digithings.ai",
    },
    "digiquant": {
        "word": "digiquant",
        "line": "A quant research desk in a glass box you own.",
        "domain": "digiquant.io",
    },
}


def _font() -> TTFont:
    if not FONT.exists():
        raise SystemExit(
            f"missing {FONT.relative_to(REPO_ROOT)} — run `npm install` first; the Geist "
            "fonts ship in the geist package, not in this repo"
        )
    font = TTFont(FONT)
    upem = font["head"].unitsPerEm
    advance = font["hmtx"]["d"][0]
    # The whole layout assumes a monospace 0.6em advance, the same number
    # `.term-cursor` is 0.6em wide for. Fail loudly if a font update changes it
    # rather than shipping a card with the cursor a fraction of a cell off.
    if round(advance / upem, 4) != CELL_EM:
        raise SystemExit(f"Geist Mono advance is {advance}/{upem}, expected {CELL_EM}em")
    return font


def outline(font: TTFont, text: str, em: float, x: float, baseline: float, fill: str) -> str:
    """`text` as embedded glyph paths, laid out on a monospace grid."""
    upem = font["head"].unitsPerEm
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = em / upem
    step = em * CELL_EM
    parts = []
    for index, char in enumerate(text):
        if char == " ":
            continue
        name = cmap.get(ord(char))
        if name is None:
            raise SystemExit(f"{char!r} is not in Geist Mono — pick different copy")
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        commands = pen.getCommands()
        if not commands:
            continue
        # y-flip: font units are y-up, SVG is y-down.
        parts.append(
            f'<g transform="translate({x + index * step:.2f} {baseline:.2f}) '
            f'scale({scale:.6f} {-scale:.6f})"><path d="{commands}" fill="{fill}"/></g>'
        )
    return "\n    ".join(parts)


def card(font: TTFont, key: str) -> str:
    spec = HEADLINES[key]
    word, line, domain = spec["word"], spec["line"], spec["domain"]

    cells = len(word) + 1  # + the cursor
    lockup_w = cells * WORD_EM * CELL_EM
    x0 = (WIDTH - lockup_w) / 2
    # Optically centre the wordmark + tagline as one block inside the frame,
    # treating the domain as a footer rather than part of the block. Centring all
    # three together left a visibly larger gap above the wordmark than below it.
    baseline = 275

    cursor_x = x0 + len(word) * WORD_EM * CELL_EM
    cursor_w = WORD_EM * CELL_EM
    cursor_h = WORD_EM * CURSOR_H_EM

    line_w = len(line) * LINE_EM * CELL_EM
    domain_w = len(domain) * DOMAIN_EM * CELL_EM

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <!-- GENERATED by frontend/digiweb/brand/build-og.py — do not hand-edit.
       Wordmark is outlined from GeistMono-Regular (400), not SVG <text>: there is
       no Geist installed for librsvg, so <text> would rasterise in a fallback
       face. Cursor is one character cell (0.6em) by 0.71em, the height of a `d`. -->
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>
  <rect x="40.5" y="40.5" width="{WIDTH - 81}" height="{HEIGHT - 81}"
        fill="none" stroke="{MUTE}" stroke-opacity="0.28" stroke-width="1"/>
  <g>
    {outline(font, word, WORD_EM, x0, baseline, INK)}
  </g>
  <rect x="{cursor_x:.2f}" y="{baseline - cursor_h:.2f}"
        width="{cursor_w:.2f}" height="{cursor_h:.2f}" fill="{INK}"/>
  <g>
    {outline(font, line, LINE_EM, (WIDTH - line_w) / 2, 375, MUTE)}
  </g>
  <g>
    {outline(font, domain, DOMAIN_EM, (WIDTH - domain_w) / 2, 545, MUTE)}
  </g>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    font = _font()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cards = {key: card(font, key) for key in HEADLINES}

    if args.check:
        for key, svg in cards.items():
            target = OUT_DIR / f"{key}-og.svg"
            if not target.exists() or target.read_text(encoding="utf-8") != svg:
                print(f"❌  {target.name} is stale — re-run build-og.py", file=sys.stderr)
                return 1
        print("og cards: in sync ✅")
        return 0

    for key, svg in cards.items():
        (OUT_DIR / f"{key}-og.svg").write_text(svg, encoding="utf-8")

    script = """
const sharp = require("sharp"), fs = require("fs"), dir = process.argv[1];
const keys = %s;
(async () => {
  for (const k of keys) {
    const svg = fs.readFileSync(`${dir}/${k}-og.svg`);
    const f = `${dir}/${k}-og.png`;
    await sharp(svg).png({ compressionLevel: 9 }).toFile(f);
    const m = await sharp(f).metadata();
    console.log(`  ${k}-og.png  ${m.width}x${m.height}  ${(fs.statSync(f).size / 1024).toFixed(1)}KB`);
  }
})().catch((e) => { console.error(e.message); process.exit(1); });
""" % list(HEADLINES)
    subprocess.run(["node", "-e", script, str(OUT_DIR)], cwd=REPO_ROOT, check=True)
    print("\nog cards: rebuilt ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
