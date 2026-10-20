"""7×10 DIGIVOICE glyph map.

The home header in ``tui.py`` paints these glyphs as five half-block rows
in the terminal foreground. This module keeps the glyph table and the
cell sampler.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Letters stay grayscale. The home header uses this table; menu selection does not.
TEAL_RGB = (61, 214, 196)
_RESET = "\x1b[0m"

# PixelWordmark.tsx
STEPS: tuple[float, ...] = (0.36, 0.5, 0.66, 0.82, 1.0)
WORDMARK_SEED = 0xD161
GLINT_COUNT = 13
STRAY_COUNT = 70

# D/I/G/T/H/N/S copied from PixelWordmark.tsx. V/O/C/E drawn in the same
# 7×10 two-pixel stroke language so DIGIVOICE matches DIGITHINGS.
PIXEL_GLYPHS: dict[str, tuple[str, ...]] = {
    "D": (
        "######.",
        "#######",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "#######",
        "######.",
    ),
    "I": (
        "#######",
        "#######",
        "..##...",
        "..##...",
        "..##...",
        "..##...",
        "..##...",
        "..##...",
        "#######",
        "#######",
    ),
    "G": (
        ".#####.",
        "#######",
        "##.....",
        "##.....",
        "##..###",
        "##..###",
        "##...##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "T": (
        "#######",
        "#######",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
    ),
    "H": (
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "#######",
        "#######",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
    ),
    "N": (
        "##...##",
        "###..##",
        "###..##",
        "##.#.##",
        "##.#.##",
        "##..###",
        "##..###",
        "##...##",
        "##...##",
        "##...##",
    ),
    "S": (
        ".######",
        "#######",
        "##.....",
        "##.....",
        "######.",
        "######.",
        ".....##",
        ".....##",
        "#######",
        "######.",
    ),
    # Centered half-block header (f62e5982d): a block V, not the pointed landing V.
    "V": (
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        ".#####.",
        "..###..",
    ),
    "O": (
        ".#####.",
        "#######",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "C": (
        ".#####.",
        "#######",
        "##.....",
        "##.....",
        "##.....",
        "##.....",
        "##.....",
        "##.....",
        "#######",
        ".#####.",
    ),
    "E": (
        "#######",
        "#######",
        "##.....",
        "##.....",
        "######.",
        "######.",
        "##.....",
        "##.....",
        "#######",
        "#######",
    ),
}


def _u32(n: int) -> int:
    return n & 0xFFFFFFFF


def _i32(n: int) -> int:
    n = _u32(n)
    return n - 0x100000000 if n >= 0x80000000 else n


def _imul(a: int, b: int) -> int:
    return _i32(_u32(a) * _u32(b))


def mulberry32(seed: int) -> Callable[[], float]:
    """JS ``mulberry32`` from PixelWordmark.tsx (signed-32 state, unit interval)."""
    state = _i32(seed)

    def rand() -> float:
        nonlocal state
        state = _i32(state + 0x6D2B79F5)
        t = _imul(state ^ (_u32(state) >> 15), 1 | state)
        t = _i32(_i32(t) + _imul(t ^ (_u32(t) >> 7), 61 | t)) ^ _i32(t)
        t = _i32(t)
        return _u32(t ^ (_u32(t) >> 14)) / 4294967296.0

    return rand


def cell_hash(a: int, b: int) -> float:
    """JS ``hash`` from pixel-field.ts — deterministic 0..1 noise."""
    n = _i32(_imul(0x165667B1, a) + _imul(0x27D4EB2F, b))
    n = _imul(n ^ (_u32(n) >> 13), 0x4BF19F61)
    return _u32(n ^ (_u32(n) >> 16)) / 4294967296.0


@dataclass(frozen=True, slots=True)
class PixelCell:
    x: int
    y: int
    kind: str
    glint: bool = False
    delay_ms: int = 0
    duration_ms: int = 0
    a: float = 1.0
    b: float = 1.0
    c: float = 1.0
    f: float = 1.0
    glint_delay_ms: int = 0
    glint_period_ms: int = 0


def letter_gap(cols: int, letters: int) -> int:
    """Landing uses a 2-cell gap (x += 9). Shrink only when the terminal is tight."""
    for gap in (2, 1, 0):
        width = letters * 7 + max(0, letters - 1) * gap
        if width <= max(1, cols - 2):
            return gap
    return 0


def grid_width(word: str, gap: int) -> int:
    n = max(1, len(word))
    return n * 7 + max(0, n - 1) * gap


def word_cells(
    word: str = "DIGIVOICE", gap: int = 2
) -> tuple[tuple[PixelCell, ...], tuple[PixelCell, ...]]:
    """Letter cells + 70 strays. Same rand consumption as PixelWordmark.tsx."""
    rand = mulberry32(WORDMARK_SEED)
    letters_n = max(1, len(STEPS))

    def pick() -> float:
        return STEPS[int(rand() * letters_n) % letters_n]

    used: set[tuple[int, int]] = set()
    letters: list[PixelCell] = []
    x = 0
    for index, ch in enumerate(word.upper()):
        if index:
            x += gap
        glyph = PIXEL_GLYPHS.get(ch)
        if glyph is not None:
            for y, row in enumerate(glyph):
                for c, mark in enumerate(row):
                    if mark != "#":
                        continue
                    px = x + c
                    letters.append(PixelCell(px, y, "letter"))
                    used.add((px, y))
        x += 7
    glint: set[int] = set()
    if letters:
        while len(glint) < min(GLINT_COUNT, len(letters)):
            glint.add(int(rand() * len(letters)) % len(letters))
    painted: list[PixelCell] = []
    for index, cell in enumerate(letters):
        is_glint = index in glint
        extra_g = extra_gp = 0
        delay = int(rand() * 692 + 8)
        duration = int(rand() * 380 + 240)
        a, b, c, f = pick(), pick(), pick(), pick()
        if is_glint:
            extra_g = int(rand() * 6500 + 2500)
            extra_gp = int(rand() * 8000 + 7000)
        painted.append(
            PixelCell(
                cell.x,
                cell.y,
                "letter",
                glint=is_glint,
                delay_ms=delay,
                duration_ms=duration,
                a=a,
                b=b,
                c=c,
                f=f,
                glint_delay_ms=extra_g,
                glint_period_ms=extra_gp,
            )
        )
    width = max(grid_width(word.upper(), gap), 1)
    stray: list[PixelCell] = []
    attempts = 0
    while len(stray) < STRAY_COUNT and attempts < 4000:
        attempts += 1
        px = int(rand() * width)
        py = int(rand() * 10)
        key = (px, py)
        if key in used:
            continue
        used.add(key)
        stray.append(
            PixelCell(
                px,
                py,
                "stray",
                delay_ms=int(rand() * 1100),
                duration_ms=int(rand() * 140 + 60),
            )
        )
    return tuple(painted), tuple(stray)


def _gray_sgr(alpha: float, glint: bool, x: int, y: int, t_ms: int) -> str:
    """Per-glyph grayscale. Glints flash brighter; idle noise is a small wobble."""
    if glint:
        return "\x1b[1;38;2;255;255;255m"
    base = int(96 + max(0.0, min(1.0, alpha)) * 144)
    wobble = int(cell_hash(x + (t_ms // 160), y) * 28) - 14
    gray = max(72, min(235, base + wobble))
    return f"\x1b[38;2;{gray};{gray};{gray}m"


def _sgr(kind: str) -> str:
    if kind == "dim":
        return "\x1b[2m"
    if kind == "gray":
        return "\x1b[38;2;168;168;168m"
    if kind == "gray-dim":
        return "\x1b[2;38;2;140;140;140m"
    return ""


def _glinting(cell: PixelCell, t_ms: int) -> bool:
    if not cell.glint:
        return False
    if cell.glint_period_ms and t_ms >= cell.glint_delay_ms:
        elapsed = (t_ms - cell.glint_delay_ms) % cell.glint_period_ms
        if elapsed < max(80, int(0.05 * cell.glint_period_ms)):
            return True
    # Fast sparkle so the 160ms home pulse reads as top-bar motion.
    return (cell.x * 13 + cell.y * 7 + t_ms // 160) % 8 == 0


def _lit_letters(letters: tuple[PixelCell, ...], frac: float) -> set[tuple[int, int]]:
    if frac <= 0:
        return set()
    ordered = sorted(letters, key=lambda cell: (cell.x * 13 + cell.y * 7) % 97)
    if frac >= 1:
        return {(cell.x, cell.y) for cell in ordered}
    count = int(len(ordered) * frac)
    if count == 0 and ordered:
        count = 1
    return {(cell.x, cell.y) for cell in ordered[:count]}


def _trail_alpha(col: int, row: int, pointer: tuple[int, int] | None) -> float:
    """Local teal glow around the pointer. No cursor glyph."""
    if pointer is None:
        return 0.0
    dx = col - pointer[0]
    dy = row - pointer[1]
    dist2 = dx * dx + dy * dy
    if dist2 == 0:
        return 0.9
    if dist2 <= 2:
        return 0.55
    if dist2 <= 5:
        return 0.28
    return 0.0


def _field_on(col: int, row: int, cols: int, rows: int, t_ms: int) -> bool:
    if cols <= 0 or rows <= 0:
        return False
    cx = (cols - 1) / 2
    cy = (rows - 1) * 0.46
    rx = max(1.0, cols * 0.42)
    ry = max(1.0, rows * 0.55)
    nx = (col - cx) / rx
    ny = (row - cy) / ry
    radial = (nx * nx + ny * ny) ** 0.5
    # Sparse land-like dots; a slow hash flip is the idle shimmer.
    if cell_hash(col, row) > 0.16:
        return False
    if cell_hash(col + 17, row + (t_ms // 180)) > 0.62:
        return False
    return radial < 1.35


def render_pixel_hero(
    word: str = "DIGIVOICE",
    *,
    cols: int = 100,
    rows: int = 16,
    t_ms: int = 0,
    frac: float = 1.0,
    ansi: bool = False,
    pointer: tuple[int, int] | None = None,
    field: bool = True,
) -> list[str]:
    """``rows`` lines of the DIGIVOICE block-pixel field (or the 10-row lockup)."""
    word = word.upper()
    if rows <= 0 or cols <= 0:
        return []
    gap = letter_gap(cols, max(1, len(word)))
    width = grid_width(word, gap)
    letters, stray = word_cells(word, gap)
    lit = _lit_letters(letters, frac)
    by_xy = {(cell.x, cell.y): cell for cell in letters}
    stray_on = 0.0 < frac < 1.0
    letter_h = 10
    if field:
        ox = max(0, (cols - width) // 2)
        oy = max(0, (rows - letter_h) // 2)
        out_w, out_h = cols, rows
    else:
        ox = oy = 0
        out_w, out_h = max(width, 1), letter_h
    letter_cells = {(ox + cell.x, oy + cell.y) for cell in letters if (cell.x, cell.y) in lit}
    stray_cells = {(ox + cell.x, oy + cell.y) for cell in stray} if stray_on else set()
    lines: list[str] = []
    for y in range(out_h):
        parts: list[str] = []
        dirty = ""
        for x in range(out_w):
            lx, ly = x - ox, y - oy
            cell = by_xy.get((lx, ly))
            ch = " "
            kind = ""
            if cell is not None and (x, y) in letter_cells:
                ch = "█"
                kind = _gray_sgr(cell.f, _glinting(cell, t_ms), cell.x, cell.y, t_ms)
            elif (x, y) in stray_cells:
                ch = "░"
                kind = "gray-dim"
            else:
                trail = _trail_alpha(x, y, pointer) if field else 0.0
                ambient = field and _field_on(x, y, out_w, out_h, t_ms)
                if trail > 0.5:
                    ch = "█"
                    kind = "gray"
                elif trail > 0:
                    ch = "░"
                    kind = "gray-dim"
                elif ambient and (x, y) not in letter_cells:
                    ch = "·"
                    kind = "dim"
            if ansi:
                want = kind if kind.startswith("\x1b") else _sgr(kind)
                if want != dirty:
                    if dirty:
                        parts.append(_RESET)
                    if want:
                        parts.append(want)
                    dirty = want
            parts.append(ch)
        if dirty and ansi:
            parts.append(_RESET)
        lines.append("".join(parts))
    return lines


__all__ = [
    "GLINT_COUNT",
    "PIXEL_GLYPHS",
    "STEPS",
    "STRAY_COUNT",
    "TEAL_RGB",
    "WORDMARK_SEED",
    "PixelCell",
    "cell_hash",
    "grid_width",
    "letter_gap",
    "mulberry32",
    "render_pixel_hero",
    "word_cells",
]
