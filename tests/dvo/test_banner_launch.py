"""Banner click uses a fake launcher. Nothing here starts Terminal or Hammerspoon."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.banner_launch import banner_click, mark_tui_closed, mark_tui_open, read_tui_open

pytestmark = pytest.mark.unit


def test_click_opens_then_focuses_without_stacking() -> None:
    seen: list[str] = []

    def launch(action: str) -> None:
        seen.append(action)

    assert banner_click(already_open=False, launcher=launch) == "open"
    assert banner_click(already_open=True, launcher=launch) == "focus"
    assert banner_click(already_open=True, launcher=launch) == "focus"
    assert seen == ["open", "focus", "focus"]


def test_pid_file_is_the_open_terminal(tmp_path: Path) -> None:
    assert read_tui_open(tmp_path) is False
    mark_tui_open(tmp_path)
    assert read_tui_open(tmp_path) is True
    mark_tui_closed(tmp_path)
    assert read_tui_open(tmp_path) is False
    assert not (tmp_path / "tui.pid").exists()
