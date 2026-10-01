"""Centered home frame: wordmark, status, step rail. Non-TTY overview stays plain."""

from __future__ import annotations

import pytest
from digivoice.home import HOME_GROUPS, HOME_MENU, render_home_overview
from digivoice.tui import render_screen, render_wordmark_lines

pytestmark = pytest.mark.unit

_CONTEXT = [
    "models: stt ggml-base.en · tts (auto) — banner full (top-center)",
    "health: ok (4/4 ready)",
]


def _frame(**overrides: object) -> str:
    params: dict[str, object] = {
        "subtitle": "local speech control",
        "context": _CONTEXT,
        "hero": True,
        "groups": HOME_GROUPS,
        "cols": 120,
        "rows": 48,
        "use_ansi": False,
        "clear": False,
    }
    params.update(overrides)
    return render_screen("Actions", list(HOME_MENU), 0, **params)  # type: ignore[arg-type]


def test_wordmark_is_five_half_block_rows() -> None:
    rows = render_wordmark_lines("DIGIVOICE", cols=120, ansi=False)
    assert len(rows) == 5
    assert len(rows[0]) == 79
    assert all(len(row) == len(rows[0]) for row in rows)
    assert any(ch in "\n".join(rows) for ch in "▀▄█")


def test_wordmark_glint_changes_with_phase() -> None:
    first = render_wordmark_lines("DIGIVOICE", cols=120, phase=0, ansi=True)
    later = render_wordmark_lines("DIGIVOICE", cols=120, phase=3, ansi=True)
    assert first != later
    assert "\x1b[" in first[0]


def test_wordmark_builds_in() -> None:
    bare = render_wordmark_lines("DIGIVOICE", cols=120, frac=0, ansi=False)
    full = render_wordmark_lines("DIGIVOICE", cols=120, frac=1, ansi=False)
    assert "\n".join(bare).strip() == ""
    assert "█" in "\n".join(full)


def test_home_frame_is_centered_with_a_step_rail() -> None:
    frame = _frame()
    assert "▶" not in frame
    assert any(ch in frame for ch in "▀▄█")
    assert "STATUS" in frame
    assert "▦" in frame and "▥" in frame and ("■" in frame or "□" in frame)
    for name in ("OPERATE", "MAINTAIN", "CONFIGURE", "LEAVE"):
        assert name in frame
    for item in HOME_MENU:
        assert item.split(" (")[0] in frame
    doctor = next(line for line in frame.splitlines() if "Doctor" in line)
    settings = next(line for line in frame.splitlines() if "Settings" in line)
    assert "■" in doctor
    assert "□" in settings
    assert "■" not in settings
    content = [line for line in frame.splitlines() if line.strip()]
    assert content[0].startswith(" ")
    blanks = 0
    for line in frame.splitlines():
        if line.strip():
            break
        blanks += 1
    assert blanks >= 2


def test_home_frame_keeps_every_action_on_a_short_terminal() -> None:
    frame = _frame(cols=80, rows=24)
    for item in HOME_MENU:
        assert item.split(" (")[0] in frame
    assert "STATUS" in frame


def test_plain_frame_has_no_cursor_codes() -> None:
    assert "\x1b" not in _frame()


def test_groups_cover_the_home_menu_in_order() -> None:
    covered: list[int] = []
    for _name, start, end in HOME_GROUPS:
        covered.extend(range(start, end))
    assert covered == list(range(len(HOME_MENU)))


def test_non_tty_overview_stays_the_plain_tree() -> None:
    text = render_home_overview("settings-body")
    assert text.startswith("┌─ DIGIVOICE")
    assert "▶ Doctor" in text
    assert "settings-body" in text


def test_no_color_still_emits_clear_home_when_screen_on() -> None:
    """NO_COLOR must not disable clear/home — that stacks intro+home frames."""
    frame = render_screen(
        "Actions",
        list(HOME_MENU),
        0,
        hero=True,
        groups=HOME_GROUPS,
        cols=100,
        rows=40,
        use_ansi=False,
        use_screen=True,
        clear=True,
    )
    assert "\x1b[2J" in frame and "\x1b[H" in frame
    assert "\x1b[7m" not in frame  # no inverse SGR without color


def test_read_key_keeps_csi_and_ss3_arrows_intact() -> None:
    """Buffered stdin.read + select(fd) used to split \x1b[A into esc/[ /A."""
    import os
    import pty
    import termios
    import threading
    import time
    import tty

    from digivoice.tui import _read_key, _read_key_on_fd

    master, slave = pty.openpty()
    # One-shot path: a single CSI must not become esc (the home quit key).
    stdin = os.fdopen(slave, "r", buffering=1)

    def feed_one() -> None:
        time.sleep(0.05)
        os.write(master, b"\x1b[A")

    threading.Thread(target=feed_one, daemon=True).start()
    assert _read_key(stdin, timeout=0.5) == "up"
    stdin.close()
    os.close(master)

    # Held-raw path (menu loop): bulk CSI+SS3 must each decode, none lost to
    # cooked restore between keys.
    master, slave = pty.openpty()
    saved = termios.tcgetattr(slave)
    tty.setraw(slave)

    def feed_many() -> None:
        time.sleep(0.05)
        os.write(master, b"\x1b[A\x1b[B\x1bOA\x1bOBq")

    threading.Thread(target=feed_many, daemon=True).start()
    got = [_read_key_on_fd(slave, timeout=0.5) for _ in range(5)]
    termios.tcsetattr(slave, termios.TCSADRAIN, saved)
    os.close(slave)
    os.close(master)
    assert got == ["up", "down", "up", "down", "q"], got


def test_compose_uses_crlf_line_breaks() -> None:
    """Frames must use CRLF so paints under held-raw input do not staircase."""
    frame = _frame(use_screen=True, clear=True)
    assert "\r\n" in frame
    without_crlf = frame.replace("\r\n", "")
    assert "\n" not in without_crlf


def test_menu_raw_keeps_opost_for_newline_translation() -> None:
    """tty.setraw clears OPOST; menu raw must put it back or home paints explode."""
    import os
    import pty
    import termios

    from digivoice.tui import _set_menu_raw

    master, slave = pty.openpty()
    try:
        before = termios.tcgetattr(slave)
        assert before[1] & termios.OPOST
        _set_menu_raw(slave)
        after = termios.tcgetattr(slave)
        assert after[1] & termios.OPOST, "OPOST must stay on while menu raw is held"
        assert after[1] & termios.ONLCR, "ONLCR must stay on for NL→CRLF"
        assert not (after[3] & termios.ICANON), "input must stay non-canonical"
        assert not (after[3] & termios.ECHO), "echo must stay off"
    finally:
        os.close(slave)
        os.close(master)
