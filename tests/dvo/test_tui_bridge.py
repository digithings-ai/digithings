"""OpenTUI launch argv and the local screen bridge."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.opentui import opentui_argv
from digivoice.paths import resolve_paths
from digivoice.settings import load_settings
from digivoice.tui_bridge import dispatch

pytestmark = pytest.mark.unit


def _env(tmp_path: Path) -> dict[str, str]:
    return {"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": ""}


def test_opentui_argv_points_at_the_node_app() -> None:
    argv = opentui_argv({"DIGIVOICE_NODE": "node"})
    assert argv[0] == "node"
    assert argv[1].endswith("digivoice/tui/src/main.js")
    assert Path(argv[1]).is_file()


def test_bridge_boot_lists_home_and_model_language_once(tmp_path: Path) -> None:
    env = _env(tmp_path)
    boot = dispatch({"op": "boot", "start": "/"}, platform="linux", home=tmp_path, env=env)
    actions = [row["action"] for row in boot["home"]]
    assert actions == ["History", "Settings", "System", "Quit"]
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    assert any("ggml-medium.en" in row["path"] for row in rows)
    assert any("ggml-large-v3" in row["path"] for row in rows)
    for row in rows:
        visible = f"{row['action']}\n{row['meta']}"
        language = "English" if "English" in visible else "multilingual"
        assert visible.count(language) == 1


def test_bridge_apply_confirms_before_a_missing_download(tmp_path: Path) -> None:
    env = _env(tmp_path)
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["path"].endswith("ggml-tiny.en"))
    pending = dispatch(
        {"op": "apply", "path": "/settings/speech/model", "index": index},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert pending["confirm"] is True
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).stt_model == "ggml-base.en"
    assert "Download" in pending["rows"][0]["action"]


def test_bridge_restart_does_not_stop_and_update_stays_a_note(tmp_path: Path) -> None:
    env = _env(tmp_path)
    restart = dispatch({"op": "restart"}, platform="linux", home=tmp_path, env=env)
    assert restart["restart"] is True
    assert "stopped" not in restart
    update = dispatch({"op": "update"}, platform="linux", home=tmp_path, env=env)
    assert "not wired yet" in update["note"]
    assert "uv tool install" in update["note"]
