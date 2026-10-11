"""Shared stdlib TUI primitives: fullscreen frames, pixel wordmark, menus.

Home (`home.py`) and setup (`setup.py`) draw from here. A TTY takes the
viewport: alternate screen, one repaint per key. The home hero is the landing pixel lockup: five half-block rows of DIGIVOICE.
Each cell is an xterm color-cube gray (truecolor when the terminal asks for
it), the wordmark builds in place, then a few cells glint. Menus use a step rail.
The selected row is a bold ``[*]``; other rows are ``[ ]``. A settings
row paints the name in bold, the value in brackets, and the explanation
in a cube gray.

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
from collections.abc import Mapping, Sequence
from typing import TextIO

from pydantic import BaseModel, ConfigDict

from digivoice.pixel_hero import PIXEL_GLYPHS, PixelCell, word_cells

# TTY contract:
# - Full viewport: alternate screen while a shell is open, CSI clear + home
#   on the first paint, cursor-home redraws after that. Never scroll-append.
# - Screen control (alt / clear / home / hide-cursor) follows the TTY + TERM,
#   not color. `NO_COLOR` only skips SGR — otherwise frames append and stack.
# - Menu loops hold raw *input* so CSI arrows stay intact, but keep OPOST so
#   NL→CRLF still runs. Full setraw clears OPOST; frames joined with bare LF
#   then staircase (scattered labels / broken wordmark) on Terminal.app.
# - Menu color is bold/dim on the terminal's own foreground. Settings rows
#   put the value in brackets and the explanation in a cube gray (index 145),
#   because dim and the 232–255 ramp both collapse to white in Terminal.app.
#   The wordmark uses the xterm 6×6×6 cube (or truecolor when COLORTERM says so).
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

NAV_FOOTER = "↑↓ move · enter select · esc back · click"
TUI_FOOTER_HINT = NAV_FOOTER
# Click targets that are not menu rows. Negative so they never match an option.
HIT_BACK = -1
HIT_PREV = -2
HIT_NEXT = -3

Group = tuple[str, int, int]

# Screen row → option index for the last frame. Clicks use this.
_ROW_HITS: list[int | None] = []
_MOUSE_ON = "\x1b[?1000h\x1b[?1006h"
_MOUSE_OFF = "\x1b[?1000l\x1b[?1006l"


class MenuBlock(BaseModel):
    """One row, drawn the same way on every screen.

    The action is the line you read. Under it, in gray: the shortcut key,
    the slash path, then metadata (a value or a timestamp). Empty parts
    are skipped. No sentence explaining the shortcut.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    path: str = ""
    meta: str = ""
    shortcut: str = ""


def hit_at(row: int) -> int | None:
    """Option index for a 0-based screen row, or None on chrome."""
    if row < 0 or row >= len(_ROW_HITS):
        return None
    return _ROW_HITS[row]


def row_hits() -> list[int | None]:
    """Screen-row hit map from the last `render_screen`."""
    return _ROW_HITS


def match_shortcut(key: str, shortcuts: Mapping[str, int] | None) -> int | None:
    """Map a key to an option. ``copy`` is Command-C / Windows-C when the terminal sends it."""
    if not shortcuts:
        return None
    if key in shortcuts:
        return shortcuts[key]
    if key == "copy" and "c" in shortcuts:
        return shortcuts["c"]
    return None


def _kitty_key(payload: str) -> str:
    """CSI u: ``code;mods``. Super (Command / Windows) plus c is ``copy``."""
    head = payload.split(":", 1)[0]
    parts = head.split(";")
    try:
        code = int(parts[0])
        mods = int(parts[1]) if len(parts) > 1 else 1
    except ValueError:
        return "esc"
    if not 32 <= code < 127:
        return "esc"
    char = chr(code)
    if char in {"c", "C"} and (mods - 1) & 8:
        return "copy"
    return char


def _modify_other_key(payload: str) -> str:
    """xterm modifyOtherKeys: ``27;mod;code``. Meta/super plus c is ``copy``."""
    parts = payload.split(";")
    if len(parts) < 3:
        return "esc"
    try:
        mod = int(parts[1])
        code = int(parts[2])
    except ValueError:
        return "esc"
    if code in {99, 67} and mod & 8:
        return "copy"
    return "esc"


# Kitty / xterm modifier parameter is 1 + bitfield (shift 1, alt 2, ctrl 4, cmd 8).
_CHORD_MOD_BITS = (("ctrl", 4), ("shift", 1), ("alt", 2), ("cmd", 8))
_KITTY_PUSH = "\x1b[>1u"
_KITTY_POP = "\x1b[<u"
_MODIFY_PUSH = "\x1b[>4;2m"
_MODIFY_POP = "\x1b[>4;0m"


def _key_token(code: int) -> str | None:
    """Name a key for a chord. Letters stay lowercase."""
    if code == 32:
        return "space"
    if code == 9:
        return "tab"
    if code in {10, 13}:
        return "enter"
    if code == 27:
        return "esc"
    if code == 127:
        return "delete"
    if 33 <= code < 127:
        return chr(code).lower()
    return None


def chord_from_code(mods: int, code: int) -> str | None:
    """Turn a Kitty/xterm modifier number and code point into a binding.

    Shift alone on a letter is the typed character, so ``Right Option`` can
    still be entered by hand. ``ctrl``, ``alt``, or ``cmd`` make a chord
    (``ctrl+shift+space``).
    """
    if mods < 1:
        return None
    bits = mods - 1
    ctrl = bool(bits & 4)
    alt = bool(bits & 2)
    cmd = bool(bits & 8)
    shift = bool(bits & 1)
    if not ctrl and not alt and not cmd:
        if code == 32:
            return " "
        if 33 <= code < 127:
            char = chr(code)
            if shift and char.isalpha():
                return char.upper()
            return char
        if code in {10, 13}:
            return "enter"
        if code == 27:
            return "esc"
        if code == 9:
            return "tab"
        if code == 127:
            return "\x7f"
        return None
    key = _key_token(code)
    if key is None:
        return None
    prefix = [name for name, bit in _CHORD_MOD_BITS if bits & bit]
    return "+".join([*prefix, key])


def chord_from_kitty(payload: str) -> str | None:
    """CSI u payload ``code;mods`` (no trailing ``u``)."""
    head = payload.split(":", 1)[0]
    if head.endswith("u"):
        head = head[:-1]
    parts = head.split(";")
    try:
        code = int(parts[0])
        mods = int(parts[1]) if len(parts) > 1 else 1
    except ValueError:
        return None
    return chord_from_code(mods, code)


def chord_from_modify_other(payload: str) -> str | None:
    """xterm ``27;mod;code`` (optional trailing ``~``)."""
    body = payload[:-1] if payload.endswith("~") else payload
    parts = body.split(";")
    if len(parts) < 3:
        return None
    try:
        mods = int(parts[1])
        code = int(parts[2])
    except ValueError:
        return None
    return chord_from_code(mods, code)


def mouse_action(body: str, *, pressed: bool) -> str:
    """Left press is ``click``. Motion and other buttons stay ``mouse``."""
    parts = body.split(";")
    if len(parts) != 3:
        return "mouse"
    try:
        btn = int(parts[0])
    except ValueError:
        return "mouse"
    if not pressed or btn & 32:
        return "mouse"
    if btn & 3 == 0:
        return "click"
    return "mouse"


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


def _value_face(label: str) -> tuple[str, str]:
    """Split ``name  [value]`` into the name and the bracketed value."""
    if label.endswith("]") and " [" in label:
        name, rest = label.rsplit(" [", 1)
        name = name.rstrip()
        if name:
            return name, f"[{rest}"
    return label, ""


def _muted_sgr(*, truecolor: bool) -> str:
    """Explanation gray. Cube 145, the landing 0.66 step. Not dim, not the ramp."""
    return _alpha_sgr(0.66, truecolor=truecolor)


def _edge_spaces(text: str) -> tuple[str, str, str]:
    """Split leading spaces, the word, and trailing spaces."""
    gap = text[: len(text) - len(text.lstrip(" "))]
    rest = text[len(gap) :]
    name = rest.rstrip(" ")
    return gap, name, rest[len(name) :]


def _paint_detail_name(plain: str, *, ansi: bool) -> str:
    """Bold the name. Leave ``[value]`` in the terminal foreground."""
    if not ansi:
        return plain
    lead = ""
    body = plain
    if body[:1] in {"│", "|"}:
        lead = f"\x1b[2m{body[:1]}{_ANSI_RESET}"
        body = body[1:]
    mark_at = body.find("[*]")
    token = "[*]"
    if mark_at < 0:
        mark_at = body.find("[ ]")
        token = "[ ]"
    if mark_at < 0:
        return f"{lead}{body}"
    before = body[:mark_at]
    after = body[mark_at + 3 :]
    mark_s = f"\x1b[1m{token}{_ANSI_RESET}" if token == "[*]" else token
    if "  [" in after:
        name_part, value_tail = after.split("  [", 1)
        gap, name, pad = _edge_spaces(name_part)
        return f"{lead}{before}{mark_s}{gap}\x1b[1m{name}{_ANSI_RESET}{pad}  [{value_tail}"
    gap, name, pad = _edge_spaces(after)
    return f"{lead}{before}{mark_s}{gap}\x1b[1m{name}{_ANSI_RESET}{pad}"


def _paint_detail_explain(plain: str, *, ansi: bool, truecolor: bool) -> str:
    """One explanation line in cube gray."""
    if not ansi:
        return plain
    if plain[:1] in {"│", "|"}:
        lead = f"\x1b[2m{plain[:1]}{_ANSI_RESET}"
        body = plain[1:]
    else:
        lead, body = "", plain
    if not body.strip():
        return f"{lead}{body}"
    return f"{lead}{_muted_sgr(truecolor=truecolor)}{body}{_ANSI_RESET}"


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


def _push(lines: list[str], hits: list[int | None], line: str, hit: int | None = None) -> None:
    lines.append(line)
    hits.append(hit)


def _emit_blocks(
    lines: list[str],
    hits: list[int | None],
    blocks: Sequence[MenuBlock],
    start: int,
    end: int,
    selected: int,
    checked: set[int] | None,
    panel_w: int,
    density: str,
    ansi: bool,
    truecolor: bool,
) -> None:
    """Action, then gray shortcut, path, and metadata. Every line of a row is clickable."""
    inner_w = max(12, panel_w - 1)
    for index in range(start, end):
        block = blocks[index]
        mark = _mark(index, selected, checked)
        prefix = f"  {mark}"
        indent = " " * len(prefix)
        body_w = max(8, inner_w - len(prefix))
        action_lines = wrap_text(block.action, body_w) or [""]
        _push(
            lines,
            hits,
            _paint_detail_name(_fit("│" + prefix + action_lines[0], panel_w), ansi=ansi),
            index,
        )
        for extra in action_lines[1:]:
            _push(
                lines,
                hits,
                _paint_detail_name(_fit("│" + indent + extra, panel_w), ansi=ansi),
                index,
            )
        for gray in (block.shortcut, block.path, block.meta):
            if not gray:
                continue
            for part in wrap_text(gray, body_w):
                _push(
                    lines,
                    hits,
                    _paint_detail_explain(
                        _fit("│" + indent + part, panel_w),
                        ansi=ansi,
                        truecolor=truecolor,
                    ),
                    index,
                )
        if density == "roomy" and index + 1 < end:
            _push(lines, hits, _paint(_fit("│", panel_w), "rail", ansi), None)


def _emit_detail_items(
    lines: list[str],
    hits: list[int | None],
    options: Sequence[str],
    start: int,
    end: int,
    selected: int,
    checked: set[int] | None,
    panel_w: int,
    density: str,
    ansi: bool,
    truecolor: bool,
) -> None:
    """Name in bold, value in brackets, explanation on the next line in gray."""
    inner_w = max(12, panel_w - 1)
    faces: list[tuple[str, str]] = []
    for index in range(start, end):
        label, _hint = _option_parts(options[index])
        faces.append(_value_face(label))
    name_w = max((len(name) for name, value in faces if value), default=0)
    for offset, index in enumerate(range(start, end)):
        _label, hint = _option_parts(options[index])
        name, value = faces[offset]
        mark = _mark(index, selected, checked)
        prefix = f"  {mark}"
        body = f"{name.ljust(name_w)}  {value}" if value else name
        _push(
            lines,
            hits,
            _paint_detail_name(_fit("│" + prefix + body, panel_w), ansi=ansi),
            index,
        )
        if hint:
            indent = " " * len(prefix)
            width = max(8, inner_w - len(prefix))
            for part in wrap_text(hint, width):
                _push(
                    lines,
                    hits,
                    _paint_detail_explain(
                        _fit("│" + indent + part, panel_w),
                        ansi=ansi,
                        truecolor=truecolor,
                    ),
                    index,
                )
        if density == "roomy" and index + 1 < end:
            _push(lines, hits, _paint(_fit("│", panel_w), "rail", ansi), None)


def _emit_items(
    lines: list[str],
    hits: list[int | None],
    options: Sequence[str],
    start: int,
    end: int,
    selected: int,
    checked: set[int] | None,
    label_w: int,
    panel_w: int,
    density: str,
    ansi: bool,
    *,
    detail: bool = False,
    truecolor: bool = False,
    blocks: Sequence[MenuBlock] | None = None,
) -> None:
    if blocks is not None:
        _emit_blocks(
            lines,
            hits,
            blocks,
            start,
            end,
            selected,
            checked,
            panel_w,
            density,
            ansi,
            truecolor,
        )
        return
    if detail:
        _emit_detail_items(
            lines,
            hits,
            options,
            start,
            end,
            selected,
            checked,
            panel_w,
            density,
            ansi,
            truecolor,
        )
        return
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
            _push(lines, hits, _paint(_fit("│" + row, panel_w), style, ansi), index)
        if density == "roomy" and index + 1 < end:
            _push(lines, hits, _paint(_fit("│", panel_w), "rail", ansi), None)


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
    detail: bool = False,
    truecolor: bool = False,
    blocks: Sequence[MenuBlock] | None = None,
    lead: Sequence[str] | None = None,
    lead_meta: str | None = None,
    typed: str | None = None,
    paging: bool = False,
) -> tuple[list[str], list[int | None]]:
    lines: list[str] = []
    hits: list[int | None] = []
    count = len(blocks) if blocks is not None else len(options)
    selected = selected % count if count else 0
    if blocks is not None:
        labels = [block.action for block in blocks] or [""]
    else:
        labels = [_option_parts(option)[0] for option in options] or [""]
    natural = max(len(label) for label in labels)
    label_w = min(natural, max(8, panel_w - 20))
    if density == "tight":
        groups = None
        subtitle = None
    roomy = density == "roomy"
    spaced = density not in {"compact", "tight"}

    def add(line: str, hit: int | None = None) -> None:
        _push(lines, hits, line, hit)

    add(_paint(_fit(f"┌  {_KICKER}", panel_w), "rule", ansi))
    if subtitle and spaced:
        for row in wrap_text(subtitle, max(12, panel_w - 3)):
            add(_paint(_fit(f"│  {row}", panel_w), "kv", ansi))

    pairs = _context_pairs(context) if hero else []
    if pairs:
        if spaced:
            add(_paint(_fit("│", panel_w), "rail", ansi))
        add(_paint(_fit("■  STATUS", panel_w), "step-off", ansi))
        for symbol, val in pairs:
            lead_symbol = symbol if symbol in _STATUS_SYMBOLS else "□"
            prefix = f"│  {lead_symbol}  " if lead_symbol else "│  "
            wrapped = wrap_text(val, max(8, panel_w - len(prefix)))
            for i, row in enumerate(wrapped):
                lead_out = prefix if i == 0 else "│     "
                add(_paint(_fit(lead_out + row, panel_w), "kv", ansi))

    def emit(start: int, end: int) -> None:
        _emit_items(
            lines,
            hits,
            options,
            start,
            end,
            selected,
            checked,
            label_w,
            panel_w,
            density,
            ansi,
            detail=detail,
            truecolor=truecolor,
            blocks=blocks,
        )

    usable = [group for group in groups or [] if 0 <= group[1] < group[2] <= count]
    if usable:
        if spaced:
            add(_paint(_fit("│", panel_w), "rail", ansi))
        covered: set[int] = set()
        for name, start, end in usable:
            active = start <= selected < end
            symbol = "■" if active else "□"
            style = "step-on" if active else "step-off"
            add(_paint(_fit(f"{symbol}  {name.upper()}", panel_w), style, ansi))
            emit(start, end)
            covered.update(range(start, end))
            if spaced:
                add(_paint(_fit("│", panel_w), "rail", ansi))
        for index in range(count):
            if index in covered:
                continue
            emit(index, index + 1)
    else:
        if spaced and lines:
            add(_paint(_fit("│", panel_w), "rail", ansi))
        add(_paint(_fit(f"■  {title}", panel_w), "step-on", ansi))
        if lead:
            width = max(8, panel_w - 3)
            for row in lead:
                for part in wrap_text(row, width):
                    add(_paint(_fit(f"│  {part}", panel_w), "item", ansi))
            if lead_meta:
                add(
                    _paint_detail_explain(
                        _fit(f"│  {lead_meta}", panel_w),
                        ansi=ansi,
                        truecolor=truecolor,
                    )
                )
        if roomy:
            add(_paint(_fit("│", panel_w), "rail", ansi))
        if count:
            emit(0, count)
        if spaced:
            add(_paint(_fit("│", panel_w), "rail", ansi))

    if typed:
        add(
            _paint_detail_explain(
                _fit(f"│  {typed}", panel_w),
                ansi=ansi,
                truecolor=truecolor,
            )
        )
    if blocks is not None and count:
        current = blocks[selected].action
    elif count:
        current = _option_parts(options[selected])[0]
    else:
        current = title
    _ = hint
    footer_hint = NAV_FOOTER
    full = f"└  {current}  ·  {footer_hint}"
    short = f"└  {footer_hint}"
    footer = full if len(full) <= panel_w else short
    if len(footer) <= panel_w:
        add(_paint(_fit(footer, panel_w), "rule", ansi), HIT_BACK)
    else:
        wrapped = wrap_text(footer_hint, max(8, panel_w - 3))
        add(_paint(_fit(f"└  {wrapped[0]}", panel_w), "rule", ansi), HIT_BACK)
        for row in wrapped[1:]:
            add(_paint(_fit(f"   {row}", panel_w), "rule", ansi), HIT_BACK)
    if paging:
        add(_paint(_fit("   ← previous", panel_w), "rule", ansi), HIT_PREV)
        add(_paint(_fit("   → next", panel_w), "rule", ansi), HIT_NEXT)
    return lines, hits


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
    detail: bool = False,
    blocks: Sequence[MenuBlock] | None = None,
    lead: Sequence[str] | None = None,
    lead_meta: str | None = None,
    typed: str | None = None,
    paging: bool = False,
) -> str:
    """One centered frame. `hero` paints the half-block DIGIVOICE wordmark."""
    global _ROW_HITS
    term_cols, term_rows = _term_size()
    cols = term_cols if cols is None else cols
    rows = term_rows if rows is None else rows
    panel_w = max(36, min(88, cols - 6))
    if hero and not subtitle:
        subtitle = "local speech control"
    elapsed = phase * 160 if t_ms is None else t_ms
    _ = pointer
    chosen_panel: list[str] = []
    chosen_hits: list[int | None] = []
    for density in ("roomy", "comfy", "compact", "tight"):
        panel, panel_hits = _panel_lines(
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
            detail=detail,
            truecolor=truecolor,
            blocks=blocks,
            lead=lead,
            lead_meta=lead_meta,
            typed=typed,
            paging=paging,
        )
        header_h = rows - len(panel)
        needed = 5 + _HERO_GAP + 1 if hero and density in {"roomy", "comfy"} else (5 if hero else 0)
        if header_h >= needed or density == "tight":
            chosen_panel = panel
            chosen_hits = panel_hits
            break
        chosen_panel = panel
        chosen_hits = panel_hits
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
    placed_n = len(word_lines) + len(chosen_panel)
    top = (rows - placed_n) // 2 if placed_n < rows else 0
    _ROW_HITS = [None] * top + [None] * len(word_lines) + chosen_hits
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
                packed_body = "".join(packed)
                cell = parse_sgr_mouse(packed_body)
                if cell is not None:
                    _note_pointer(cell)
                    return mouse_action(packed_body, pressed=ch == "M")
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
            joined = "".join(body)
            if joined.endswith("u") and ";" in joined:
                return _kitty_key(joined[:-1])
            if joined.startswith("27;") and joined.endswith("~"):
                return _modify_other_key(joined[:-1])
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


def _write_numbered(
    stdout: TextIO,
    title: str,
    options: Sequence[str],
    blocks: Sequence[MenuBlock] | None,
    *,
    paging: bool,
) -> None:
    stdout.write(f"\n{title}\n")
    rows = list(blocks) if blocks is not None else None
    count = len(rows) if rows is not None else len(options)
    for index in range(count):
        if rows is not None:
            block = rows[index]
            stdout.write(f"  {index + 1}) {block.action}\n")
            for extra in (block.shortcut, block.path, block.meta):
                if extra:
                    stdout.write(f"     {extra}\n")
        else:
            stdout.write(f"  {index + 1}) {options[index]}\n")
    if paging:
        stdout.write("  (number, next/prev, /path, or blank to go back)\n")
    else:
        stdout.write("  (number, /path, or blank to go back)\n")
    stdout.flush()


def choose(
    title: str,
    options: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    hint: str | None = None,
    subtitle: str | None = None,
    context: Sequence[str] | None = None,
    *,
    hero: bool = False,
    pulse: bool = False,
    groups: Sequence[Group] | None = None,
    detail: bool = False,
    start_at: int = 0,
    paging: bool = False,
    blocks: Sequence[MenuBlock] | None = None,
    shortcuts: Mapping[str, int] | None = None,
    lead: Sequence[str] | None = None,
    lead_meta: str | None = None,
) -> int | str | None:
    """Pick an option index. Arrow/Enter on a TTY, numbered prompt otherwise.

    TTY mode paints a step-rail frame and redraws on every key. The footer
    is always ``↑↓ move · enter select · esc back · click``. Up and down
    move. Enter selects. Esc goes back. A click on a row selects it. A click
    on the footer goes back. ``q`` also goes back and is not in the footer.
    Left and right are page changes only when ``paging`` is set; they are
    not a second back or select. `/` starts a slash path; Enter runs it.
    A shortcut key returns that index. `c` copies when the screen binds it;
    Command-C / Windows-C does too when the terminal forwards the chord.
    `hero` paints the DIGIVOICE pixel lockup. ``start_at`` is the row to
    land on. Returns None on back. With `paging`, left/right and the
    previous/next rows return ``page-prev`` and ``page-next``.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    listed = list(options or [])
    if blocks is not None:
        listed = [block.action for block in blocks]
    if _is_tty(stdin):
        if not listed:
            return None
        selected = start_at % len(listed)
        color = _use_ansi()
        screen = _use_screen()
        color_true = _truecolor()
        live = pulse and screen and not _reduce_motion()
        phase = 0
        first = True
        typed = ""
        fd = stdin.fileno()
        saved = termios.tcgetattr(fd)
        if hero and _hero_origin is not None:
            origin = _hero_origin
        elif hero:
            origin = time.monotonic() - _BUILD_MS / 1000
        else:
            origin = time.monotonic()
        mouse_on = bool(screen and _is_tty(stdout))
        try:
            _set_menu_raw(fd)
            _cursor(stdout, False)
            if mouse_on:
                stdout.write(_MOUSE_ON)
                stdout.flush()
            while True:
                stdout.write(
                    render_screen(
                        title,
                        listed,
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
                        detail=detail,
                        blocks=blocks,
                        lead=lead,
                        lead_meta=lead_meta,
                        typed=typed or None,
                        paging=paging,
                    )
                )
                stdout.flush()
                first = False
                key = _read_key_on_fd(fd, 0.08 if live else None)
                if key is None or key == "mouse":
                    phase = (phase + 1) % 8
                    continue
                if key == "click" and _pointer is not None:
                    hit = hit_at(_pointer[1])
                    if hit is None:
                        continue
                    if hit == HIT_BACK:
                        return None
                    if hit == HIT_PREV and paging:
                        return "page-prev"
                    if hit == HIT_NEXT and paging:
                        return "page-next"
                    if hit >= 0:
                        return hit
                    continue
                if typed:
                    if key == "enter":
                        return typed
                    if key == "esc":
                        typed = ""
                        continue
                    if key in {"\x7f", "\x08"}:
                        typed = typed[:-1]
                        continue
                    if len(key) == 1 and key.isprintable():
                        typed += key
                    continue
                jumped = match_shortcut(key, shortcuts)
                if jumped is not None:
                    return jumped
                if key == "/":
                    typed = "/"
                    continue
                if key == "up" or key in {"k", "K"}:
                    selected = (selected - 1) % len(listed)
                elif key == "down" or key in {"j", "J"}:
                    selected = (selected + 1) % len(listed)
                elif paging and key == "left":
                    return "page-prev"
                elif paging and key == "right":
                    return "page-next"
                elif key in {"enter", " "}:
                    return selected
                elif key in {"esc", "q", "Q"}:
                    return None
        except (OSError, ValueError):
            return None
        finally:
            _note_pointer(None)
            if mouse_on:
                try:
                    stdout.write(_MOUSE_OFF)
                    stdout.flush()
                except (OSError, ValueError):
                    pass
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            _cursor(stdout, True)
        return None
    _write_numbered(stdout, title, listed, blocks, paging=paging)
    try:
        raw = stdin.readline()
    except (OSError, ValueError):
        return None
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("/"):
        return raw
    if paging and raw.casefold() in {"n", "next", ">", "l"}:
        return "page-next"
    if paging and raw.casefold() in {"p", "prev", "<", "h"}:
        return "page-prev"
    try:
        index = int(raw) - 1
    except ValueError:
        return None
    return index if 0 <= index < len(listed) else None


def _ctrl_byte(first: str) -> str | None:
    """A raw control byte is ``ctrl+letter`` (NUL is ``ctrl+space``)."""
    if first == "\x00":
        return "ctrl+space"
    if "\x01" <= first <= "\x1a":
        return "ctrl+" + chr(ord(first) + 96)
    return None


def _read_csi(fd: int) -> str | None:
    """Bytes after CSI ``[``, including the final byte, or None on a short read."""
    peek = _read_byte(fd, 0.04)
    if peek is None:
        return None
    if "@" <= peek <= "~":
        return peek
    body = [peek]
    while True:
        ch = _read_byte(fd, 0.04)
        if ch is None:
            return None
        body.append(ch)
        if "@" <= ch <= "~":
            return "".join(body)
        if len(body) > 16:
            return None


def _read_capture_key(fd: int) -> str | None:
    """One capture key. Chords keep their modifiers. Ctrl-C is a chord, not a signal.

    Menus keep :func:`_read_key_on_fd`. This reader is only the hotkey row.
    """
    first_b = os.read(fd, 1)
    if not first_b:
        return None
    first = first_b.decode("latin-1")
    if first == "\x1b":
        second = _read_byte(fd, 0.04)
        if second is None:
            return "esc"
        if second == "[":
            joined = _read_csi(fd)
            if joined is None:
                return "esc"
            if joined.startswith("<") and joined[-1] in "Mm":
                packed = joined[1:-1]
                cell = parse_sgr_mouse(packed)
                if cell is not None:
                    _note_pointer(cell)
                    return mouse_action(packed, pressed=joined[-1] == "M")
                return "esc"
            if joined.endswith("u") and ";" in joined:
                return chord_from_kitty(joined[:-1]) or "esc"
            if joined.startswith("27;") and joined.endswith("~"):
                return chord_from_modify_other(joined[:-1]) or "esc"
            return _arrow_name(joined[-1])
        if second == "O":
            third = _read_byte(fd, 0.04)
            return "esc" if third is None else _arrow_name(third)
        return "esc"
    if first in {"\r", "\n"}:
        return "enter"
    chord = _ctrl_byte(first)
    if chord is not None:
        return chord
    return first


def capture_binding(
    title: str,
    blocks: Sequence[MenuBlock],
    selected: int,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    subtitle: str | None = None,
) -> str | None:
    """Read a hotkey for one row. Esc cancels. Enter locks the binding in.

    Nothing is returned until Enter, so a press alone is not saved. A pressed
    chord fills the field and still waits. Typed names work the same way:
    ``Right Option``, ``Double-tap Left Option``, ``Esc``, ``ctrl+shift+space``.
    Blank Enter cancels. The capture loop is only this row. Non-TTY reads one
    line so a pipe cannot hang.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    shown = list(blocks)
    if not shown or not 0 <= selected < len(shown):
        return None
    if not _is_tty(stdin):
        stdout.write("input new hotkey\n")
        stdout.flush()
        try:
            raw = stdin.readline()
        except (OSError, ValueError):
            return None
        if not raw:
            return None
        text = raw.strip()
        return text or None
    fd = stdin.fileno()
    saved = termios.tcgetattr(fd)
    typed = ""
    first = True
    try:
        _set_menu_raw(fd)
        _cursor(stdout, False)
        if _use_screen():
            stdout.write(_KITTY_PUSH + _MODIFY_PUSH)
            stdout.flush()
        while True:
            preview = "input new hotkey" if not typed else f"input new hotkey  {typed}"
            armed = [
                block.model_copy(update={"meta": preview}) if index == selected else block
                for index, block in enumerate(shown)
            ]
            stdout.write(
                render_screen(
                    title,
                    [block.action for block in armed],
                    selected,
                    subtitle=subtitle,
                    hint=NAV_FOOTER,
                    use_ansi=_use_ansi(),
                    use_screen=_use_screen(),
                    clear=first,
                    redraw=not first,
                    truecolor=_truecolor(),
                    blocks=armed,
                )
            )
            stdout.flush()
            first = False
            key = _read_capture_key(fd)
            if key is None or key in {"mouse", "click"}:
                continue
            if key == "esc":
                return None
            if key == "enter":
                return typed.strip() or None
            if key in {"\x7f", "\x08"}:
                typed = typed[:-1]
                continue
            if len(key) == 1 and key.isprintable():
                typed += key
                continue
            # A pressed chord fills the field. Enter still has to lock it in.
            typed = key
    except (OSError, ValueError):
        return None
    finally:
        if _use_screen():
            try:
                stdout.write(_KITTY_POP + _MODIFY_POP)
                stdout.flush()
            except (OSError, ValueError):
                pass
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        _cursor(stdout, True)


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
        hint = NAV_FOOTER
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
        footer_bits.append(NAV_FOOTER)
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
    "HIT_BACK",
    "HIT_NEXT",
    "HIT_PREV",
    "NAV_FOOTER",
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
