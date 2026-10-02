"""Shared stdlib TUI primitives: fullscreen frames, pixel wordmark, menus.

Home (`home.py`) and setup (`setup.py`) draw from here. A TTY takes the
viewport: alternate screen, content centered, one repaint per key. The home
hero is the DIGIVOICE pixel wordmark (half-block cells, brief build-in, then
soft teal particles and a quiet glint — landing chrome, not a rainbow title).
Menus use a step rail — active section marked, the current row checked and
inverted — so the shell does not read as a flat wizard list.

Non-TTY paths (StringIO / pipes / agents) stay on the numbered prompt so
`--print` / `DIGIVOICE_SETUP_NONINTERACTIVE` / `--json` and the unit tests
that feed StringIO never hang and never gain cursor codes.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import sys
import termios
import time
import tty
from collections.abc import Sequence
from typing import TextIO

# TTY contract:
# - Full viewport: alternate screen while a shell is open, CSI clear + home
#   on the first paint, cursor-home redraws after that. Never scroll-append.
# - Screen control (alt / clear / home / hide-cursor) follows the TTY + TERM,
#   not color. `NO_COLOR` only skips SGR — otherwise frames append and stack.
# - Menu loops hold raw *input* so CSI arrows stay intact, but keep OPOST so
#   NL→CRLF still runs. Full setraw clears OPOST; frames joined with bare LF
#   then staircase (scattered labels / broken wordmark) on Terminal.app.
# - Color is SGR on the terminal's own foreground, so light and dark both work.
#   `NO_COLOR` or `TERM=dumb` skips color. `DIGIVOICE_REDUCE_MOTION=1` skips
#   the build-in and the idle pulse.

_ANSI_HIDE = "\x1b[?25l"
_ANSI_SHOW = "\x1b[?25h"
_ANSI_CLEAR_HOME = "\x1b[2J\x1b[H"
_ANSI_HOME = "\x1b[H"
_ANSI_CLEAR_EOL = "\x1b[K"
_ANSI_CLEAR_DOWN = "\x1b[J"
_ANSI_ALT_ON = "\x1b[?1049h"
_ANSI_ALT_OFF = "\x1b[?1049l"
_ANSI_RESET = "\x1b[0m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# digithings landing accent (teal). Header chrome stays one hue — no rainbow title.
_TEAL_RGB = (61, 214, 196)
_TEAL = "\x1b[38;2;61;214;196m"

_STATUS_SYMBOLS = frozenset({"▦", "▥", "■", "□", "▤"})

_DEFAULT_SUBTITLE = "digivoice setup · local speech config"
_KICKER = "digivoice"

# Nested home → setup stays on one alternate screen.
_fullscreen_depth = 0

# Pixel glyphs are 7 wide x 10 tall, `#` = filled. D/I/G/T/H/N/S copied from
# apps/digithings-web/components/landing/PixelWordmark.tsx; V/O/C/E drawn in
# the same block language for the DIGIVOICE wordmark.
_PIXEL_GLYPHS: dict[str, tuple[str, ...]] = {
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

TUI_FOOTER_HINT = "↑↓ move · enter select · esc back · q quit"

Group = tuple[str, int, int]


def _use_screen() -> bool:
    """Cursor / alt-screen / clear codes. Independent of NO_COLOR."""
    return os.environ.get("TERM", "") != "dumb"


def _use_ansi() -> bool:
    """SGR color only. NO_COLOR must not disable clear/home (double-paint)."""
    if os.environ.get("NO_COLOR"):
        return False
    return _use_screen()


def _reduce_motion() -> bool:
    return bool(os.environ.get("DIGIVOICE_REDUCE_MOTION"))


def _set_menu_raw(fd: int) -> None:
    """Raw input for the menu loop, but keep OPOST so frame newlines stay CRLF.

    ``tty.setraw`` clears ``OPOST``. Digivoice paints while that mode is held, and
    frames are joined with ``\n``. With OPOST off the terminal treats LF as
    "down one row, same column" — every line shifts right and the home layout
    explodes. Re-enable ``OPOST|ONLCR`` after setraw so paints match cooked
    intro frames; input stays non-canonical / no-echo for CSI reads.
    """
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    attrs[1] |= termios.OPOST | termios.ONLCR
    termios.tcsetattr(fd, termios.TCSADRAIN, attrs)


def _is_tty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except Exception:
        return False


def _term_size() -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=(100, 36))
    return max(40, size.columns), max(16, size.lines)


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _fit(text: str, width: int, *, truncate: bool = True) -> str:
    if len(text) > width:
        if not truncate or width < 2:
            return text
        return text[: width - 1] + "…"
    return text.ljust(width)


def _paint(plain: str, style: str, ansi: bool) -> str:
    """Theme-safe SGR. Teal selection; dim chrome; body uses default fg."""
    if not ansi or not plain:
        return plain
    if style == "bar" and plain[:1] in {"│", "|"}:
        return f"\x1b[2m{plain[:1]}{_ANSI_RESET}{_TEAL}\x1b[7;1m{plain[1:]}{_ANSI_RESET}"
    if style == "bar":
        return f"{_TEAL}\x1b[7;1m{plain}{_ANSI_RESET}"
    if style in {"item", "kv"} and plain[:1] in {"│", "|"}:
        return f"\x1b[2m{plain[:1]}{_ANSI_RESET}{plain[1:]}"
    if style == "step-on":
        return f"{_TEAL}\x1b[1m{plain}{_ANSI_RESET}"
    return f"\x1b[2m{plain}{_ANSI_RESET}"


def fullscreen_enter(stdout: TextIO) -> None:
    """Take the alternate screen. Nested calls (home → setup) keep one buffer."""
    global _fullscreen_depth
    if not _is_tty(stdout) or not _use_screen():
        return
    if _fullscreen_depth == 0:
        try:
            stdout.write(_ANSI_ALT_ON + _ANSI_HIDE)
            stdout.flush()
        except (OSError, ValueError):
            return
    _fullscreen_depth += 1


def fullscreen_leave(stdout: TextIO) -> None:
    """Restore the caller's screen when the outermost shell exits."""
    global _fullscreen_depth
    if _fullscreen_depth == 0:
        return
    _fullscreen_depth -= 1
    if _fullscreen_depth == 0 and _is_tty(stdout) and _use_screen():
        try:
            stdout.write(_ANSI_SHOW + _ANSI_ALT_OFF)
            stdout.flush()
        except (OSError, ValueError):
            pass


def _letter_gap(cols: int, letters: int) -> int:
    for gap in (2, 1, 0):
        width = letters * 7 + max(0, letters - 1) * gap
        if width <= max(1, cols - 2):
            return gap
    return 0


def _pixel_grid(word: str, gap: int) -> list[list[bool]]:
    rows: list[list[bool]] = [[] for _ in range(10)]
    for index, ch in enumerate(word.upper()):
        if index:
            for row in rows:
                row.extend([False] * gap)
        glyph = _PIXEL_GLYPHS.get(ch)
        for y in range(10):
            if glyph is None:
                rows[y].extend([False] * 7)
            else:
                rows[y].extend(cell == "#" for cell in glyph[y])
    return rows


def _filled_cells(grid: list[list[bool]]) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for y, row in enumerate(grid):
        for x, on in enumerate(row):
            if on:
                cells.append((x, y))
    return cells


def _glint_index(cells: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    if not cells:
        return {}
    step = max(1, len(cells) // 12)
    chosen = cells[::step][:12]
    return {cell: index for index, cell in enumerate(chosen)}


def _lit_set(cells: list[tuple[int, int]], frac: float) -> set[tuple[int, int]]:
    if frac >= 1:
        return set(cells)
    ordered = sorted(cells, key=lambda point: (point[0] * 13 + point[1] * 7) % 97)
    count = int(len(ordered) * frac)
    if frac > 0 and count == 0 and ordered:
        count = 1
    return set(ordered[:count])


def _stray_set(width: int, blocked: set[tuple[int, int]], frac: float) -> set[tuple[int, int]]:
    if frac <= 0 or frac >= 1 or width <= 0:
        return set()
    found: set[tuple[int, int]] = set()
    n = 0
    while len(found) < 12 and n < 80:
        point = ((n * 17 + 5) % width, (n * 5 + 2) % 10)
        n += 1
        if point in blocked:
            continue
        found.add(point)
    return found


def _teal_sgr(*, bold: bool = False, dim: bool = False, invert: bool = False) -> str:
    r, g, b = _TEAL_RGB
    bits: list[str] = []
    if invert:
        bits.extend(("1", "7"))
    elif bold:
        bits.append("1")
    elif dim:
        bits.append("2")
    bits.append(f"38;2;{r};{g};{b}")
    return f"\x1b[{';'.join(bits)}m"


def _idle_particles(width: int, blocked: set[tuple[int, int]], phase: int) -> set[tuple[int, int]]:
    """Landing-style stray cells: soft teal dots that drift after the build-in."""
    if width <= 0:
        return set()
    found: set[tuple[int, int]] = set()
    n = 0
    while n < 200 and len(found) < 32:
        point = ((n * 17 + 5 + phase * 3) % width, (n * 5 + 2 + phase) % 10)
        n += 1
        if point in blocked:
            continue
        if (n + phase) % 3 == 0:
            continue
        found.add(point)
    return found


def _cell_sgr(
    x: int,
    y: int,
    phase: int,
    glints: dict[tuple[int, int], int],
    hot_ok: bool,
    letter_index: int = 0,
) -> str:
    _ = letter_index
    gi = glints.get((x, y))
    if hot_ok and gi is not None and (gi + phase) % 8 == 0:
        return _teal_sgr(invert=True)
    if (x * 3 + y * 5) % 4 == 0:
        return _teal_sgr(dim=True)
    if (x * 3 + y * 5) % 4 == 3:
        return _teal_sgr(bold=True)
    return _teal_sgr()


def render_wordmark_lines(
    word: str = "DIGIVOICE",
    *,
    cols: int = 100,
    phase: int = 0,
    frac: float = 1.0,
    ansi: bool = False,
) -> list[str]:
    """Five half-block rows. `frac` reveals cells for the build-in; `phase` glints."""
    letters = word.upper()
    gap = _letter_gap(cols, max(1, len(letters)))
    grid = _pixel_grid(letters, gap)
    if not grid or not grid[0]:
        return []
    cells = _filled_cells(grid)
    lit = _lit_set(cells, frac)
    glints = _glint_index(cells)
    strays = _stray_set(len(grid[0]), set(cells), frac)
    idle = _idle_particles(len(grid[0]), set(cells), phase) if frac >= 1 else set()
    hot_ok = ansi and frac >= 1
    lines: list[str] = []
    width = len(grid[0])
    stride = 7 + gap if gap else 7
    n_letters = max(1, len(letters))
    for y in range(0, 10, 2):
        parts: list[str] = []
        dirty = False
        for x in range(width):
            top_on = (x, y) in lit or (x, y) in strays
            bot_on = (x, y + 1) in lit or (x, y + 1) in strays
            if not top_on and not bot_on:
                particle = (x, y) in idle or (x, y + 1) in idle
                if particle:
                    if ansi:
                        parts.append(_teal_sgr(dim=True))
                        dirty = True
                    parts.append("·")
                    continue
                if dirty and ansi:
                    parts.append(_ANSI_RESET)
                    dirty = False
                parts.append(" ")
                continue
            if top_on and bot_on:
                ch = "█"
                sx, sy = x, y
            elif top_on:
                ch = "▀"
                sx, sy = x, y
            else:
                ch = "▄"
                sx, sy = x, y + 1
            if ansi:
                letter_index = min(sx // stride, n_letters - 1) if stride else 0
                stray_only = (sx, sy) in strays and (sx, sy) not in lit
                if stray_only:
                    sgr = "\x1b[2m"
                else:
                    sgr = _cell_sgr(sx, sy, phase, glints, hot_ok, letter_index)
                if sgr:
                    parts.append(sgr)
                    dirty = True
                elif dirty:
                    parts.append(_ANSI_RESET)
                    dirty = False
            parts.append(ch)
        if dirty and ansi:
            parts.append(_ANSI_RESET)
        lines.append("".join(parts))
    return lines


def pixel_wordmark(word: str = "DIGIVOICE", fill: str = "█", empty: str = " ") -> str:
    """Render WORD in the PixelWordmark block language (10 text rows)."""
    rows: list[str] = []
    word = word.upper()
    for y in range(10):
        parts: list[str] = []
        for ch in word:
            glyph = _PIXEL_GLYPHS.get(ch)
            if glyph is None:
                parts.append(empty * 7)
            else:
                parts.append("".join(fill if c == "#" else empty for c in glyph[y]))
        rows.append(("  ".join(parts)).rstrip())
    return "\n".join(rows)


def tui_header_lines(subtitle: str | None = None) -> list[str]:
    """Half-block wordmark + subtitle. Frames compose their own centered panel."""
    return [
        *render_wordmark_lines("DIGIVOICE", cols=100, ansi=False),
        "",
        subtitle or _DEFAULT_SUBTITLE,
    ]


def pixel_wordmark_cells(word: str = "DIGIVOICE") -> list[tuple[int, int]]:
    """Filled (x, y) cells of WORD in glyph order. Used for the build-in."""
    cells: list[tuple[int, int]] = []
    x = 0
    for ch in word.upper():
        glyph = _PIXEL_GLYPHS.get(ch)
        if glyph is not None:
            for y in range(10):
                for c, mark in enumerate(glyph[y]):
                    if mark == "#":
                        cells.append((x + c, y))
        x += 9
    return cells


def pixel_build_frame(word: str = "DIGIVOICE", frac: float = 1.0) -> str:
    """Wordmark with a deterministic fraction of cells lit (intro build-in)."""
    return "\n".join(render_wordmark_lines(word, cols=100, frac=frac, ansi=False))


def _option_parts(option: str) -> tuple[str, str]:
    if " (" in option and option.endswith(")"):
        label, hint = option.split(" (", 1)
        return label, hint[:-1]
    return option, ""


def _health_symbol(value: str) -> str:
    return "■" if value.strip().lower().startswith("ok") else "□"


def _context_pairs(context: Sequence[str] | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in context or []:
        stripped = line.strip()
        if stripped and stripped[0] in _STATUS_SYMBOLS:
            pairs.append((stripped[0], stripped[1:].strip()))
            continue
        if line.startswith("models:") and " — banner " in line:
            models, banner = line.split(" — banner ", 1)
            pairs.append(("▦", models.split(":", 1)[1].strip()))
            pairs.append(("▥", banner.strip()))
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key == "models":
                pairs.append(("▦", val))
            elif key == "banner":
                pairs.append(("▥", val))
            elif key == "health":
                pairs.append((_health_symbol(val), val))
            elif key == "control":
                pairs.append(("▤", val))
            elif key:
                pairs.append(("□", val))
            elif val:
                pairs.append(("", val))
        elif line.strip():
            pairs.append(("", line.strip()))
    return pairs


def _mark(index: int, selected: int, checked: set[int] | None) -> str:
    if checked is not None:
        return "■ " if index in checked else "□ "
    return "■   " if index == selected else "□   "


def _emit_items(
    lines: list[str],
    options: Sequence[str],
    start: int,
    end: int,
    selected: int,
    checked: set[int] | None,
    label_w: int,
    panel_w: int,
    density: str,
    ansi: bool,
) -> None:
    for index in range(start, end):
        label, hint = _option_parts(options[index])
        if len(label) > label_w:
            label = label[: max(1, label_w - 1)] + "…"
        body = f"  {_mark(index, selected, checked)}{label.ljust(label_w)}"
        if hint:
            body += f"  {hint}"
        style = "bar" if index == selected else "item"
        lines.append(_paint(_fit("│" + body, panel_w), style, ansi))
        if density == "roomy" and index + 1 < end:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))


def _panel_lines(
    *,
    title: str,
    options: Sequence[str],
    selected: int,
    checked: set[int] | None,
    subtitle: str | None,
    context: Sequence[str] | None,
    groups: Sequence[Group] | None,
    hero: bool,
    panel_w: int,
    density: str,
    hint: str | None,
    ansi: bool,
) -> list[str]:
    lines: list[str] = []
    count = len(options)
    selected = selected % count if count else 0
    labels = [_option_parts(option)[0] for option in options] or [""]
    natural = max(len(label) for label in labels)
    label_w = min(natural, max(8, panel_w - 20))
    roomy = density == "roomy"
    spaced = density != "compact"

    lines.append(_paint(_fit(f"┌  {_KICKER}", panel_w), "rule", ansi))
    if subtitle and spaced:
        lines.append(_paint(_fit(f"│  {subtitle}", panel_w), "kv", ansi))

    pairs = _context_pairs(context) if hero else []
    if pairs:
        if spaced:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))
        lines.append(_paint(_fit("■  STATUS", panel_w), "step-off", ansi))
        for symbol, val in pairs:
            lead = symbol if symbol in _STATUS_SYMBOLS else "□"
            if lead:
                lines.append(_paint(_fit(f"│  {lead}  {val}", panel_w), "kv", ansi))
            else:
                lines.append(_paint(_fit(f"│  {val}", panel_w), "kv", ansi))

    usable = [group for group in groups or [] if 0 <= group[1] < group[2] <= count]
    if usable:
        if spaced:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))
        covered: set[int] = set()
        for name, start, end in usable:
            active = start <= selected < end
            symbol = "■" if active else "□"
            style = "step-on" if active else "step-off"
            lines.append(_paint(_fit(f"{symbol}  {name.upper()}", panel_w), style, ansi))
            _emit_items(
                lines, options, start, end, selected, checked, label_w, panel_w, density, ansi
            )
            covered.update(range(start, end))
            if spaced:
                lines.append(_paint(_fit("│", panel_w), "rail", ansi))
        for index in range(count):
            if index in covered:
                continue
            _emit_items(
                lines, options, index, index + 1, selected, checked, label_w, panel_w, density, ansi
            )
    else:
        if spaced and lines:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))
        lines.append(_paint(_fit(f"■  {title}", panel_w), "step-on", ansi))
        if roomy:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))
        if count:
            _emit_items(
                lines, options, 0, count, selected, checked, label_w, panel_w, density, ansi
            )
        if spaced:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))

    current = _option_parts(options[selected])[0] if count else title
    footer_hint = hint or TUI_FOOTER_HINT
    full = f"└  {current}  ·  {footer_hint}"
    short = f"└  {footer_hint}"
    footer = full if len(full) <= panel_w else short
    lines.append(_paint(_fit(footer, panel_w), "rule", ansi))
    return lines


def _pad_line(line: str, cols: int, anchor: int, ansi: bool) -> str:
    left = (cols - anchor) // 2 if 0 < anchor < cols else 0
    eol = _ANSI_CLEAR_EOL if ansi else ""
    if line == "" and left == 0:
        return eol
    return (" " * left) + line + eol


def _compose(
    word_lines: Sequence[str],
    panel_lines: Sequence[str],
    cols: int,
    rows: int,
    panel_w: int,
    *,
    clear: bool,
    redraw: bool,
    ansi: bool,
    screen: bool | None = None,
) -> str:
    # `ansi` = SGR color; `screen` = clear/home/eol. Default screen to ansi for
    # older call sites; choose/play_intro pass screen independently of NO_COLOR.
    screen_ok = ansi if screen is None else screen
    placed: list[str] = []
    if word_lines:
        anchor = _visible_len(word_lines[0])
        placed.extend(_pad_line(line, cols, anchor, screen_ok) for line in word_lines)
    placed.extend(_pad_line(line, cols, panel_w, screen_ok) for line in panel_lines)
    top = (rows - len(placed)) // 2 if len(placed) < rows else 0
    if clear and screen_ok:
        prefix = _ANSI_CLEAR_HOME
    elif redraw and screen_ok:
        prefix = _ANSI_HOME
    else:
        prefix = ""
    suffix = _ANSI_CLEAR_DOWN if screen_ok and (clear or redraw) else ""
    # Explicit CRLF: menu loops hold raw input; if OPOST were off, bare LF would
    # staircase. Harmless under cooked ONLCR (extra CR stays on column 0).
    nl = "\r\n"
    gap = nl * top
    return prefix + gap + nl.join(placed) + nl + suffix


def render_screen(
    title: str,
    options: Sequence[str],
    selected: int,
    *,
    hint: str | None = None,
    checked: set[int] | None = None,
    subtitle: str | None = None,
    context: Sequence[str] | None = None,
    hero: bool = False,
    phase: int = 0,
    groups: Sequence[Group] | None = None,
    cols: int | None = None,
    rows: int | None = None,
    use_ansi: bool = False,
    use_screen: bool | None = None,
    clear: bool = False,
    redraw: bool = False,
) -> str:
    """One centered frame. `hero` adds the DIGIVOICE wordmark above the step rail."""
    term_cols, term_rows = _term_size()
    cols = term_cols if cols is None else cols
    rows = term_rows if rows is None else rows
    panel_w = max(36, min(64, cols - 4))
    if hero and not subtitle:
        subtitle = "local speech control"
    word_lines = (
        render_wordmark_lines("DIGIVOICE", cols=cols, phase=phase, ansi=use_ansi) if hero else []
    )
    chosen: list[str] = []
    chosen_panel: list[str] = []
    for density in ("roomy", "comfy", "compact"):
        panel = _panel_lines(
            title=title,
            options=options,
            selected=selected,
            checked=checked,
            subtitle=subtitle,
            context=context,
            groups=groups,
            hero=hero,
            panel_w=panel_w,
            density=density,
            hint=hint,
            ansi=use_ansi,
        )
        block = [*word_lines, ""] if hero and density != "compact" else list(word_lines)
        if hero and density == "compact":
            block = list(word_lines)
        block.extend(panel)
        chosen = block
        chosen_panel = panel
        if len(block) <= rows or density == "compact":
            break
    word_n = len(chosen) - len(chosen_panel)
    return _compose(
        chosen[:word_n],
        chosen[word_n:],
        cols,
        rows,
        panel_w,
        clear=clear,
        redraw=redraw,
        ansi=use_ansi,
        screen=use_screen,
    )


def _arrow_name(code: str) -> str:
    return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(code, "esc")


def _read_byte(fd: int, wait: float) -> str | None:
    """One raw byte from ``fd``, or None if nothing arrives within ``wait``."""
    if not select.select([fd], [], [], wait)[0]:
        return None
    data = os.read(fd, 1)
    return data.decode("latin-1") if data else None


def _read_key_on_fd(fd: int, timeout: float | None = None) -> str | None:
    """Read one key from an fd already in raw mode. See :func:`_read_key`."""
    if timeout is not None and not select.select([fd], [], [], timeout)[0]:
        return None
    first_b = os.read(fd, 1)
    if not first_b:
        return None
    first = first_b.decode("latin-1")
    if first == "\x1b":
        # Bare Esc and arrows share the first byte. Only wait briefly.
        second = _read_byte(fd, 0.04)
        if second is None:
            return "esc"
        if second == "[":
            # CSI cursor: [A or [1;3A — final byte is 0x40–0x7E.
            body: list[str] = []
            while True:
                ch = _read_byte(fd, 0.04)
                if ch is None:
                    return "esc"
                body.append(ch)
                if "@" <= ch <= "~":
                    break
                if len(body) > 8:
                    return "esc"
            return _arrow_name(body[-1])
        if second == "O":
            # SS3 application cursor keys: OA/OB/OC/OD.
            third = _read_byte(fd, 0.04)
            return "esc" if third is None else _arrow_name(third)
        return "esc"
    if first in {"\r", "\n"}:
        return "enter"
    if first == "\x03":
        raise KeyboardInterrupt
    return first


def _read_key(stdin: TextIO, timeout: float | None = None) -> str | None:
    """Read one key. Arrow sequences become names. `timeout` yields None on idle.

    Uses ``os.read`` on the fd — never ``stdin.read``. TextIO buffering plus
    ``select`` on the fd splits CSI tails (``\\x1b[A`` → esc, then ``[``, ``A``),
    and home treats esc as quit. Also accepts SS3 application-cursor ``\\x1bOA``.

    One-shot callers enter/leave raw here. Menu loops hold raw *input* for the
    whole session via :func:`_set_menu_raw` (OPOST kept on) so cooked restore
    cannot eat a queued CSI and paints still get NL→CRLF.
    """
    fd = stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return _read_key_on_fd(fd, timeout)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _cursor(stdout: TextIO, show: bool) -> None:
    if not _use_screen() or not _is_tty(stdout):
        return
    try:
        stdout.write(_ANSI_SHOW if show else _ANSI_HIDE)
        stdout.flush()
    except (OSError, ValueError):
        pass


def choose(
    title: str,
    options: list[str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    hint: str | None = None,
    subtitle: str | None = None,
    context: Sequence[str] | None = None,
    *,
    hero: bool = False,
    pulse: bool = False,
    groups: Sequence[Group] | None = None,
) -> int | None:
    """Pick an option index. Arrow/Enter on a TTY, numbered prompt otherwise.

    TTY mode centers a step-rail frame and redraws on every key. Space confirms
    like Enter; Esc/q goes back. `hero` paints the DIGIVOICE wordmark and, when
    `pulse` is set, lets a few cells glint while idle. Returns None on back.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if _is_tty(stdin):
        if not options:
            return None
        selected = 0
        color = _use_ansi()
        screen = _use_screen()
        # Pulse needs timed reads; screen (not color) is enough to redraw.
        live = pulse and screen and not _reduce_motion()
        phase = 0
        first = True
        fd = stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            _set_menu_raw(fd)
            _cursor(stdout, False)
            while True:
                stdout.write(
                    render_screen(
                        title,
                        options,
                        selected,
                        hint=hint,
                        subtitle=subtitle,
                        context=context,
                        hero=hero,
                        phase=phase,
                        groups=groups,
                        use_ansi=color,
                        use_screen=screen,
                        clear=first,
                        redraw=not first,
                    )
                )
                stdout.flush()
                first = False
                key = _read_key_on_fd(fd, 0.16 if live else None)
                if key is None:
                    phase = (phase + 1) % 8
                    continue
                if key == "up" or key in {"k", "K"}:
                    selected = (selected - 1) % len(options)
                elif key == "down" or key in {"j", "J"}:
                    selected = (selected + 1) % len(options)
                elif key in {"enter", " ", "right"}:
                    return selected
                elif key in {"esc", "q", "Q", "left"}:
                    return None
        except (OSError, ValueError):
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            _cursor(stdout, True)
    stdout.write(f"\n{title}\n")
    for i, option in enumerate(options, start=1):
        stdout.write(f"  {i}) {option}\n")
    stdout.write("  (number, or blank to go back)\n")
    stdout.flush()
    try:
        raw = stdin.readline()
    except (OSError, ValueError):
        return None
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        index = int(raw) - 1
    except ValueError:
        return None
    return index if 0 <= index < len(options) else None


def choose_many(
    title: str,
    options: list[str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    initial: set[int] | None = None,
    subtitle: str | None = None,
) -> list[int] | None:
    """Multi-select: Space toggles, Enter confirms, Esc/q cancels.

    TTY mode uses the same centered rail as :func:`choose`. Non-TTY falls back
    to a comma-separated numbered prompt so agents/pipes never hang.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if _is_tty(stdin):
        if not options:
            return None
        selected = 0
        checked: set[int] = set(initial or set())
        color = _use_ansi()
        screen = _use_screen()
        hint = "↑↓ move · space toggle · enter confirm · esc back · q quit"
        first = True
        fd = stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            _set_menu_raw(fd)
            _cursor(stdout, False)
            while True:
                stdout.write(
                    render_screen(
                        title,
                        options,
                        selected,
                        hint=hint,
                        checked=checked,
                        subtitle=subtitle,
                        use_ansi=color,
                        use_screen=screen,
                        clear=first,
                        redraw=not first,
                    )
                )
                stdout.flush()
                first = False
                key = _read_key_on_fd(fd)
                if key is None:
                    return None
                if key == "up" or key in {"k", "K"}:
                    selected = (selected - 1) % len(options)
                elif key == "down" or key in {"j", "J"}:
                    selected = (selected + 1) % len(options)
                elif key == " ":
                    if selected in checked:
                        checked.discard(selected)
                    else:
                        checked.add(selected)
                    selected = (selected + 1) % len(options)
                elif key == "enter":
                    return sorted(checked)
                elif key in {"esc", "q", "Q"}:
                    return None
        except (OSError, ValueError):
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            _cursor(stdout, True)
    stdout.write(f"\n{title} (multi: comma-separated numbers, blank cancels)\n")
    for i, option in enumerate(options, start=1):
        stdout.write(f"  {i}) {option}\n")
    stdout.flush()
    try:
        raw = stdin.readline()
    except (OSError, ValueError):
        return None
    if not raw or not raw.strip():
        return None
    picked: list[int] = []
    for part in raw.strip().split(","):
        try:
            index = int(part.strip()) - 1
        except ValueError:
            return None
        if 0 <= index < len(options) and index not in picked:
            picked.append(index)
    return sorted(picked)


def _pause(
    stdin: TextIO | None = None, stdout: TextIO | None = None, prompt: str = "Enter to go back"
) -> None:
    """Wait for one key on a TTY, one line otherwise. EOF returns immediately."""
    stdout = stdout or sys.stdout
    stdin = stdin or sys.stdin
    if _is_tty(stdin):
        try:
            _read_key(stdin)
        except (OSError, ValueError):
            pass
        finally:
            _cursor(stdout, True)
        return
    stdout.write(f"  {prompt}> ")
    stdout.flush()
    try:
        stdin.readline()
    except (OSError, ValueError):
        pass


def _write_info_frame(
    stdout: TextIO,
    title: str,
    body: list[str],
    footer: str = "Enter to go back",
    subtitle: str | None = None,
) -> None:
    """Centered read-only panel. Long reports top-align and may scroll."""
    _ = subtitle
    cols, rows = _term_size()
    tty_out = _is_tty(stdout)
    ansi = _use_ansi() and tty_out
    screen = _use_screen() and tty_out
    longest = max((len(line) for line in body), default=20)
    panel_w = max(36, min(cols - 2, max(62, min(longest + 4, cols - 2))))
    lines = [
        _paint(_fit(f"┌  {_KICKER}", panel_w), "rule", ansi),
        _paint(_fit(f"■  {title}", panel_w), "step-on", ansi),
    ]
    for entry in body or ["(empty)"]:
        lines.append(_paint(_fit("│  " + entry.rstrip(), panel_w, truncate=False), "kv", ansi))
    lines.append(_paint(_fit(f"└  {footer} · esc back · q quit", panel_w), "rule", ansi))
    stdout.write(
        _compose([], lines, cols, rows, panel_w, clear=True, redraw=False, ansi=ansi, screen=screen)
    )
    _cursor(stdout, False)
    stdout.flush()


def _render_menu_frame(
    title: str,
    options: list[str],
    selected: int,
    hint: str | None = None,
    checked: set[int] | None = None,
    subtitle: str | None = None,
    context: Sequence[str] | None = None,
) -> str:
    """Compatibility wrapper: one centered frame with color when the TTY allows it."""
    return render_screen(
        title,
        options,
        selected,
        hint=hint,
        checked=checked,
        subtitle=subtitle,
        context=context,
        use_ansi=_use_ansi(),
        clear=True,
    )


def play_intro(
    stdout: TextIO,
    subtitle: str | None = None,
    steps: tuple[float, ...] = (0.22, 0.48, 0.72, 0.9, 1.0),
    delay: float = 0.045,
) -> None:
    """Brief centered pixel build-in before the home menu. Skips on error."""
    if _reduce_motion():
        return
    cols, rows = _term_size()
    ansi = _use_ansi()
    screen = _use_screen()
    panel_w = max(36, min(64, cols - 4))
    tag = subtitle or "local speech control"
    try:
        for index, frac in enumerate(steps):
            word = render_wordmark_lines("DIGIVOICE", cols=cols, frac=frac, ansi=ansi)
            panel = [
                _paint(_fit(f"┌  {_KICKER}", panel_w), "rule", ansi),
                _paint(_fit(f"│  {tag}", panel_w), "kv", ansi),
                _paint(_fit("└", panel_w), "rule", ansi),
            ]
            stdout.write(
                _compose(
                    word,
                    panel,
                    cols,
                    rows,
                    panel_w,
                    clear=index == 0,
                    redraw=index != 0,
                    ansi=ansi,
                    screen=screen,
                )
            )
            stdout.flush()
            time.sleep(delay)
    except (OSError, ValueError):
        pass


__all__ = [
    "TUI_FOOTER_HINT",
    "_ANSI_CLEAR_EOL",
    "_ANSI_CLEAR_HOME",
    "_ANSI_SHOW",
    "_DEFAULT_SUBTITLE",
    "_is_tty",
    "_pause",
    "_read_key",
    "_render_menu_frame",
    "_use_ansi",
    "_set_menu_raw",
    "_use_screen",
    "_write_info_frame",
    "choose",
    "choose_many",
    "fullscreen_enter",
    "fullscreen_leave",
    "pixel_build_frame",
    "pixel_wordmark",
    "pixel_wordmark_cells",
    "play_intro",
    "render_screen",
    "render_wordmark_lines",
    "tui_header_lines",
]
