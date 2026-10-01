"""Shared stdlib TUI primitives: ANSI frames, pixel wordmark, menus.

Home (`home.py`) and setup (`setup.py`) draw from here so the whole CLI shares
one in-place redraw contract: CSI clear+home plus a full repaint on every key,
never scroll-appended menus. Speech stays local; nothing here touches hardware.
"""

from __future__ import annotations

import sys
from typing import TextIO

# --- Interactive wizard (stdlib only) -------------------------------------
#
# TTY rendering contract (CHR-860 craft pass):
# - Full redraw in place on every keypress: CSI clear + home, then the whole
#   frame (pixel header + title + options + footer). Never scroll-append menus.
# - Non-TTY paths (StringIO / pipes / agents) are byte-stable and keep the
#   numbered prompt so `--print` / `DIGIVOICE_SETUP_NONINTERACTIVE` / `--json`
#   and the unit tests using StringIO stay unchanged.

_ANSI_HIDE = "\x1b[?25l"
_ANSI_SHOW = "\x1b[?25h"
_ANSI_CLEAR_HOME = "\x1b[2J\x1b[H"
_ANSI_CLEAR_EOL = "\x1b[K"
_ANSI_INV = "\x1b[7m"
_ANSI_BOLD = "\x1b[1m"
_ANSI_DIM = "\x1b[2m"
_ANSI_RESET = "\x1b[0m"

_DEFAULT_SUBTITLE = "digivoice setup · local speech config"

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

TUI_FOOTER_HINT = "↑↓ move · Enter select · Space select · Esc back · q quit"


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
    """Pixel wordmark + subtitle used as the TTY frame header."""
    return [pixel_wordmark(), "", subtitle or _DEFAULT_SUBTITLE]


def _is_tty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except Exception:
        return False


def _read_key(stdin: TextIO) -> str:
    """Read one keypress, translating ANSI arrows to names. Requires a TTY."""
    import termios
    import tty as _tty

    fd = stdin.fileno()
    old = _tty.tcgetattr(fd) if hasattr(_tty, "tcgetattr") else None
    try:
        _tty.setraw(fd)
        first = stdin.read(1)
    finally:
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if first == "\x1b":
        second = stdin.read(1)
        if second == "[":
            third = stdin.read(1)
            return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(third, "esc")
        return "esc"
    if first in {"\r", "\n"}:
        return "enter"
    if first == "\x03":  # Ctrl-C
        raise KeyboardInterrupt
    return first


def _use_ansi() -> bool:
    import os

    if os.environ.get("NO_COLOR"):
        return False
    return os.environ.get("TERM", "") != "dumb"


def _render_menu_frame(
    title: str,
    options: list[str],
    selected: int,
    hint: str | None = None,
    checked: set[int] | None = None,
    subtitle: str | None = None,
) -> str:
    """Build one full TTY frame: clear+home, pixel header, menu, footer."""
    use_ansi = _use_ansi()
    inv, bold, dim, reset, clear_eol = (
        (_ANSI_INV, _ANSI_BOLD, _ANSI_DIM, _ANSI_RESET, _ANSI_CLEAR_EOL)
        if use_ansi
        else ("", "", "", "", "")
    )
    lines = [_ANSI_CLEAR_HOME]
    lines.extend(tui_header_lines(subtitle))
    lines.append(f"{title}")
    for i, option in enumerate(options):
        marker = "▶" if i == selected else " "
        if checked is not None:
            box = "[x]" if i in checked else "[ ]"
            text = f"  {marker} {box} {option}"
        else:
            text = f"  {marker} {option}"
        if i == selected and use_ansi:
            text = f"{inv}{bold}{text}{reset}"
        lines.append(text + clear_eol)
    lines.append(f"{dim}  ({hint or TUI_FOOTER_HINT}){reset}{clear_eol}")
    return "\n".join(lines) + "\n"


def choose(
    title: str,
    options: list[str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    hint: str | None = None,
    subtitle: str | None = None,
) -> int | None:
    """Pick an option index. Arrow/Enter on a TTY, numbered prompt otherwise.

    TTY mode redraws the whole frame in place on every key (CSI clear+home)
    so menu lines never duplicate. Space confirms like Enter; Esc/q goes back.
    Returns None on Esc/back/quit.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if _is_tty(stdin):
        if not options:
            return None
        selected = 0
        use_ansi = _use_ansi()
        try:
            if use_ansi:
                stdout.write(_ANSI_HIDE)
            while True:
                stdout.write(_render_menu_frame(title, options, selected, hint, subtitle=subtitle))
                stdout.flush()
                key = _read_key(stdin)
                if key == "up" or key in {"k", "K"}:
                    selected = (selected - 1) % len(options)
                elif key == "down" or key in {"j", "J"}:
                    selected = (selected + 1) % len(options)
                elif key in {"enter", " ", "right"}:
                    return selected
                elif key in {"esc", "q", "Q", "left"}:
                    return None
        except (OSError, ValueError):
            pass  # fall through to the numbered prompt
        finally:
            try:
                if use_ansi:
                    stdout.write(_ANSI_SHOW)
                    stdout.flush()
            except (OSError, ValueError):
                pass
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
        return None  # EOF: never block an agent/pipe.
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

    TTY mode redraws in place like :func:`choose`. Non-TTY falls back to a
    comma-separated numbered prompt so agents/pipes never hang.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if _is_tty(stdin):
        selected = 0
        checked: set[int] = set(initial or set())
        use_ansi = _use_ansi()
        hint = "↑↓ move · Space toggle · Enter confirm · Esc back · q quit"
        try:
            if use_ansi:
                stdout.write(_ANSI_HIDE)
            while True:
                stdout.write(_render_menu_frame(title, options, selected, hint, checked, subtitle))
                stdout.flush()
                key = _read_key(stdin)
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
            try:
                if use_ansi:
                    stdout.write(_ANSI_SHOW)
                    stdout.flush()
            except (OSError, ValueError):
                pass
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
    """Wait for one line. EOF returns immediately so pipes never hang."""
    stdout = stdout or sys.stdout
    stdin = stdin or sys.stdin
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
    """Full redraw of a read-only info screen (TTY) to avoid scroll-append."""
    use_ansi = _use_ansi()
    dim, reset, clear_eol = (_ANSI_DIM, _ANSI_RESET, _ANSI_CLEAR_EOL) if use_ansi else ("", "", "")
    lines = [_ANSI_CLEAR_HOME]
    lines.extend(tui_header_lines(subtitle))
    lines.append(title)
    lines.extend(line + clear_eol for line in body)
    lines.append(f"{dim}  ({footer} · Esc back · q quit){reset}{clear_eol}")
    stdout.write("\n".join(lines) + "\n")
    stdout.flush()


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
    cells = pixel_wordmark_cells(word)
    lit = {(x, y) for i, (x, y) in enumerate(cells) if (i * 7 + x * 3 + y) % 10 < frac * 10}
    width = max((x for x, _ in cells), default=0) + 1
    rows: list[str] = []
    for y in range(10):
        rows.append("".join("█" if (x, y) in lit else " " for x in range(width)).rstrip())
    return "\n".join(rows)


def play_intro(
    stdout: TextIO,
    subtitle: str | None = None,
    steps: tuple[float, ...] = (0.3, 0.6, 1.0),
    delay: float = 0.06,
) -> None:
    """Brief pixel build-in before the home menu. TTY only; skips on error."""
    import time

    try:
        for frac in steps:
            stdout.write(_ANSI_CLEAR_HOME + pixel_build_frame(frac=frac) + "\n\n")
            stdout.write((subtitle or _DEFAULT_SUBTITLE) + "\n")
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
    "_write_info_frame",
    "choose",
    "choose_many",
    "pixel_build_frame",
    "pixel_wordmark",
    "pixel_wordmark_cells",
    "play_intro",
    "tui_header_lines",
]
