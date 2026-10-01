"""Piper speak: argv text, clipboard, history fallback, injected runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.errors import SpeakError
from digivoice.history import append_entry, dict_entry
from digivoice.paths import resolve_paths
from digivoice.speak import (
    piper_argv,
    play_argv,
    read_selection,
    resolve_voice,
    select_piper,
    select_player,
    speak,
)

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit

SPOKEN = "ship the release notes"


def _writes_speak_wav(reply: FakeReply | None = None):
    def _respond(call):
        wav = next(Path(part) for part in call.argv if part.endswith(".wav"))
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"RIFF0000WAVEfmt ")
        return reply or FakeReply()

    return _respond


def _speak_runtime(
    tmp_path: Path,
    *,
    platform: str = "linux",
    runner: FakeRunner | None = None,
    commands: dict[str, str] | None = None,
    env_extra: dict[str, str] | None = None,
) -> Runtime:
    models = tmp_path / "models"
    models.mkdir(parents=True, exist_ok=True)
    voice = models / "en_US-lessac-medium.onnx"
    voice.write_bytes(b"fake onnx")
    (models / "ggml-base.en.bin").write_bytes(b"fake weights")
    resolved = {
        "piper": "/usr/bin/piper",
        "aplay": "/usr/bin/aplay",
        "afplay": "/usr/bin/afplay",
        "pbpaste": "/usr/bin/pbpaste",
        "wl-paste": "/usr/bin/wl-paste",
    }
    if commands:
        resolved.update(commands)
    env = {"DIGIVOICE_DATA_DIR": str(tmp_path)}
    if env_extra:
        env.update(env_extra)
    return Runtime(
        platform=platform,
        home=tmp_path,
        env=env,
        probe=FakeProbe(
            commands=resolved,
            directories={str(models), str(tmp_path)},
            files={str(voice), str(models / "ggml-base.en.bin")},
            executables={"/home/chris/.local/bin/piper"},
        ),
        runner=runner
        or FakeRunner(
            {
                "piper": _writes_speak_wav(),
                "aplay": FakeReply(),
                "afplay": FakeReply(),
                "pbpaste": FakeReply(stdout=SPOKEN),
                "wl-paste": FakeReply(stdout=SPOKEN),
            }
        ),
    )


def test_piper_argv_pipes_model_and_wav() -> None:
    argv = piper_argv("/usr/bin/piper", Path("/v.onnx"), Path("/out.wav"))
    assert argv == ["/usr/bin/piper", "--model", "/v.onnx", "--output_file", "/out.wav"]


def test_play_argv_per_player() -> None:
    assert play_argv("afplay", "/usr/bin/afplay", Path("/a.wav")) == ["/usr/bin/afplay", "/a.wav"]
    assert play_argv("aplay", "/usr/bin/aplay", Path("/a.wav"))[0] == "/usr/bin/aplay"
    assert "-nodisp" in play_argv("ffplay", "/usr/bin/ffplay", Path("/a.wav"))


def test_select_piper_prefers_path_then_fallback() -> None:
    probe = FakeProbe(
        commands={"piper": "/opt/piper"},
        executables={str(Path("/home/chris") / ".local" / "bin" / "piper")},
    )
    assert select_piper(probe, Path("/home/chris")) == "/opt/piper"
    probe2 = FakeProbe(executables={str(Path("/home/chris") / ".local" / "bin" / "piper")})
    assert select_piper(probe2, Path("/home/chris")) == str(
        Path("/home/chris") / ".local" / "bin" / "piper"
    )


def test_resolve_voice_uses_env_then_models_dir(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    voice = models / "voice.onnx"
    voice.write_bytes(b"x")
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    probe = FakeProbe(directories={str(models)}, files={str(voice)})
    assert resolve_voice(paths, {}, probe) == voice
    other = tmp_path / "other.onnx"
    other.write_bytes(b"y")
    probe2 = FakeProbe(files={str(other)})
    assert resolve_voice(paths, {"DIGIVOICE_PIPER_VOICE": str(other)}, probe2) == other


def test_resolve_voice_missing_fails(tmp_path: Path) -> None:
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    with pytest.raises(SpeakError, match="no Piper voice"):
        resolve_voice(paths, {}, FakeProbe())


def test_select_player_darwin_and_linux() -> None:
    assert select_player("darwin", FakeProbe(commands={"afplay": "/usr/bin/afplay"})) == (
        "afplay",
        "/usr/bin/afplay",
    )
    assert select_player("linux", FakeProbe(commands={"ffplay": "/usr/bin/ffplay"})) == (
        "ffplay",
        "/usr/bin/ffplay",
    )


def test_speak_module_writes_wav_and_plays(tmp_path: Path) -> None:
    runtime = _speak_runtime(tmp_path)
    paths = resolve_paths("linux", tmp_path, runtime.env)
    result = speak(
        paths,
        runtime.probe,
        runtime.runner,  # type: ignore[arg-type]
        SPOKEN,
        platform="linux",
        home=tmp_path,
        env=runtime.env,
    )
    assert result.text == SPOKEN
    assert Path(result.wav_path).is_file()
    assert result.player == "aplay"
    assert runtime.runner.programs == ["piper", "aplay"]  # type: ignore[union-attr]
    assert runtime.runner.calls[0].stdin == SPOKEN + "\n"  # type: ignore[union-attr]


def test_cli_speak_text_appends_history(tmp_path: Path) -> None:
    runtime = _speak_runtime(tmp_path)
    result = run(["speak", "ship", "the", "release", "notes"], runtime)
    assert result.code == 0
    assert result.stdout == f"{SPOKEN}\n"
    assert "aplay" in result.stderr or "afplay" in result.stderr
    entry = json.loads((tmp_path / "history.jsonl").read_text(encoding="utf-8"))
    assert entry["kind"] == "speak"
    assert entry["text"] == SPOKEN
    assert entry["wav"] is None
    assert entry["ts"].endswith("Z")


def test_cli_speak_clipboard(tmp_path: Path) -> None:
    runtime = _speak_runtime(tmp_path, platform="darwin")
    result = run(["speak", "--clipboard"], runtime)
    assert result.code == 0
    assert result.stdout == f"{SPOKEN}\n"
    assert "pbpaste" in runtime.runner.programs  # type: ignore[union-attr]


def test_read_selection_linux_primary(tmp_path: Path) -> None:
    runner = FakeRunner({"xclip": FakeReply(stdout="selected coding reply")})
    probe = FakeProbe(commands={"xclip": "/usr/bin/xclip"})
    assert read_selection("linux", probe, runner) == "selected coding reply"
    assert runner.calls[0].argv[1:4] == ["-o", "-selection", "primary"]


def test_read_selection_linux_empty_fails_soft(tmp_path: Path) -> None:
    runner = FakeRunner({"xclip": FakeReply(stdout="")})
    probe = FakeProbe(commands={"xclip": "/usr/bin/xclip"})
    with pytest.raises(SpeakError, match="nothing selected"):
        read_selection("linux", probe, runner)


def test_read_selection_darwin_requires_clipboard_change(tmp_path: Path) -> None:
    pastes = iter(["leftover dictation", "selected coding reply"])

    def pbpaste_reply(_call):
        return FakeReply(stdout=next(pastes))

    runner = FakeRunner({"pbpaste": pbpaste_reply, "osascript": FakeReply()})
    probe = FakeProbe(commands={"pbpaste": "/usr/bin/pbpaste", "osascript": "/usr/bin/osascript"})
    assert read_selection("darwin", probe, runner) == "selected coding reply"


def test_read_selection_darwin_unchanged_clipboard_is_empty_selection(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "pbpaste": FakeReply(stdout="leftover dictation"),
            "osascript": FakeReply(),
        }
    )
    probe = FakeProbe(commands={"pbpaste": "/usr/bin/pbpaste", "osascript": "/usr/bin/osascript"})
    with pytest.raises(SpeakError, match="nothing selected"):
        read_selection("darwin", probe, runner)


def test_cli_speak_selection_success(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "piper": _writes_speak_wav(),
            "aplay": FakeReply(),
            "xclip": FakeReply(stdout="coding CLI reply"),
        }
    )
    runtime = _speak_runtime(tmp_path, runner=runner, commands={"xclip": "/usr/bin/xclip"})
    result = run(["speak", "--selection"], runtime)
    assert result.code == 0
    assert result.stdout == "coding CLI reply\n"


def test_cli_speak_selection_empty_fails_soft_no_dict_history(tmp_path: Path) -> None:
    append_entry(tmp_path / "history.jsonl", dict_entry("from dict history", None))
    runner = FakeRunner(
        {
            "piper": _writes_speak_wav(),
            "aplay": FakeReply(),
            "xclip": FakeReply(stdout=""),
        }
    )
    runtime = _speak_runtime(tmp_path, runner=runner, commands={"xclip": "/usr/bin/xclip"})
    result = run(["speak", "--selection"], runtime)
    assert result.code == 1
    assert "nothing selected" in result.stderr
    assert "from dict history" not in result.stdout
    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "dict"


def test_cli_speak_clipboard_or_history_is_clipboard_only_no_history(tmp_path: Path) -> None:
    append_entry(tmp_path / "history.jsonl", dict_entry("from dict history", None))
    runner = FakeRunner(
        {
            "piper": _writes_speak_wav(),
            "aplay": FakeReply(),
            "wl-paste": FakeReply(stdout=""),
        }
    )
    runtime = _speak_runtime(tmp_path, runner=runner)
    result = run(["speak", "--clipboard-or-history"], runtime)
    assert result.code == 1
    assert "clipboard" in result.stderr.lower() or "empty" in result.stderr.lower()
    assert "from dict history" not in result.stdout


def test_cli_speak_missing_piper_fails_soft(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "voice.onnx").write_bytes(b"x")
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(
            commands={"aplay": "/usr/bin/aplay"},
            directories={str(models)},
            files={str(models / "voice.onnx")},
        ),
        runner=FakeRunner(),
    )
    result = run(["speak", "hello"], runtime)
    assert result.code == 1
    assert "digivoice speak:" in result.stderr
    assert "piper" in result.stderr


def test_cli_speak_rejects_mixed_sources(tmp_path: Path) -> None:
    runtime = _speak_runtime(tmp_path)
    assert run(["speak", "--clipboard", "hello"], runtime).code == 2
