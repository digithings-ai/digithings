"""whisper-cli transcription: binary lookup, argv shape, and transcript cleaning."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.errors import EmptyTranscriptError, TranscribeError
from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL_FILE, resolve_paths
from digivoice.probe import real_probe
from digivoice.settings import VoiceSettings, save_settings
from digivoice.transcribe import (
    LANGUAGE,
    clean_transcript,
    model_file,
    select_whisper,
    transcribe,
    whisper_argv,
)

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit

WHISPER = FakeProbe(commands={"whisper-cli": "/usr/bin/whisper-cli"})


@pytest.fixture
def paths(tmp_path: Path) -> VoicePaths:
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def _install_model(paths: VoicePaths) -> Path:
    model = model_file(paths)
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"fake weights")
    return model


def test_argv_passes_the_model_file_and_the_wav() -> None:
    argv = whisper_argv("/usr/bin/whisper-cli", Path("/m/ggml-base.en.bin"), Path("/tmp/a.wav"))
    assert argv[0] == "/usr/bin/whisper-cli"
    assert argv[argv.index("-m") + 1] == "/m/ggml-base.en.bin"
    assert argv[argv.index("-f") + 1] == "/tmp/a.wav"
    assert argv[argv.index("-l") + 1] == LANGUAGE
    assert "-nt" in argv


def test_whisper_cli_is_preferred_and_whisper_cpp_is_accepted() -> None:
    both = FakeProbe(commands={"whisper-cli": "/a/whisper-cli", "whisper-cpp": "/b/whisper-cpp"})
    assert select_whisper(both) == "/a/whisper-cli"
    assert select_whisper(FakeProbe(commands={"whisper-cpp": "/b/whisper-cpp"})) == "/b/whisper-cpp"
    assert select_whisper(FakeProbe()) is None


def test_a_fake_whisper_in_a_path_dir_is_found_with_no_override(tmp_path: Path) -> None:
    binary = tmp_path / "whisper-cli"
    binary.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    binary.chmod(0o755)
    assert real_probe(str(tmp_path)).lookup("whisper-cli") == str(binary)
    # No PATH and no fallback dirs: nothing to find.
    assert real_probe(None, fallback_dirs=()).lookup("whisper-cli") is None


def test_clean_transcript_drops_segment_timestamps() -> None:
    raw = "[00:00:00.000 --> 00:00:01.500]   ship it.\n[00:00:01.500 --> 00:00:03.000]   now.\n"
    assert clean_transcript(raw) == "ship it. now."


def test_clean_transcript_collapses_plain_lines() -> None:
    assert clean_transcript("\n  hello   there \n\n") == "hello there"


def test_transcribe_returns_the_cleaned_text(paths: VoicePaths) -> None:
    model = _install_model(paths)
    runner = FakeRunner(
        {"whisper-cli": FakeReply(stdout="[00:00:00.000 --> 00:00:01.000]   ship it.\n")}
    )
    result = transcribe(paths, WHISPER, runner, "/tmp/a.wav")
    assert result.text == "ship it."
    assert result.model == "ggml-base.en"
    assert result.model_path == str(model)
    assert result.wav_path == "/tmp/a.wav"
    assert runner.call_for("whisper-cli") is not None


def test_transcribe_without_whisper_fails_soft(paths: VoicePaths) -> None:
    with pytest.raises(TranscribeError) as excinfo:
        transcribe(paths, FakeProbe(), FakeRunner(), "/tmp/a.wav")
    assert "whisper-cli" in str(excinfo.value)


def test_transcribe_without_the_model_file_names_it(paths: VoicePaths) -> None:
    with pytest.raises(TranscribeError) as excinfo:
        transcribe(paths, WHISPER, FakeRunner(), "/tmp/a.wav")
    assert DEFAULT_MODEL_FILE in str(excinfo.value)
    assert "ggml-base.en" in str(excinfo.value)


def test_transcribe_reports_a_whisper_failure(paths: VoicePaths) -> None:
    _install_model(paths)
    runner = FakeRunner({"whisper-cli": FakeReply(code=1, stderr="error: failed to open wav")})
    with pytest.raises(TranscribeError) as excinfo:
        transcribe(paths, WHISPER, runner, "/tmp/a.wav")
    assert "failed to open wav" in str(excinfo.value)


def test_silence_is_an_error_not_an_empty_history_entry(paths: VoicePaths) -> None:
    _install_model(paths)
    runner = FakeRunner({"whisper-cli": FakeReply(stdout="\n \n")})
    with pytest.raises(TranscribeError) as excinfo:
        transcribe(paths, WHISPER, runner, "/tmp/a.wav")
    assert "no text" in str(excinfo.value)


@pytest.mark.parametrize(
    "raw",
    ["[BLANK_AUDIO]", " [ Silence ] \n", "(silence)", "[BLANK_AUDIO]\n[BLANK_AUDIO]"],
)
def test_silence_markers_are_an_empty_take(paths: VoicePaths, raw: str) -> None:
    _install_model(paths)
    runner = FakeRunner({"whisper-cli": FakeReply(stdout=raw)})
    with pytest.raises(EmptyTranscriptError):
        transcribe(paths, WHISPER, runner, "/tmp/a.wav")


def test_silence_marker_next_to_speech_is_dropped() -> None:
    assert clean_transcript("[BLANK_AUDIO] ship it. [ Silence ]") == "ship it."


def test_transcribe_opens_a_catalog_copy_under_an_install_root(
    paths: VoicePaths, tmp_path: Path
) -> None:
    weight = tmp_path / ".lmstudio" / "models" / "whisper" / "ggml-small.en.bin"
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b"fake weights")
    runner = FakeRunner({"whisper-cli": FakeReply(stdout="ship the notes\n")})
    result = transcribe(
        paths,
        WHISPER,
        runner,
        "/tmp/a.wav",
        model_id="ggml-small.en",
        home=tmp_path,
        env={},
    )
    assert result.text == "ship the notes"
    assert result.model_path == str(weight)
    call = runner.call_for("whisper-cli")
    assert call is not None
    assert call.argv[call.argv.index("-m") + 1] == str(weight)
    assert call.argv[call.argv.index("-l") + 1] == "en"


def test_absolute_model_id_is_that_file_not_the_models_dir(
    paths: VoicePaths, tmp_path: Path
) -> None:
    """A selected absolute path is the file itself, even when models_dir has the same name."""
    weight = tmp_path / "Library" / "Models" / "ggml-small.en"
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b"installed weights")
    models = Path(paths.models_dir)
    models.mkdir(parents=True)
    decoy = models / "ggml-small.en.bin"
    decoy.write_bytes(b"not this copy")
    found = model_file(paths, str(weight), home=tmp_path, env={})
    assert found == weight
    assert found != decoy


def test_transcribe_opens_a_catalog_copy_under_mlx(paths: VoicePaths, tmp_path: Path) -> None:
    weight = tmp_path / ".mlxstudio" / "models" / "whisper" / "GGML-small.en.bin"
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b"mlx weights")
    runner = FakeRunner({"whisper-cli": FakeReply(stdout="ship the notes\n")})
    result = transcribe(
        paths,
        WHISPER,
        runner,
        "/tmp/a.wav",
        model_id="ggml-small.en",
        home=tmp_path,
        env={},
    )
    assert result.model_path == str(weight)
    call = runner.call_for("whisper-cli")
    assert call is not None
    assert call.argv[call.argv.index("-m") + 1] == str(weight)


def test_transcribe_keeps_a_missing_absolute_bin(paths: VoicePaths, tmp_path: Path) -> None:
    missing = tmp_path / "gone.bin"
    decoy = tmp_path / ".ollama" / "models" / "gone.bin"
    decoy.parent.mkdir(parents=True)
    decoy.write_bytes(b"not this one")
    with pytest.raises(TranscribeError, match="not installed locally") as excinfo:
        transcribe(
            paths,
            WHISPER,
            FakeRunner(),
            "/tmp/a.wav",
            model_id=str(missing),
            home=tmp_path,
        )
    assert str(missing) in str(excinfo.value)
    assert str(decoy) not in str(excinfo.value)


def test_transcribe_runs_the_saved_stt_model_not_the_default(paths: VoicePaths) -> None:
    models = Path(paths.models_dir)
    models.mkdir(parents=True, exist_ok=True)
    saved = models / "ggml-small.en.bin"
    saved.write_bytes(b"small weights")
    default = models / DEFAULT_MODEL_FILE
    default.write_bytes(b"default weights")
    save_settings(paths, VoiceSettings(stt_model="ggml-small.en"))
    runner = FakeRunner({"whisper-cli": FakeReply(stdout="ship the notes\n")})
    result = transcribe(paths, WHISPER, runner, "/tmp/a.wav")
    assert result.model == "ggml-small.en"
    assert result.model_path == str(saved)
    call = runner.call_for("whisper-cli")
    assert call is not None
    assert call.argv[call.argv.index("-m") + 1] == str(saved)
    assert str(default) not in call.argv


def test_transcribe_uses_configured_stt_model(paths: VoicePaths) -> None:
    models = Path(paths.models_dir)
    models.mkdir(parents=True, exist_ok=True)
    tiny = models / "ggml-tiny.bin"
    tiny.write_bytes(b"fake weights")
    runner = FakeRunner({"whisper-cli": FakeReply(stdout="hola mundo\n")})
    result = transcribe(paths, WHISPER, runner, "/tmp/a.wav", model_id="ggml-tiny")
    assert result.text == "hola mundo"
    assert result.model == "ggml-tiny"
    assert result.model_path == str(tiny)
    call = runner.call_for("whisper-cli")
    assert call is not None
    argv = call.argv
    assert argv[argv.index("-m") + 1] == str(tiny)
    assert argv[argv.index("-l") + 1] == "auto"
