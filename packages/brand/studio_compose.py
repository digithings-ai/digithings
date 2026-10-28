"""Compose a static brand-studio frame.

Mirrors the export path in ``apps/digiweb/components/brand/studio/studio-app.ts``:
a field (or a solid ground), then either the wordmark mask or the logo.
The studio rule is one or the other, never both. Glints and strays are dropped.
The default theme forces accent = ink, so a monochrome logo stays monochrome.
"""

from __future__ import annotations

import re
from pathlib import Path

STUDIO = Path(__file__).resolve().parent / "studio"

DARK_BG = "#0A0E0C"
DARK_INK = "#ECEEF0"
LIGHT_BG = "#FBFBF9"
LIGHT_INK = "#14181B"

# packages/design/tokens.css — digiquant --up / --down, dark then light.
QUANT_UP = {"dark": "#3DD6C4", "light": "#0E8C7F"}
QUANT_DOWN = {"dark": "#E5533E", "light": "#B2452E"}


def mix(a: str, b: str, weight: float) -> str:
    """Same channel mix the studio uses (``mix`` in studio-app.ts)."""

    def channels(color: str) -> tuple[int, int, int]:
        text = color.strip()
        if text.startswith("#"):
            hex_color = text[1:]
            return (
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16),
            )
        match = re.fullmatch(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", text)
        if match is None:
            raise SystemExit(f"cannot parse colour {color!r}")
        return tuple(int(part) for part in match.groups())  # type: ignore[return-value]

    left = channels(a)
    right = channels(b)
    mixed = [round(left[i] * weight + right[i] * (1 - weight)) for i in range(3)]
    return f"rgb({mixed[0]}, {mixed[1]}, {mixed[2]})"


def _svg_inner(source: str) -> tuple[str, float, float]:
    match = re.search(r'viewBox="([^"]+)"', source)
    if match is None:
        raise SystemExit("studio svg is missing a viewBox")
    parts = match.group(1).split()
    width = float(parts[2])
    height = float(parts[3])
    inner = re.sub(r"^[\s\S]*?<svg[^>]*>", "", source)
    inner = re.sub(r"</svg>\s*$", "", inner)
    return inner, width, height


def _read(name: str) -> str:
    path = STUDIO / name
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return path.read_text(encoding="utf-8")


def wordmark_inner(ink: str) -> tuple[str, float, float]:
    inner, width, height = _svg_inner(_read("wordmark-mask.svg"))
    return inner.replace('fill="currentColor"', f'fill="{ink}"'), width, height


def field_layer(name: str, ink: str, width: float, height: float) -> str:
    inner, field_w, field_h = _svg_inner(_read(f"field-{name}.svg"))
    painted = inner.replace('fill="currentColor"', f'fill="{ink}"')
    return (
        f'<svg x="0" y="0" width="{width:.4f}" height="{height:.4f}" '
        f'viewBox="0 0 {field_w:.4f} {field_h:.4f}" preserveAspectRatio="none" '
        f'shape-rendering="crispEdges">{painted}</svg>'
    )


def _classes(attrs: str) -> set[str]:
    match = re.search(r'class="([^"]*)"', attrs)
    if match is None:
        return set()
    return set(match.group(1).split())


def static_logo(source: str, bg: str, ink: str, *, accent: str, dim: str) -> str:
    """Recolor ``logo-animated.svg`` the way the studio's static export does.

    ``accent`` and ``dim`` override those two bands before the face shade
    (left 0.78, right 0.56, top full) is mixed toward the ground.
    """

    def replace(match: re.Match[str]) -> str:
        attrs = match.group(1)
        classes = _classes(attrs)
        if classes & {"glint", "stray"}:
            return ""
        if "accent" in classes:
            tone = accent
        elif "mid" in classes:
            tone = mix(ink, bg, 0.52)
        elif "dim" in classes:
            tone = dim
        else:
            tone = ink
        if "f-left" in classes:
            fill = mix(tone, bg, 0.78)
        elif "f-right" in classes:
            fill = mix(tone, bg, 0.56)
        else:
            fill = tone
        clean = re.sub(r'\sclass="[^"]*"', "", attrs)
        clean = re.sub(r'\sstyle="[^"]*"', "", clean)
        return f'<rect fill="{fill}"{clean}/>'

    return re.sub(r"<rect\b([^>]*?)(?:/>|>\s*</rect>)", replace, source)


def logo_mark_inner(ink: str) -> tuple[str, float, float]:
    """The static Jenga mark. Opacities are already the face shades."""
    inner, width, height = _svg_inner(_read("logo-mark.svg"))
    return inner.replace('fill="currentColor"', f'fill="{ink}"'), width, height


def quant_logo_inner(mode: str) -> tuple[str, float, float]:
    bg = DARK_BG if mode == "dark" else LIGHT_BG
    ink = DARK_INK if mode == "dark" else LIGHT_INK
    inner, width, height = _svg_inner(_read("logo-animated.svg"))
    painted = static_logo(
        inner,
        bg,
        ink,
        accent=QUANT_UP[mode],
        dim=QUANT_DOWN[mode],
    )
    return painted, width, height


def place(
    inner: str,
    box_w: float,
    box_h: float,
    canvas_w: float,
    canvas_h: float,
    size_pct: float,
) -> str:
    """Centre ``inner`` so its height is ``size_pct`` percent of the canvas."""
    size = size_pct / 100 * canvas_h
    scale = size / box_h
    return (
        f'<g transform="translate({canvas_w / 2:.4f} {canvas_h / 2:.4f}) '
        f"scale({scale:.4f}) "
        f'translate({-box_w / 2:.4f} {-box_h / 2:.4f})" '
        f'shape-rendering="crispEdges">{inner}</g>'
    )


def frame(width: int, height: int, *parts: str, comment: str) -> str:
    body = "".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges">'
        f"<!-- {comment} -->{body}</svg>\n"
    )


# --- pixel wordmarks -------------------------------------------------------
#
# The 4×4 wordmark is the hero-banner pixel font with every font pixel split
# into 16 sub-pixels. Each font pixel takes one brightness step, and each
# sub-pixel jitters ±0.05 around it, rounded to 0.05. That is how
# ``wordmark-mask.svg`` (DIGITHINGS) is drawn; ``pixel_wordmark_inner`` draws
# any module word the same way, from the same font and the module's own glyph
# overrides, so a DIGIQUANT card is the same mark family, not a redraw.

HERO_BANNER = Path(__file__).resolve().parents[1] / "hero-banner" / "src"
# DIGITHINGS' animation steps (packages/hero-banner/src/definitions/index.ts).
WORDMARK_STEPS = (0.36, 0.5, 0.66, 0.82, 1.0)
SUBPIXELS = 4
GLYPH_GAP = 2

_GLYPH_LINE = re.compile(r'^\s*"?([A-Z0-9])"?:\s*\[([^\]]*)\]', re.M)


def _glyph_rows(block: str) -> dict[str, list[str]]:
    return {key: re.findall(r'"([.#]+)"', rows) for key, rows in _GLYPH_LINE.findall(block)}


def pixel_font(module: str | None = None) -> dict[str, list[str]]:
    """The 7×10 family font, with ``module``'s glyph overrides applied."""
    glyphs = _glyph_rows((HERO_BANNER / "font.ts").read_text(encoding="utf-8"))
    if module:
        source = (HERO_BANNER / "definitions" / "index.ts").read_text(encoding="utf-8")
        match = re.search(
            rf"export const {module.upper()}: BannerDefinition = \{{([\s\S]*?)\n\}};", source
        )
        if match is None:
            raise SystemExit(f"no {module.upper()} banner definition in hero-banner")
        overrides = re.search(r"glyphs:\s*\{([\s\S]*?)\n\s*\},", match.group(1))
        if overrides:
            glyphs.update(_glyph_rows(overrides.group(1)))
    for key, rows in glyphs.items():
        if len(rows) != 10 or any(len(row) != 7 for row in rows):
            raise SystemExit(f"glyph {key!r} is not 7×10")
    return glyphs


def pixel_cells(text: str, glyphs: dict[str, list[str]]) -> list[tuple[int, int]]:
    """Lit font pixels (column, row) for ``text`` with a two-pixel gap."""
    cells = []
    for index, char in enumerate(text):
        rows = glyphs.get(char)
        if rows is None:
            raise SystemExit(f"{char!r} is not in the pixel font")
        for row, line in enumerate(rows):
            for col, value in enumerate(line):
                if value == "#":
                    cells.append((index * (7 + GLYPH_GAP) + col, row))
    return cells


def _lcg(seed: int):
    state = seed & 0xFFFFFFFF
    while True:
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        yield state / 0x100000000


def pixel_wordmark_inner(
    text: str, ink: str, *, module: str | None = None, seed: int
) -> tuple[str, float, float]:
    """``text`` as a 4×4 sub-pixel mask, the same shape as ``wordmark-mask.svg``."""
    glyphs = pixel_font(module)
    width = len(text) * 7 + (len(text) - 1) * GLYPH_GAP
    rand = _lcg(seed)
    step = 1 / SUBPIXELS
    rects = []
    for col, row in pixel_cells(text, glyphs):
        base = WORDMARK_STEPS[int(next(rand) * len(WORDMARK_STEPS))]
        for sy in range(SUBPIXELS):
            for sx in range(SUBPIXELS):
                jitter = (next(rand) - 0.5) * 0.1
                alpha = min(1.0, max(0.05, round((base + jitter) / 0.05) * 0.05))
                rects.append(
                    f'<rect x="{col + sx * step:g}" y="{row + sy * step:g}" '
                    f'width="{step:g}" height="{step:g}" fill="{ink}" opacity="{alpha:.2f}"/>'
                )
    return "".join(rects), float(width), 10.0
