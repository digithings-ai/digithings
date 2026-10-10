#!/usr/bin/env python3
"""Render digivoice TUI frames to PNG for the visual gate.

Calls ``bun scripts/shoot.js`` for each view (same repo, no network) and paints
the captured character spans with Pillow. The PNGs are throwaway review
artifacts: write them to /tmp or the run scratch dir, never the repo.

Requires Python >= 3.10 and Pillow:

    uv run --with pillow python scripts/capture.py --out /tmp/dvo-shots

Each view renders the real ``mountDigivoice`` app against a deterministic stub
session, so a screenshot never depends on the machine's models, history or mic.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOOT = HERE / "shoot.js"

FONT_CANDIDATES = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)

# name -> (font pixels, target px (w, h)); cols/rows are derived from the font
# metrics so the character grid fills the target exactly and the wordmark fits.
SIZES = {
    "phone": (10, (390, 844)),
    "desktop": (15, (1440, 900)),
}

SCREENS = ("home", "settings", "system", "doctor", "history")

CANVAS_BG = (11, 12, 14, 255)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            index = 1 if (bold and path.endswith(".ttc")) else 0
            return ImageFont.truetype(path, size, index=index)
        except OSError:
            continue
    raise SystemExit("no monospace font found; tried: " + ", ".join(FONT_CANDIDATES))


def as_rgba(ints: list[int] | None) -> tuple[int, int, int, int] | None:
    if not ints:
        return None
    if len(ints) >= 4:
        return (ints[0], ints[1], ints[2], ints[3])
    if len(ints) == 3:
        return (ints[0], ints[1], ints[2], 255)
    return None


def shoot(cols: int, rows: int, screen: str) -> dict:
    env = dict(os.environ)
    bun_dir = str(Path.home() / ".bun" / "bin")
    env["PATH"] = env.get("PATH", "") + os.pathsep + bun_dir
    proc = subprocess.run(
        ["bun", str(SHOOT), str(cols), str(rows), screen],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"shoot {screen} failed:\n{proc.stderr.strip()}")
    return json.loads(proc.stdout)


def render(frame: dict, font_px: int) -> Image.Image:
    font = load_font(font_px)
    bold = load_font(font_px, bold=True)
    advance = max(1, round(font.getlength("M")))
    cell_h = max(1, round(font_px * 1.45))

    cols = int(frame["cols"])
    rows = int(frame["rows"])
    img = Image.new("RGBA", (cols * advance, rows * cell_h), CANVAS_BG)
    draw = ImageDraw.Draw(img)

    for y, line in enumerate(frame["lines"]):
        x = 0
        for span in line:
            text = span.get("text") or ""
            fg = as_rgba(span.get("fg")) or (231, 234, 236, 255)
            back = as_rgba(span.get("bg"))
            width = advance * len(text)
            if width <= 0:
                continue
            if back and (back[0] or back[1] or back[2]):
                draw.rectangle([x, y * cell_h, x + width, y * cell_h + cell_h], fill=back)
            face = bold if int(span.get("attributes") or 0) & 1 else font
            draw.text((x, y * cell_h), text, font=face, fill=fg)
            x += width
    return img


def fit(img: Image.Image, target: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", target, CANVAS_BG)
    canvas.paste(img, (0, 0))
    return canvas


def grid(size_name: str) -> tuple[int, int, int, tuple[int, int]]:
    """cols/rows that fill the target px at this font size."""
    font_px, target = SIZES[size_name]
    font = load_font(font_px)
    advance = max(1, round(font.getlength("M")))
    cell_h = max(1, round(font_px * 1.45))
    cols = max(40, target[0] // advance)
    rows = max(16, target[1] // cell_h)
    return cols, rows, font_px, target


def main() -> int:
    parser = argparse.ArgumentParser(description="Render digivoice TUI screens to PNG.")
    parser.add_argument("--out", required=True, help="output directory (use /tmp)")
    parser.add_argument("--sizes", nargs="*", default=sorted(SIZES), help="which sizes to render")
    parser.add_argument("--screens", nargs="*", default=list(SCREENS), help="which screens")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for size_name in args.sizes:
        cols, rows, font_px, target = grid(size_name)
        for screen in args.screens:
            frame = shoot(cols, rows, screen)
            img = fit(render(frame, font_px), target)
            dest = out / f"{screen}-{size_name}.png"
            img.save(dest)
            written.append(dest)
            print(f"{dest}  {img.width}x{img.height}")

    print(f"\n{len(written)} screenshots in {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
