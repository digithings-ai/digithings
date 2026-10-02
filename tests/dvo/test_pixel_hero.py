"""Landing pixel-hero port: 7×10 DIGIVOICE field, not a thin title line.

Visual SoT: apps/digithings-web PixelWordmark (7×10 `#` glyphs, mulberry32
seed 0xd161, STEPS alphas, 13 glints, 70 strays) plus PixelField ambient
shimmer behind the letters. The TUI spells DIGIVOICE in that same block
language and fills leftover header rows with the field.
"""

from __future__ import annotations

import pytest
from digivoice.home import HOME_GROUPS, HOME_MENU
from digivoice.pixel_hero import (
    GLINT_COUNT,
    PIXEL_GLYPHS,
    STEPS,
    STRAY_COUNT,
    WORDMARK_SEED,
    mulberry32,
    render_pixel_hero,
    word_cells,
)
from digivoice.tui import render_screen, render_wordmark_lines

pytestmark = pytest.mark.unit

# PixelWordmark.tsx D/I/G — copied so a drift in the TUI glyphs fails here.
_LANDING = {
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
}


def test_glyphs_are_7_by_10_hash_cells() -> None:
    for ch, rows in PIXEL_GLYPHS.items():
        assert len(rows) == 10, ch
        assert all(len(row) == 7 for row in rows), ch
        assert all(set(row) <= {"#", "."} for row in rows), ch


def test_shared_letters_match_landing_pixelwordmark() -> None:
    for ch, rows in _LANDING.items():
        assert PIXEL_GLYPHS[ch] == rows


def test_digivoice_letters_exist_in_the_same_block_language() -> None:
    for ch in "DIGIVOICE":
        assert ch in PIXEL_GLYPHS


def test_mulberry32_is_deterministic_unit_interval() -> None:
    first_rng = mulberry32(WORDMARK_SEED)
    second_rng = mulberry32(WORDMARK_SEED)
    first = [first_rng() for _ in range(8)]
    second = [second_rng() for _ in range(8)]
    assert first == second
    assert all(0 <= value < 1 for value in first)
    assert len(set(first)) > 1


def test_word_cells_follow_landing_glint_and_stray_counts() -> None:
    letters, stray = word_cells("DIGIVOICE")
    assert letters
    assert all(cell.kind == "letter" for cell in letters)
    assert sum(1 for cell in letters if cell.glint) == GLINT_COUNT
    assert len(stray) == STRAY_COUNT
    assert all(cell.kind == "stray" for cell in stray)
    used = {(cell.x, cell.y) for cell in letters}
    assert used.isdisjoint({(cell.x, cell.y) for cell in stray})
    for cell in letters:
        assert cell.f in STEPS
        assert 0.0 < cell.a <= 1.0


def test_word_cells_spell_digivoice_from_glyphs() -> None:
    letters, _stray = word_cells("DIGIVOICE")
    by_xy = {(cell.x, cell.y) for cell in letters}
    x = 0
    for ch in "DIGIVOICE":
        glyph = PIXEL_GLYPHS[ch]
        for y, row in enumerate(glyph):
            for c, mark in enumerate(row):
                point = (x + c, y)
                if mark == "#":
                    assert point in by_xy, (ch, point)
                else:
                    assert point not in by_xy, (ch, point)
        x += 9


def test_wordmark_is_ten_full_block_rows_not_half_blocks() -> None:
    """Landing cells are squares of `#`; the TUI keeps one █ per cell, 10 rows."""
    rows = render_wordmark_lines("DIGIVOICE", cols=120, ansi=False)
    assert len(rows) == 10
    joined = "\n".join(rows)
    assert "█" in joined
    assert "▀" not in joined
    assert "▄" not in joined
    assert all(len(row) == len(rows[0]) for row in rows)
    assert len(rows[0]) >= 79


def test_pixel_hero_fills_the_header_not_a_thin_title() -> None:
    lines = render_pixel_hero("DIGIVOICE", cols=120, rows=22, t_ms=900, frac=1.0, ansi=False)
    assert len(lines) == 22
    joined = "\n".join(lines)
    assert joined.count("█") >= 300
    # Field particles live outside the 10-row letter box.
    letter_rows = [i for i, line in enumerate(lines) if "█" in line]
    assert letter_rows
    assert letter_rows[0] > 0 or letter_rows[-1] < 21
    field = "".join(
        lines[i] for i in range(22) if i not in set(range(letter_rows[0], letter_rows[-1] + 1))
    )
    assert any(ch in field for ch in "·░█")


def test_pixel_hero_ambient_shimmer_moves_without_a_pointer() -> None:
    still = render_pixel_hero("DIGIVOICE", cols=100, rows=16, t_ms=0, ansi=False)
    later = render_pixel_hero("DIGIVOICE", cols=100, rows=16, t_ms=2400, ansi=False)
    assert still != later


def test_pixel_hero_pointer_trail_is_teal_not_rainbow() -> None:
    bare = "\n".join(render_pixel_hero("DIGIVOICE", cols=80, rows=14, t_ms=400, ansi=True))
    trailed = "\n".join(
        render_pixel_hero(
            "DIGIVOICE",
            cols=80,
            rows=14,
            t_ms=400,
            ansi=True,
            pointer=(40, 7),
        )
    )
    assert trailed != bare
    assert "38;2;61;214;196" in trailed
    for rgb in ("229;183;101", "226;112;138", "217;122;90", "90;163;196"):
        assert f"38;2;{rgb}" not in trailed, rgb


def test_pixel_hero_is_teal_gloom_not_a_rainbow_title() -> None:
    joined = "\n".join(render_pixel_hero("DIGIVOICE", cols=120, rows=16, t_ms=800, ansi=True))
    assert "38;2;61;214;196" in joined
    for rgb in ("229;183;101", "226;112;138", "217;122;90", "90;163;196"):
        assert f"38;2;{rgb}" not in joined, rgb


def test_pixel_hero_builds_in_letter_cells() -> None:
    empty = "\n".join(render_pixel_hero("DIGIVOICE", cols=100, rows=12, frac=0, ansi=False))
    full = "\n".join(render_pixel_hero("DIGIVOICE", cols=100, rows=12, frac=1, ansi=False))
    assert empty.count("█") < full.count("█")
    assert full.count("█") >= 300


def test_home_hero_uses_the_full_pixel_field() -> None:
    frame = render_screen(
        "Actions",
        list(HOME_MENU),
        0,
        subtitle="local speech control",
        context=["models: stt ggml-base.en · tts (auto) — banner full (top-center)"],
        hero=True,
        groups=HOME_GROUPS,
        cols=120,
        rows=48,
        use_ansi=False,
        clear=False,
        t_ms=1200,
    )
    body = frame.replace("\r\n", "\n")
    lines = body.splitlines()
    assert "▀" not in body and "▄" not in body
    assert body.count("█") >= 300
    assert "STATUS" in body
    for item in HOME_MENU:
        assert item.split(" (")[0] in body
    # Full-bleed header: leftover rows are field, not a vertically-centered island.
    stripped = [i for i, line in enumerate(lines) if line.strip()]
    assert stripped
    assert stripped[0] <= 2


def test_mid_height_terminal_keeps_field_around_the_letters() -> None:
    """36-row Ghostty/Terminal must not collapse the hero to a 10-row title strip."""
    frame = render_screen(
        "Actions",
        list(HOME_MENU),
        0,
        subtitle="local speech control",
        context=["models: stt ggml-base.en · tts (auto) — banner full (top-center)"],
        hero=True,
        groups=HOME_GROUPS,
        cols=100,
        rows=36,
        use_ansi=False,
        t_ms=900,
    )
    body = frame.replace("\r\n", "\n")
    lines = body.splitlines()
    letter_rows = [i for i, line in enumerate(lines) if "█" in line]
    assert letter_rows
    assert letter_rows[-1] - letter_rows[0] >= 9
    outside = [lines[i] for i in range(len(lines)) if i < letter_rows[0] or i > letter_rows[-1]]
    assert any("·" in line for line in outside)
    assert "STATUS" in body
    for item in HOME_MENU:
        assert item.split(" (")[0] in body
