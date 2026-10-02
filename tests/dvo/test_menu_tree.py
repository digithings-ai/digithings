"""Settings path: folders, toggles, cycles, and a line of explanation on each row."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from digivoice.menu_tree import browse_settings, rows_at
from digivoice.paths import resolve_paths
from digivoice.settings import VoiceSettings, load_settings

pytestmark = pytest.mark.unit


def _paths(tmp_path: Path):
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def _walk(settings: VoiceSettings, path: str = "/settings") -> list:
    rows = rows_at(settings, path)
    found = list(rows)
    for row in rows:
        if row.kind == "dir":
            found.extend(_walk(settings, f"{path}/{row.name}"))
    return found


def test_settings_root_is_four_folders() -> None:
    rows = rows_at(VoiceSettings(), "/settings")
    assert [row.name for row in rows] == ["speech", "rewrite", "banner", "hotkeys"]
    assert all(row.kind == "dir" for row in rows)


def test_every_row_explains_itself() -> None:
    rows = _walk(VoiceSettings())
    assert rows
    for row in rows:
        assert row.explain
        assert "(" not in row.explain
        assert row.explain in row.label()
        if row.value:
            assert f"[{row.value}]" in row.label()


def test_browse_toggles_paste(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("1\n3\n\n\n"), io.StringIO())
    assert load_settings(paths).paste_on_stop is False


def test_browse_cycles_banner_density(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("3\n3\n\n\n"), io.StringIO())
    assert load_settings(paths).banner_density == "full"


def test_browse_esc_at_the_root_changes_nothing(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("\n"), io.StringIO())
    assert load_settings(paths).paste_on_stop is True
    assert load_settings(paths).banner_density == "retract"
