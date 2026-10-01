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
    assert "models" in frame and "banner" in frame and "health" in frame
    for name in ("OPERATE", "MAINTAIN", "CONFIGURE", "LEAVE"):
        assert name in frame
    for item in HOME_MENU:
        assert item.split(" (")[0] in frame
    doctor = next(line for line in frame.splitlines() if "Doctor" in line)
    settings = next(line for line in frame.splitlines() if "Settings" in line)
    assert "✓" in doctor
    assert "○" in settings
    assert "✓" not in settings
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
