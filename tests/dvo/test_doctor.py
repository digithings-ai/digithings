"""Doctor reports tools and the ggml-base.en model file."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.doctor import doctor_checks, render_doctor
from digivoice.models import DoctorReport
from digivoice.paths import resolve_paths
from digivoice.rewrite import LOCAL_REWRITE_MODEL_FILE

from tests.dvo.fakes import FakeProbe

pytestmark = pytest.mark.unit

HOME = Path("/Users/chris")
MODELS = "/Users/chris/Library/Application Support/digivoice/models"
MODEL = f"{MODELS}/ggml-base.en.bin"
PIPER_HOME = "/Users/chris/.local/bin/piper"


def _check(report: DoctorReport, check_id: str) -> str:
    found = next(item for item in report.checks if item.id == check_id)
    return f"{found.status} {found.detail}"


def _ready() -> FakeProbe:
    return FakeProbe(
        commands={
            "whisper-cli": "/opt/homebrew/bin/whisper-cli",
            "piper": "/opt/homebrew/bin/piper",
            "sox": "/opt/homebrew/bin/sox",
            "ffmpeg": "/opt/homebrew/bin/ffmpeg",
        },
        directories={MODELS},
        files={MODEL},
    )


def _report(probe: FakeProbe) -> DoctorReport:
    return render_doctor(doctor_checks("darwin", HOME, {}, probe))


def test_whisper_cpp_without_whisper_cli_is_ready() -> None:
    report = _report(
        FakeProbe(
            commands={
                "whisper-cpp": "/opt/homebrew/bin/whisper-cpp",
                "piper": "/opt/homebrew/bin/piper",
                "sox": "/opt/homebrew/bin/sox",
            },
            directories={MODELS},
            files={MODEL},
        )
    )
    detail = _check(report, "whisper-cli")
    assert detail.startswith("ok ")
    assert "/opt/homebrew/bin/whisper-cpp" in detail
    assert report.ok is True


def test_ready_when_default_model_and_tools_exist() -> None:
    report = _report(_ready())
    assert report.ok is True
    assert "result: ok" in report.text
    assert _check(report, "models").startswith("ok ")
    assert "ggml-base.en" in _check(report, "models")
    assert MODEL in _check(report, "models")


def test_ffmpeg_satisfies_capture_and_home_piper() -> None:
    report = _report(
        FakeProbe(
            commands={
                "whisper-cli": "/usr/bin/whisper-cli",
                "ffmpeg": "/usr/bin/ffmpeg",
            },
            executables={PIPER_HOME},
            directories={MODELS},
            files={MODEL},
        )
    )
    assert "missing" in _check(report, "sox")
    assert PIPER_HOME in _check(report, "piper")
    assert _check(report, "capture").startswith("ok ")
    assert report.ok is True


def test_missing_model_directory_names_both_platforms() -> None:
    report = _report(FakeProbe(commands={"whisper-cli": "/usr/bin/whisper-cli"}))
    assert report.ok is False
    assert "result: not ready" in report.text
    assert MODELS in _check(report, "models")
    assert "ggml-base.en" in _check(report, "models")
    paths = _check(report, "paths")
    assert "/Users/chris/Library/Application Support/digivoice/models" in paths
    assert "/Users/chris/.local/share/digivoice/models" in paths
    assert "/Users/chris/Library/Application Support/digivoice/recordings" in paths
    assert "history.jsonl" in _check(report, "history")
    assert _check(report, "tcc").startswith("info ")


def test_empty_models_dir_still_wants_ggml_base_en() -> None:
    report = _report(FakeProbe(directories={MODELS}))
    detail = _check(report, "models")
    assert detail.startswith("missing ")
    assert "ggml-base.en" in detail
    assert MODEL in detail


def test_rewrite_and_interrupt_are_informational_when_disabled() -> None:
    report = _report(_ready())
    assert report.ok is True
    assert "rewrite" in report.text
    assert "disabled" in _check(report, "rewrite")
    assert "interrupt" in report.text
    assert "paste + start a new take" in _check(report, "interrupt")
    assert "digivoice cancel" in _check(report, "interrupt")


def test_doctor_documents_missing_local_rewrite_model(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    probe = FakeProbe(
        commands={
            "whisper-cli": "/usr/bin/whisper-cli",
            "piper": "/usr/bin/piper",
            "sox": "/usr/bin/sox",
        },
        directories={paths.models_dir},
        files={f"{paths.models_dir}/ggml-base.en.bin"},
    )
    report = render_doctor(
        doctor_checks("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)}, probe)
    )
    detail = next(c for c in report.checks if c.id == "rewrite").detail
    assert LOCAL_REWRITE_MODEL_FILE in detail
    assert "missing" in detail.casefold() or "not installed" in detail.casefold()
    assert "openrouter" not in detail.casefold()


def test_detection_check_is_info_and_never_blocks_ok(tmp_path: Path) -> None:
    from digivoice.settings import VoiceSettings, save_settings

    report = _report(_ready())
    assert report.ok is True
    found = next(item for item in report.checks if item.id == "detection")
    assert found.status == "info"
    assert "word_detection=false" in found.detail

    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    env = {"DIGIVOICE_DATA_DIR": str(tmp_path)}
    save_settings(paths, VoiceSettings(word_detection=True))
    probe = FakeProbe(
        commands={
            "whisper-cli": "/usr/bin/whisper-cli",
            "piper": "/usr/bin/piper",
            "sox": "/usr/bin/sox",
        },
        directories={paths.models_dir},
        files={f"{paths.models_dir}/ggml-base.en.bin"},
    )
    enabled = render_doctor(doctor_checks("linux", tmp_path, env, probe))
    assert enabled.ok is True
    detail = next(item for item in enabled.checks if item.id == "detection").detail
    assert "word_detection=true" in detail
    assert "whisper" in detail
