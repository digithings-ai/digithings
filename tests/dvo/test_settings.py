"""Settings JSON load/save and CLI get/set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.paths import resolve_paths
from digivoice.settings import (
    VoiceSettings,
    load_settings,
    parse_setting_value,
    save_settings,
    set_setting,
    settings_path,
)

from tests.dvo.fakes import FakeProbe

pytestmark = pytest.mark.unit


def test_defaults_keep_rewrite_disabled(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    settings = load_settings(paths)
    assert settings.rewrite_enabled is False
    assert settings.rewrite_preset == "none"
    assert settings.paste_on_stop is True
    assert settings.word_detection is False
    assert settings.spelling_detection is False


def test_detection_flags_set_get_round_trip(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    set_setting(paths, "word_detection", "true")
    set_setting(paths, "spelling_detection", "on")
    saved = load_settings(paths)
    assert saved.word_detection is True
    assert saved.spelling_detection is True
    set_setting(paths, "word_detection", "off")
    assert load_settings(paths).word_detection is False


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    settings = VoiceSettings(
        rewrite_enabled=True,
        rewrite_preset="email",
        rewrite_model="qwen2.5:3b",
        rewrite_runner="ollama",
        rewrite_auto_route=True,
    )
    target = save_settings(paths, settings)
    assert target == settings_path(paths)
    assert target.is_file()
    loaded = load_settings(paths)
    assert loaded.rewrite_enabled is True
    assert loaded.rewrite_preset == "email"
    assert loaded.rewrite_model == "qwen2.5:3b"
    assert loaded.rewrite_auto_route is True


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    settings_path(paths).parent.mkdir(parents=True, exist_ok=True)
    settings_path(paths).write_text("{not json", encoding="utf-8")
    assert load_settings(paths).rewrite_enabled is False


def test_parse_bool_and_null() -> None:
    assert parse_setting_value("rewrite_enabled", "true") is True
    assert parse_setting_value("rewrite_enabled", "OFF") is False
    assert parse_setting_value("rewrite_model", "none") is None
    with pytest.raises(ValueError):
        parse_setting_value("rewrite_enabled", "maybe")


def test_cli_settings_show_and_json(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    text = run(["settings"], runtime)
    assert text.code == 0
    assert "rewrite_enabled" in text.stdout
    assert "Right Option" in text.stdout
    assert "paste + new take" in text.stdout

    as_json = run(["settings", "--json"], runtime)
    assert as_json.code == 0
    payload = json.loads(as_json.stdout)
    assert payload["rewrite_enabled"] is False
    assert "paths" in payload
    assert "hotkeys" in payload


def test_cli_settings_set_get(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    saved = run(["settings", "set", "rewrite_enabled", "true"], runtime)
    assert saved.code == 0
    assert (tmp_path / "settings.json").is_file()
    got = run(["settings", "get", "rewrite_enabled"], runtime)
    assert got.stdout.strip() == "true"
    preset = run(["settings", "set", "rewrite_preset", "coding"], runtime)
    assert preset.code == 0
    assert (
        load_settings(
            resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
        ).rewrite_preset
        == "coding"
    )


def test_cli_setup_alias(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    result = run(["setup", "--json"], runtime)
    assert result.code == 0
    assert json.loads(result.stdout)["paste_on_stop"] is True


def test_set_setting_rejects_unknown_key(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    with pytest.raises(KeyError):
        set_setting(paths, "not_a_key", "1")


def test_help_lists_settings() -> None:
    runtime = Runtime(platform="linux", home=Path("/tmp"), env={}, probe=FakeProbe())
    result = run([], runtime)
    assert "settings" in result.stdout
    assert "setup" in result.stdout


def test_banner_defaults_and_knobs(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    shown = json.loads(run(["settings", "--json"], runtime).stdout)
    assert shown["live_banner"] is True
    assert shown["banner_position"] == "top-center"
    assert shown["banner_density"] == "peek"
    assert shown["banner_animations"] is True
    assert run(["settings", "set", "banner_position", "bottom-right"], runtime).code == 0
    assert run(["settings", "set", "banner_density", "full"], runtime).code == 0
    assert run(["settings", "set", "banner_animations", "off"], runtime).code == 0
    assert run(["settings", "set", "live_banner", "false"], runtime).code == 0
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    saved = load_settings(paths)
    assert (
        saved.banner_position,
        saved.banner_density,
        saved.banner_animations,
        saved.live_banner,
    ) == (
        "bottom-right",
        "full",
        False,
        False,
    )
    on_disk = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert on_disk["banner_position"] == "bottom-right"
    assert on_disk["banner_density"] == "full"


def test_banner_density_rejects_unknown_values(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    bad = run(["settings", "set", "banner_density", "huge"], runtime)
    assert bad.code == 2
    assert not (tmp_path / "settings.json").exists()


def test_banner_position_rejects_unknown_values(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    bad = run(["settings", "set", "banner_position", "middle-ish"], runtime)
    assert bad.code == 2
    assert not (tmp_path / "settings.json").exists()


def test_banner_position_accepts_middle_anchors(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    assert run(["settings", "set", "banner_position", "middle-left"], runtime).code == 0
    assert run(["settings", "set", "banner_position", "middle-right"], runtime).code == 0
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    assert load_settings(paths).banner_position == "middle-right"
