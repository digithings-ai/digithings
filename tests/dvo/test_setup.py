"""Setup wizard non-interactive paths, doctor spine checks, and thin stubs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.paths import resolve_paths
from digivoice.settings import settings_path
from digivoice.setup import (
    SETUP_MENU,
    recommend_models,
    render_setup_overview,
    setup_public_dict,
)

from tests.dvo.fakes import FakeProbe

pytestmark = pytest.mark.unit

HOME = Path("/Users/chris")
MODELS = "/Users/chris/Library/Application Support/digivoice/models"
MODEL = f"{MODELS}/ggml-base.en.bin"


def _runtime(tmp_path: Path, **env: str) -> Runtime:
    merged = {"DIGIVOICE_DATA_DIR": str(tmp_path), **env}
    return Runtime(platform="linux", home=tmp_path, env=merged, probe=FakeProbe())


def test_setup_print_shows_settings_and_menu(tmp_path: Path) -> None:
    result = run(["setup", "--print"], _runtime(tmp_path))
    assert result.code == 0
    assert "digivoice setup" in result.stdout
    assert "stt_model" in result.stdout
    assert "banner_density" in result.stdout
    for item in SETUP_MENU:
        assert item.split(" (")[0] in result.stdout
    assert "Right Option" in result.stdout
    assert "#4939" in result.stdout


def test_setup_env_noninteractive_matches_print(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, DIGIVOICE_SETUP_NONINTERACTIVE="1")
    via_env = run(["setup"], runtime)
    via_flag = run(["setup", "--print"], _runtime(tmp_path))
    assert via_env.code == 0
    assert via_env.stdout == via_flag.stdout


def test_setup_print_needs_no_tty_and_exits_zero(tmp_path: Path) -> None:
    # Plain `setup` with piped stdin must never block on arrow keys.
    result = run(["setup"], _runtime(tmp_path))
    assert result.code == 0
    assert "digivoice setup" in result.stdout


def test_setup_json_has_menu_and_recommendations(tmp_path: Path) -> None:
    result = run(["setup", "--json"], _runtime(tmp_path))
    assert result.code == 0
    payload = json.loads(result.stdout)
    assert payload["paste_on_stop"] is True
    assert payload["setup_menu"] == list(SETUP_MENU)
    assert "hardware_recommendations" in payload
    assert "model_fields" in payload and "stt_model" in payload["model_fields"]


def test_recommend_models_stub_points_at_epic() -> None:
    recs = recommend_models()
    assert recs["tiers"]
    assert any(t["model"] == "ggml-base.en" for t in recs["tiers"])
    assert "#4939" in recs["pointer"]


def test_render_overview_lists_all_sections(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    from digivoice.settings import load_settings

    text = render_setup_overview(load_settings(paths), paths)
    assert "Models" in text and "Features" in text and "Hotkeys" in text
    assert "Hardware" in text


def test_setup_public_dict_extends_settings_dump(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    from digivoice.settings import load_settings

    payload = setup_public_dict(load_settings(paths), paths)
    assert payload["banner_density"] == "peek"
    assert payload["setup_menu"] == list(SETUP_MENU)


def test_interactive_review_save_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import io

    from digivoice.settings import load_settings
    from digivoice.setup import run_interactive_setup

    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    fake_in = io.StringIO("5\n1\n7\n")  # Review & save → Save → Quit
    fake_out = io.StringIO()
    code = run_interactive_setup(paths, stdin=fake_in, stdout=fake_out)
    assert code == 0
    assert (tmp_path / "settings.json").is_file()
    assert load_settings(paths).banner_density == "peek"
    assert "digivoice setup" in fake_out.getvalue()


def test_interactive_features_edit_persists(tmp_path: Path) -> None:
    import io

    from digivoice.settings import load_settings
    from digivoice.setup import run_interactive_setup

    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    # Features → banner_density → full → Back → Review & save → Save → Quit
    fake_in = io.StringIO("2\n4\n3\n6\n5\n1\n7\n")
    code = run_interactive_setup(paths, stdin=fake_in, stdout=io.StringIO())
    assert code == 0
    assert load_settings(paths).banner_density == "full"


def test_update_and_uninstall_are_documented_stubs(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    update = run(["update"], runtime)
    assert update.code == 0
    assert "not wired yet" in update.stdout
    uninstall = run(["uninstall"], runtime)
    assert uninstall.code == 0
    assert "not wired yet" in uninstall.stdout


def test_doctor_reports_settings_hotkeys_hammerspoon(tmp_path: Path) -> None:
    from digivoice.doctor import doctor_checks, render_doctor

    probe = FakeProbe(
        commands={
            "whisper-cli": "/opt/homebrew/bin/whisper-cli",
            "piper": "/opt/homebrew/bin/piper",
            "sox": "/opt/homebrew/bin/sox",
        },
        directories={MODELS},
        files={MODEL},
    )
    report = render_doctor(doctor_checks("darwin", HOME, {}, probe))
    by_id = {check.id: check for check in report.checks}
    assert by_id["settings"].status == "info"  # no file in real home-mapped dir
    assert by_id["hotkeys"].status == "ok"
    assert "Right Option" in by_id["hotkeys"].detail
    assert by_id["hammerspoon"].status == "missing"
    assert ".hammerspoon/digivoice" in by_id["hammerspoon"].detail


def test_doctor_settings_valid_then_corrupt(tmp_path: Path) -> None:
    from digivoice.doctor import doctor_checks, render_doctor

    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    probe = FakeProbe(directories={paths.models_dir}, files={f"{paths.models_dir}/x"})

    def _settings_status() -> str:
        report = render_doctor(
            doctor_checks("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)}, probe)
        )
        return next(c for c in report.checks if c.id == "settings").status

    assert _settings_status() == "info"
    settings_path(paths).write_text('{"banner_density": "full"}', encoding="utf-8")
    assert _settings_status() == "ok"
    settings_path(paths).write_text("{not json", encoding="utf-8")
    assert _settings_status() == "missing"


def test_doctor_hammerspoon_ok_when_adapter_present(tmp_path: Path) -> None:
    from digivoice.doctor import doctor_checks, render_doctor

    data_dir = tmp_path / "data"
    adapter = tmp_path / ".hammerspoon" / "digivoice"
    adapter.mkdir(parents=True)
    probe = FakeProbe(
        commands={"whisper-cli": "/usr/bin/whisper-cli"},
        directories={str(adapter)},
    )
    report = render_doctor(
        doctor_checks("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(data_dir)}, probe)
    )
    found = next(c for c in report.checks if c.id == "hammerspoon")
    assert found.status == "ok"
    assert str(adapter) in found.detail
