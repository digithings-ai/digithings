"""Centered home frame: wordmark, status, step rail. Non-TTY overview stays plain."""

from __future__ import annotations

import pytest
from digivoice.home import HOME_GROUPS, HOME_MENU, render_home_overview
from digivoice.pixel_hero import word_cells
from digivoice.settings import default_settings
from digivoice.setup import postprocess_menu_options
from digivoice.tui import (
    _alpha_sgr,
    parse_sgr_mouse,
    render_screen,
    render_wordmark_lines,
    wrap_text,
)

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
    """Version 3: five centered half-block rows, one terminal foreground."""
    rows = render_wordmark_lines("DIGIVOICE", cols=120, ansi=False)
    assert len(rows) == 5
    assert len(rows[0]) == 79
    assert all(len(row) == len(rows[0]) for row in rows)
    assert any(ch in "\n".join(rows) for ch in "▀▄█")


def test_wordmark_glint_is_a_short_flash() -> None:
    """A glint cell jumps to the brightest gray, then returns to its own shade."""
    letters, _stray = word_cells("DIGIVOICE", 2)
    changed = False
    for glint in letters:
        if not glint.glint or glint.f >= 1:
            continue
        before = render_wordmark_lines(
            "DIGIVOICE", cols=120, ansi=True, t_ms=glint.glint_delay_ms - 50
        )
        during = render_wordmark_lines(
            "DIGIVOICE", cols=120, ansi=True, t_ms=glint.glint_delay_ms + 40
        )
        if before != during:
            changed = True
            assert "38;5;231" in "\n".join(during)
            assert "38;2;" not in "\n".join(during)
            break
    assert changed


def test_wordmark_shades_are_terminal_grays() -> None:
    """Cube indexes, not the 232–255 ramp Terminal.app paints as one white."""
    codes = [_alpha_sgr(alpha) for alpha in (0.36, 0.5, 0.66, 0.82, 1.0)]
    assert codes == [
        "\x1b[38;5;59m",
        "\x1b[38;5;102m",
        "\x1b[38;5;145m",
        "\x1b[38;5;188m",
        "\x1b[38;5;231m",
    ]
    joined = "\n".join(render_wordmark_lines("DIGIVOICE", cols=120, ansi=True, t_ms=1600))
    assert "38;2;" not in joined
    present = {level for level in ("59", "102", "145", "188", "231") if f"38;5;{level}" in joined}
    assert len(present) >= 3


def test_wordmark_truecolor_matches_the_cube() -> None:
    assert _alpha_sgr(0.36, truecolor=True) == "\x1b[38;2;95;95;95m"
    assert _alpha_sgr(1.0, truecolor=True) == "\x1b[38;2;255;255;255m"
    joined = "\n".join(
        render_wordmark_lines("DIGIVOICE", cols=120, ansi=True, t_ms=1600, truecolor=True)
    )
    assert "38;2;95;95;95" in joined
    assert "38;2;255;255;255" in joined
    assert "38;5;" not in joined


def test_wordmark_v_is_the_version3_block_letter() -> None:
    """The home V is the centered half-block from f62e5982d, not the pointed landing V."""
    rows = render_wordmark_lines("DIGIVOICE", cols=120, ansi=False)
    assert rows[-1].split()[4] == "▀███▀"


def test_selected_row_is_brackets_with_a_star() -> None:
    """Selection is a bold ``[*]``. The row is not a teal bar."""
    plain = _frame()
    doctor = next(line for line in plain.splitlines() if "Doctor" in line)
    assert "[*]" in doctor
    colored = _frame(use_ansi=True)
    assert "38;2;61;214;196" not in colored
    colored_doctor = next(line for line in colored.splitlines() if "Doctor" in line)
    assert "\x1b[1m[*]" in colored_doctor
    assert "\x1b[7" not in colored_doctor


def test_wordmark_has_no_particle_field() -> None:
    plain = render_wordmark_lines("DIGIVOICE", cols=120, phase=0, ansi=False)
    assert not any("·" in row for row in plain)


def test_home_header_is_the_pixel_lockup_only() -> None:
    """The hero is the half-block wordmark. No waveform and no fact line."""
    frame = _frame()
    assert "local speech  /  on this mac  /  no cloud" not in frame
    assert "░" not in frame and "▒" not in frame
    assert "▀███▀" in frame
    assert "38;2;" not in frame


def test_hero_wordmark_builds_in_over_the_first_second() -> None:
    bare = _frame(t_ms=0)
    done = _frame(t_ms=1600)
    assert done.count("█") > bare.count("█")


def test_wordmark_builds_in() -> None:
    bare = render_wordmark_lines("DIGIVOICE", cols=120, frac=0, ansi=False)
    full = render_wordmark_lines("DIGIVOICE", cols=120, frac=1, ansi=False)
    assert "\n".join(bare).strip() == ""
    assert "█" in "\n".join(full)


def test_home_frame_is_centered_half_block() -> None:
    frame = _frame()
    assert "▶" not in frame
    assert any(ch in frame for ch in "▀▄█")
    assert "STATUS" in frame
    assert "local speech control" in frame
    assert "▦" in frame and "▥" in frame and ("■" in frame or "□" in frame)
    for name in ("OPERATE", "MAINTAIN", "CONFIGURE", "LEAVE"):
        assert name in frame
    for item in HOME_MENU:
        assert item.split(" (")[0] in frame
    doctor = next(line for line in frame.splitlines() if "Doctor" in line)
    settings = next(line for line in frame.splitlines() if "Settings" in line)
    assert "[*]" in doctor
    assert "[ ]" in settings
    assert "[*]" not in settings
    lines = frame.replace("\r\n", "\n").splitlines()
    letter_rows = [i for i, line in enumerate(lines) if any(ch in line for ch in "▀▄█")]
    assert letter_rows
    assert letter_rows[-1] - letter_rows[0] == 4
    gap = 0
    for line in lines[letter_rows[-1] + 1 :]:
        if line.strip():
            break
        gap += 1
    assert gap >= 2
    blanks = 0
    for line in lines:
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


def test_wrap_text_keeps_words_readable() -> None:
    lines = wrap_text(
        "off: paste the words as spoken; on: rewrite them with a local model first",
        40,
    )
    assert len(lines) >= 2
    assert all(len(line) <= 40 for line in lines)
    assert "paste the words as spoken" in " ".join(lines)
    assert "local model first" in " ".join(lines)


def test_postprocess_menu_wraps_on_typical_terminal() -> None:
    options = postprocess_menu_options(default_settings().model_dump(mode="json"))
    frame = render_screen(
        "Post-process",
        options,
        0,
        subtitle="After dictation, optionally rewrite the words with a local model.",
        cols=80,
        rows=28,
        use_ansi=False,
        clear=False,
    )
    body = frame.replace("\r\n", "\n")
    assert "…" not in body
    assert "as spoken" in body
    assert "local model" in body.casefold() or "rewrite" in body.casefold()
    assert "Give up after" in body
    assert "15" in body or "off" in body


def test_catalog_labels_wrap_without_ellipsis_at_80_cols() -> None:
    from digivoice.catalog import STT_CATALOG
    from digivoice.setup import _catalog_labels

    labels = _catalog_labels(STT_CATALOG, None)
    frame = render_screen(
        "Dictation model",
        labels,
        0,
        subtitle="Suggested local whisper.cpp files. Select to download and wire.",
        cols=80,
        rows=32,
        use_ansi=False,
        clear=False,
    )
    body = frame.replace("\r\n", "\n")
    assert "…" not in body
    assert "ggml-tiny.en" in body
    assert "ggml-base" in body
    assert "multilingual" in body or "many languages" in body
    assert "download + wire" in body


def test_sgr_mouse_motion_is_not_esc() -> None:
    """CSI <32;x;yM must not quit home even if a terminal reports motion."""
    assert parse_sgr_mouse("32;10;5") == (9, 4)
    assert parse_sgr_mouse("0;1;1") == (0, 0)
    assert parse_sgr_mouse("nope") is None

    import os
    import pty
    import termios
    import threading
    import time
    import tty

    from digivoice.tui import _read_key_on_fd

    master, slave = pty.openpty()
    saved = termios.tcgetattr(slave)
    tty.setraw(slave)

    def feed() -> None:
        time.sleep(0.05)
        os.write(master, b"\x1b[<32;12;8M\x1b[A")

    threading.Thread(target=feed, daemon=True).start()
    got = [_read_key_on_fd(slave, timeout=0.5) for _ in range(2)]
    termios.tcsetattr(slave, termios.TCSADRAIN, saved)
    os.close(slave)
    os.close(master)
    assert got == ["mouse", "up"], got
