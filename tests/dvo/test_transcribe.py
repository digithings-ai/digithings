"""whisper-cli transcription: binary lookup, argv shape, and transcript cleaning."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.errors import TranscribeError
from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL_FILE, resolve_paths
from digivoice.probe import real_probe
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
    assert real_probe(None).lookup("whisper-cli") is None


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
