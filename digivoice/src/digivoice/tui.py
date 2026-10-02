"""Shared stdlib TUI primitives: fullscreen frames, pixel wordmark, menus.

Home (`home.py`) and setup (`setup.py`) draw from here. A TTY takes the
viewport: alternate screen, one repaint per key. The home hero is the landing pixel lockup: five half-block rows of DIGIVOICE.
Each cell is an xterm color-cube gray (truecolor when the terminal asks for
it), the wordmark builds in place, then a few cells glint. Menus use a step rail.
The selected row is a bold ``[*]``; other rows are ``[ ]``.

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

from digivoice.pixel_hero import PIXEL_GLYPHS, PixelCell, word_cells

# TTY contract:
# - Full viewport: alternate screen while a shell is open, CSI clear + home
#   on the first paint, cursor-home redraws after that. Never scroll-append.
# - Screen control (alt / clear / home / hide-cursor) follows the TTY + TERM,
#   not color. `NO_COLOR` only skips SGR — otherwise frames append and stack.
# - Menu loops hold raw *input* so CSI arrows stay intact, but keep OPOST so
#   NL→CRLF still runs. Full setraw clears OPOST; frames joined with bare LF
#   then staircase (scattered labels / broken wordmark) on Terminal.app.
# - Menu color is bold/dim on the terminal's own foreground. The wordmark uses
#   the xterm 6×6×6 cube (or truecolor when COLORTERM says so). The gray ramp
#   232–255 and bold/dim both collapse to one white in Terminal.app.
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

# SGR mouse cell, 0-based, or None when the terminal is not reporting motion.
_pointer: tuple[int, int] | None = None

_STATUS_SYMBOLS = frozenset({"▦", "▥", "■", "□", "▤"})

_DEFAULT_SUBTITLE = "digivoice setup · local speech config"
_KICKER = "digivoice"

# Nested home → setup stays on one alternate screen.
_fullscreen_depth = 0

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


def wrap_text(text: str, width: int) -> list[str]:
    """Word-wrap `text` to `width` columns. Long tokens are sliced."""
    width = max(8, width)
    stripped = text.strip()
    if not stripped:
        return [""]
    words = stripped.split()
    lines: list[str] = []
    current = ""
    for word in words:
        pieces = [word]
        if len(word) > width:
            pieces = [word[i : i + width] for i in range(0, len(word), width)]
        for piece in pieces:
            if not current:
                current = piece
                continue
            trial = f"{current} {piece}"
            if len(trial) <= width:
                current = trial
                continue
            lines.append(current)
            current = piece
    if current:
        lines.append(current)
    return lines or [""]


def _paint_selected(plain: str) -> str:
    """Bold the ``[*]`` mark. The rest of the row keeps the terminal foreground."""
    mark_at = plain.find("[*]")
    if mark_at < 0:
        return f"\x1b[1m{plain}{_ANSI_RESET}"
    head = plain[:mark_at]
    mark = plain[mark_at : mark_at + 3]
    tail = plain[mark_at + 3 :]
    if head[:1] in {"│", "|"}:
        head_s = f"\x1b[2m{head[:1]}{_ANSI_RESET}{head[1:]}"
    else:
        head_s = head
    return f"{head_s}\x1b[1m{mark}{_ANSI_RESET}{tail}"


def _paint(plain: str, style: str, ansi: bool) -> str:
    """Theme-safe SGR. Selected mark is bold; dim chrome; body uses default fg."""
    if not ansi or not plain:
        return plain
    if style == "bar":
        return _paint_selected(plain)
    if style in {"item", "kv"} and plain[:1] in {"│", "|"}:
        return f"\x1b[2m{plain[:1]}{_ANSI_RESET}{plain[1:]}"
    if style == "step-on":
        return f"\x1b[1m{plain}{_ANSI_RESET}"
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
        glyph = PIXEL_GLYPHS.get(ch)
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


# Landing pixel-build runs out by ~1.1s; strays finish a little later.
_BUILD_MS = 1400
# Blank rows between the wordmark and the menu on the home frame.
_HERO_GAP = 2
# Set by play_intro so the home frame continues that same landing clock.
_hero_origin: float | None = None


def _reveal_alpha(
    delay_ms: int, duration_ms: int, t_ms: int, final: float, a: float, b: float, c: float
) -> float:
    """Stepped opacity from the landing ``pixel-build`` keyframes."""
    if t_ms < delay_ms:
        return 0.0
    span = max(1, duration_ms)
    if t_ms >= delay_ms + span:
        return final
    progress = (t_ms - delay_ms) / span
    if progress < 0.33:
        return a
    if progress < 0.66:
        return b
    return c


# Landing opacities → xterm cube grays (k=1..5). These indexes are the ones
# Terminal.app actually draws apart. The 232–255 ramp often comes out white.
# RGB matches the cube so truecolor terminals show the same five shades.
_SHADES: tuple[tuple[float, int, int], ...] = (
    (0.36, 95, 59),
    (0.50, 135, 102),
    (0.66, 175, 145),
    (0.82, 215, 188),
    (1.00, 255, 231),
)


def _truecolor() -> bool:
    return os.environ.get("COLORTERM", "").lower() in {"truecolor", "24bit"}


def _alpha_sgr(alpha: float, *, truecolor: bool = False) -> str:
    """One landing opacity as a cube gray, or the matching RGB when asked."""
    if alpha <= 0:
        return ""
    _step, rgb, cube = min(_SHADES, key=lambda item: abs(item[0] - alpha))
    if truecolor:
        return f"\x1b[38;2;{rgb};{rgb};{rgb}m"
    return f"\x1b[38;5;{cube}m"


def _landing_flash(cell: PixelCell, t_ms: int) -> bool:
    """The site's ``pixel-glint``: a few cells brighten for a short slice of their period."""
    if not cell.glint or cell.glint_period_ms <= 0 or t_ms < cell.glint_delay_ms:
        return False
    elapsed = (t_ms - cell.glint_delay_ms) % cell.glint_period_ms
    return elapsed < max(80, int(0.05 * cell.glint_period_ms))


def _timed_pixels(
    word: str, cols: int, t_ms: int
) -> tuple[dict[tuple[int, int], float], set[tuple[int, int]]]:
    """Letter alphas and the strays that are flickering at ``t_ms``."""
    gap = _letter_gap(cols, max(1, len(word)))
    letters, stray = word_cells(word, gap)
    alphas: dict[tuple[int, int], float] = {}
    for cell in letters:
        alpha = _reveal_alpha(cell.delay_ms, cell.duration_ms, t_ms, cell.f, cell.a, cell.b, cell.c)
        if alpha > 0:
            alphas[(cell.x, cell.y)] = alpha
    flickering = {
        (cell.x, cell.y)
        for cell in stray
        if cell.delay_ms <= t_ms < cell.delay_ms + max(1, cell.duration_ms)
    }
    return alphas, flickering


def render_wordmark_lines(
    word: str = "DIGIVOICE",
    *,
    cols: int = 100,
    phase: int = 0,
    frac: float = 1.0,
    ansi: bool = False,
    t_ms: int | None = None,
    truecolor: bool = False,
) -> list[str]:
    """Five half-block rows. `frac` reveals cells; `t_ms` plays the landing build."""
    letters = word.upper()
    gap = _letter_gap(cols, max(1, len(letters)))
    grid = _pixel_grid(letters, gap)
    if not grid or not grid[0]:
        return []
    cells = _filled_cells(grid)
    building = t_ms is not None and t_ms < _BUILD_MS
    alphas: dict[tuple[int, int], float] = {}
    if building and t_ms is not None:
        alphas, strays = _timed_pixels(letters, cols, t_ms)
        lit = set(alphas)
    else:
        lit = _lit_set(cells, frac)
        strays = _stray_set(len(grid[0]), set(cells), frac)
    settled: dict[tuple[int, int], PixelCell] = {}
    if not building:
        gap_cells, _unused = word_cells(letters, gap)
        settled = {(cell.x, cell.y): cell for cell in gap_cells}
    clock = phase * 160 if t_ms is None else t_ms
    lines: list[str] = []
    width = len(grid[0])
    for y in range(0, 10, 2):
        parts: list[str] = []
        dirty = False
        for x in range(width):
            top_on = (x, y) in lit or (x, y) in strays
            bot_on = (x, y + 1) in lit or (x, y + 1) in strays
            if not top_on and not bot_on:
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
                points: list[tuple[int, int]] = []
                if top_on:
                    points.append((x, y))
                if bot_on:
                    points.append((x, y + 1))
                cells_here = [settled[point] for point in points if point in settled]
                primary = settled.get((sx, sy))
                stray_only = bool(points) and all(
                    point in strays and point not in lit for point in points
                )
                if stray_only:
                    sgr = _alpha_sgr(0.36, truecolor=truecolor)
                elif building:
                    sgr = _alpha_sgr(alphas.get((sx, sy), 0.0), truecolor=truecolor)
                elif any(_landing_flash(cell, clock) for cell in cells_here):
                    sgr = _alpha_sgr(1.0, truecolor=truecolor)
                elif primary is not None:
                    sgr = _alpha_sgr(primary.f, truecolor=truecolor)
                else:
                    sgr = ""
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
            glyph = PIXEL_GLYPHS.get(ch)
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
        glyph = PIXEL_GLYPHS.get(ch)
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
    """``[*]`` when chosen, ``[ ]`` otherwise. Same width so labels stay aligned."""
    if checked is not None:
        on = index in checked
    else:
        on = index == selected
    return "[*] " if on else "[ ] "


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
    _ = label_w
    inner_w = max(12, panel_w - 1)
    for index in range(start, end):
        label, hint = _option_parts(options[index])
        mark = _mark(index, selected, checked)
        prefix = f"  {mark}"
        body_w = max(8, inner_w - len(prefix))
        label_lines = wrap_text(label, body_w)
        style = "bar" if index == selected else "item"
        first = prefix + label_lines[0]
        remainder_indent = " " * len(prefix)
        extra: list[str] = [remainder_indent + part for part in label_lines[1:]]
        if hint:
            if len(first) + 2 + len(hint) <= inner_w:
                first = f"{first}  {hint}"
            else:
                extra.extend(remainder_indent + part for part in wrap_text(hint, body_w))
        for row in [first, *extra]:
            lines.append(_paint(_fit("│" + row, panel_w), style, ansi))
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
    if density == "tight":
        groups = None
        subtitle = None
    roomy = density == "roomy"
    spaced = density not in {"compact", "tight"}

    lines.append(_paint(_fit(f"┌  {_KICKER}", panel_w), "rule", ansi))
    if subtitle and spaced:
        for row in wrap_text(subtitle, max(12, panel_w - 3)):
            lines.append(_paint(_fit(f"│  {row}", panel_w), "kv", ansi))

    pairs = _context_pairs(context) if hero else []
    if pairs:
        if spaced:
            lines.append(_paint(_fit("│", panel_w), "rail", ansi))
        lines.append(_paint(_fit("■  STATUS", panel_w), "step-off", ansi))
        for symbol, val in pairs:
            lead = symbol if symbol in _STATUS_SYMBOLS else "□"
            prefix = f"│  {lead}  " if lead else "│  "
            wrapped = wrap_text(val, max(8, panel_w - len(prefix)))
            for i, row in enumerate(wrapped):
                lead_out = prefix if i == 0 else "│     "
                lines.append(_paint(_fit(lead_out + row, panel_w), "kv", ansi))

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
    if len(footer) <= panel_w:
        lines.append(_paint(_fit(footer, panel_w), "rule", ansi))
        return lines
    wrapped = wrap_text(footer_hint, max(8, panel_w - 3))
    lines.append(_paint(_fit(f"└  {wrapped[0]}", panel_w), "rule", ansi))
    for row in wrapped[1:]:
        lines.append(_paint(_fit(f"   {row}", panel_w), "rule", ansi))
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
    fill: bool = False,
) -> str:
    # `ansi` = SGR color; `screen` = clear/home/eol. Default screen to ansi for
    # older call sites; choose/play_intro pass screen independently of NO_COLOR.
    screen_ok = ansi if screen is None else screen
    placed: list[str] = []
    if word_lines:
        anchor = cols if fill else _visible_len(word_lines[0])
        placed.extend(_pad_line(line, cols, anchor, screen_ok) for line in word_lines)
    placed.extend(_pad_line(line, cols, panel_w, screen_ok) for line in panel_lines)
    top = 0 if fill else ((rows - len(placed)) // 2 if len(placed) < rows else 0)
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
    t_ms: int | None = None,
    pointer: tuple[int, int] | None = None,
    truecolor: bool = False,
) -> str:
    """One centered frame. `hero` paints the half-block DIGIVOICE wordmark."""
    term_cols, term_rows = _term_size()
    cols = term_cols if cols is None else cols
    rows = term_rows if rows is None else rows
    panel_w = max(36, min(88, cols - 6))
    if hero and not subtitle:
        subtitle = "local speech control"
    elapsed = phase * 160 if t_ms is None else t_ms
    _ = pointer
    chosen_panel: list[str] = []
    for density in ("roomy", "comfy", "compact", "tight"):
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
        header_h = rows - len(panel)
        needed = 5 + _HERO_GAP + 1 if hero and density in {"roomy", "comfy"} else (5 if hero else 0)
        if header_h >= needed or density == "tight":
            chosen_panel = panel
            break
        chosen_panel = panel
    word_lines = (
        render_wordmark_lines(
            "DIGIVOICE",
            cols=cols,
            phase=max(0, elapsed // 160),
            ansi=use_ansi,
            t_ms=t_ms,
            truecolor=truecolor,
        )
        if hero
        else []
    )
    if word_lines:
        spare = rows - len(chosen_panel) - len(word_lines)
        gap_n = min(_HERO_GAP, max(0, spare))
        word_lines = [*word_lines, *([" "] * gap_n)]
    return _compose(
        word_lines,
        chosen_panel,
        cols,
        rows,
        panel_w,
        clear=clear,
        redraw=redraw,
        ansi=use_ansi,
        screen=use_screen,
        fill=False,
    )


def _arrow_name(code: str) -> str:
    return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(code, "esc")


def parse_sgr_mouse(body: str) -> tuple[int, int] | None:
    """Decode ``btn;x;y`` from CSI ``< ... M``. Returns 0-based (col, row)."""
    parts = body.split(";")
    if len(parts) != 3:
        return None
    try:
        _btn, x, y = (int(part) for part in parts)
    except ValueError:
        return None
    if x <= 0 or y <= 0:
        return None
    return (x - 1, y - 1)


def _note_pointer(cell: tuple[int, int] | None) -> None:
    global _pointer
    _pointer = cell


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
            peek = _read_byte(fd, 0.04)
            if peek is None:
                return "esc"
            if peek == "<":
                # SGR mouse: CSI < btn ; x ; y M/m. Never treat M as quit/esc.
                packed: list[str] = []
                while True:
                    ch = _read_byte(fd, 0.04)
                    if ch is None:
                        return "esc"
                    if ch in "Mm":
                        break
                    packed.append(ch)
                    if len(packed) > 16:
                        return "esc"
                cell = parse_sgr_mouse("".join(packed))
                if cell is not None:
                    _note_pointer(cell)
                    return "mouse"
                return "esc"
            # CSI cursor: [A or [1;3A — final byte is 0x40–0x7E.
            body: list[str] = [peek]
            if not ("@" <= peek <= "~"):
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

    TTY mode paints a step-rail frame and redraws on every key. Space confirms
    like Enter; Esc/q goes back. `hero` paints the DIGIVOICE pixel lockup.
    When `pulse` is set, the lockup builds on the landing clock and a few
    cells keep glinting. :func:`play_intro` arms that clock.
    Returns None on back.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if _is_tty(stdin):
        if not options:
            return None
        selected = 0
        color = _use_ansi()
        screen = _use_screen()
        color_true = _truecolor()
        # Pulse needs timed reads; screen (not color) is enough to redraw.
        live = pulse and screen and not _reduce_motion()
        phase = 0
        first = True
        fd = stdin.fileno()
        saved = termios.tcgetattr(fd)
        # Home arms the clock in play_intro so the build plays on this frame.
        # A hero opened on its own starts already settled.
        if hero and _hero_origin is not None:
            origin = _hero_origin
        elif hero:
            origin = time.monotonic() - _BUILD_MS / 1000
        else:
            origin = time.monotonic()
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
                        t_ms=int((time.monotonic() - origin) * 1000) if live else None,
                        truecolor=color_true,
                    )
                )
                stdout.flush()
                first = False
                # 80ms tracks the landing glint; a slower poll skips the flash.
                key = _read_key_on_fd(fd, 0.08 if live else None)
                if key is None or key == "mouse":
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
            _note_pointer(None)
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
    *,
    wait: bool = True,
) -> None:
    """Centered read-only panel. Long reports wrap; overflow scrolls with ↑↓."""
    cols, rows = _term_size()
    tty_out = _is_tty(stdout)
    ansi = _use_ansi() and tty_out
    screen = _use_screen() and tty_out
    inner_w = max(20, min(cols - 6, 88) - 3)
    wrapped: list[str] = []
    for entry in body or ["(empty)"]:
        wrapped.extend(wrap_text(entry.rstrip() or " ", inner_w))
    panel_w = max(36, min(cols - 2, max(62, min(inner_w + 4, cols - 2))))
    chrome = 3  # rule, title, footer
    window = max(4, rows - chrome - 2)
    offset = 0
    stdin = sys.stdin
    while True:
        view = wrapped[offset : offset + window]
        more = offset + window < len(wrapped)
        less = offset > 0
        footer_bits = [footer]
        if less or more:
            footer_bits.append("↑↓ scroll")
        footer_bits.append("esc back · q quit")
        lines = [
            _paint(_fit(f"┌  {_KICKER}", panel_w), "rule", ansi),
            _paint(_fit(f"■  {title}", panel_w), "step-on", ansi),
        ]
        if subtitle:
            for row in wrap_text(subtitle, inner_w):
                lines.append(_paint(_fit(f"│  {row}", panel_w), "kv", ansi))
        for entry in view or ["(empty)"]:
            lines.append(_paint(_fit("│  " + entry, panel_w), "kv", ansi))
        lines.append(_paint(_fit("└  " + " · ".join(footer_bits), panel_w), "rule", ansi))
        stdout.write(
            _compose(
                [], lines, cols, rows, panel_w, clear=True, redraw=False, ansi=ansi, screen=screen
            )
        )
        _cursor(stdout, False)
        stdout.flush()
        if not tty_out or not wait:
            return
        try:
            key = _read_key(stdin)
        except (OSError, ValueError):
            return
        if key in {"down", "j", "J", " "} and more:
            offset = min(len(wrapped) - window, offset + 1)
            continue
        if key in {"up", "k", "K"} and less:
            offset = max(0, offset - 1)
            continue
        return


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
    steps: tuple[float, ...] = (0.0, 0.22, 0.48, 0.74, 1.0),
    delay: float = 0.08,
) -> None:
    """Arm the landing clock. The home frame plays the build, then the glint.

    The wordmark stays put above the menu, the same way the site builds the
    hero in place. ``steps`` and ``delay`` remain so older callers still import.
    """
    global _hero_origin
    _ = (stdout, subtitle, steps, delay)
    if _reduce_motion():
        _hero_origin = time.monotonic() - _BUILD_MS / 1000
        return
    _hero_origin = time.monotonic()


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
    "parse_sgr_mouse",
    "pixel_build_frame",
    "pixel_wordmark",
    "pixel_wordmark_cells",
    "play_intro",
    "render_screen",
    "render_wordmark_lines",
    "tui_header_lines",
    "wrap_text",
]
