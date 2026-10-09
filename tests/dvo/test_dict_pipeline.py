"""Full dictation path: capture → STT → post-process hooks → clipboard/paste.

No live microphone, whisper weights, or Mac UI. Fakes cover sox/ffmpeg,
whisper-cli/whisper-cpp, local rewrite, pbcopy, and osascript.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.paths import resolve_paths
from digivoice.rewrite import PRESET_PROMPTS
from digivoice.settings import VoiceSettings, save_settings
from digivoice.status import read_status

from tests.dvo.fakes import FakeCall, FakeProbe, FakeReply, FakeRunner, writes_wav

pytestmark = pytest.mark.unit

RAW = "hey ship the release notes tomorrow please"
REWRITE = "Ship the release notes tomorrow."
DARWIN = {"pbcopy": "/usr/bin/pbcopy", "osascript": "/usr/bin/osascript"}


class FakeRewrite:
    name = "fake"

    def __init__(self, text: str = REWRITE) -> None:
        self._text = text
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return True

    def rewrite(self, system: str, user: str, *, timeout: float) -> str:
        self.calls.append((system, user))
        return self._text


def _install_model(tmp_path: Path, name: str = "ggml-base.en.bin") -> Path:
    models = tmp_path / "models"
    models.mkdir(parents=True, exist_ok=True)
    target = models / name
    target.write_bytes(b"fake weights")
    return target


def _runtime(
    tmp_path: Path,
    runner: FakeRunner,
    *,
    rewrite_runner: FakeRewrite | None = None,
    extra_commands: dict[str, str] | None = None,
) -> Runtime:
    commands = {
        "sox": "/usr/bin/sox",
        "whisper-cli": "/usr/bin/whisper-cli",
        **DARWIN,
        **(extra_commands or {}),
    }
    return Runtime(
        platform="darwin",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands=commands),
        runner=runner,
        rewrite_runner=rewrite_runner,
    )


def test_coding_preset_is_the_local_agent_hook() -> None:
    """Post-STT coding preset is the in-pipeline hook for CLI/IDE agents."""
    prompt = PRESET_PROMPTS["coding"].casefold()
    assert "coding agent" in prompt
    assert "cli" in prompt
    assert "no preamble" in prompt
    assert "cloud" not in prompt
    assert "openai" not in prompt


def test_dict_path_records_rewrites_pastes_and_logs(tmp_path: Path) -> None:
    """Hammerspoon-equivalent happy path: STT → rewrite → pbcopy stdin → Cmd+V → history."""
    _install_model(tmp_path)
    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(paths, VoiceSettings(rewrite_enabled=True, rewrite_preset="coding"))
    fake = FakeRewrite(REWRITE)
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=f"[00:00:00.000 --> 00:00:01.000]   {RAW}\n"),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--toggle"], _runtime(tmp_path, runner, rewrite_runner=fake))
    assert result.code == 0
    assert result.stdout == f"{REWRITE}\n"
    assert result.stdout.strip() not in {RAW, ""}
    assert runner.programs == ["sox", "whisper-cli", "pbcopy", "osascript"]
    copied, typed = runner.calls[-2], runner.calls[-1]
    assert copied.program == "pbcopy"
    assert copied.stdin == REWRITE
    assert copied.argv == ["/usr/bin/pbcopy"]
    assert typed.argv == [
        "/usr/bin/osascript",
        "-e",
        'tell application "System Events" to keystroke "v" using command down',
    ]
    assert REWRITE not in typed.argv[-1]
    assert fake.calls and RAW in fake.calls[0][1]
    assert "coding agent" in fake.calls[0][0].casefold()
    entry = json.loads((tmp_path / "history.jsonl").read_text(encoding="utf-8"))
    assert entry["kind"] == "dict"
    assert entry["text"] == REWRITE
    assert Path(entry["wav"]).is_file()
    snapshot = read_status(tmp_path / "status.json")
    assert snapshot is not None
    assert (snapshot.kind, snapshot.state, snapshot.text) == ("dict", "done", REWRITE)
    assert "pasted" in snapshot.detail
    listed = run(["history", "--json", "--last", "1"], _runtime(tmp_path, FakeRunner()))
    payload = json.loads(listed.stdout)
    assert payload["entries"][0]["text"] == REWRITE


def test_dict_uses_settings_stt_model_not_the_hardcoded_default(tmp_path: Path) -> None:
    """select-dictation: setup/settings stt_model must be the whisper -m file."""
    _install_model(tmp_path, "ggml-small.en.bin")
    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(paths, VoiceSettings(stt_model="ggml-small.en"))
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout="ship it.\n"),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold", "--no-rewrite"], _runtime(tmp_path, runner))
    assert result.code == 0
    whisper = runner.call_for("whisper-cli")
    assert whisper is not None
    model_arg = whisper.argv[whisper.argv.index("-m") + 1]
    assert model_arg.endswith("ggml-small.en.bin")
    assert "ggml-base.en.bin" not in whisper.argv
    assert "ggml-small.en" in result.stderr


def test_dict_honors_paste_on_stop_false(tmp_path: Path) -> None:
    _install_model(tmp_path)
    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(paths, VoiceSettings(paste_on_stop=False))
    runner = FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout="ship it.\n")})
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == 0
    assert result.stdout == "ship it.\n"
    assert "paste_on_stop=false" in result.stderr
    assert runner.programs == ["sox", "whisper-cli"]
    assert (
        json.loads((tmp_path / "history.jsonl").read_text(encoding="utf-8"))["text"] == "ship it."
    )


def test_dict_auto_routes_rewrite_from_the_focused_app(tmp_path: Path) -> None:
    _install_model(tmp_path)
    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(
        paths,
        VoiceSettings(rewrite_enabled=True, rewrite_auto_route=True, rewrite_preset="none"),
    )
    fake = FakeRewrite("Dear team,\n\nPlease ship the notes.\n")
    osascript_replies = iter(
        [
            FakeReply(stdout="Mail\n"),  # focused-app probe for auto-route
            FakeReply(),  # Cmd+V
        ]
    )

    def osascript(_call: FakeCall) -> FakeReply:
        return next(osascript_replies)

    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=RAW),
            "osascript": osascript,
            "pbcopy": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner, rewrite_runner=fake))
    assert result.code == 0
    assert result.stdout.startswith("Dear team")
    assert fake.calls
    assert "professional email" in fake.calls[0][0].casefold()
    assert runner.programs.count("osascript") == 2


def test_dict_accepts_whisper_cpp_alias(tmp_path: Path) -> None:
    _install_model(tmp_path)
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cpp": FakeReply(stdout="from the alias.\n"),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    runtime = Runtime(
        platform="darwin",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(
            commands={
                "sox": "/usr/bin/sox",
                "whisper-cpp": "/usr/bin/whisper-cpp",
                **DARWIN,
            }
        ),
        runner=runner,
    )
    result = run(["dict", "--hold", "--no-paste"], runtime)
    assert result.code == 0
    assert result.stdout == "from the alias.\n"
    assert runner.programs == ["sox", "whisper-cpp"]


def test_dict_ffmpeg_capture_still_pastes(tmp_path: Path) -> None:
    _install_model(tmp_path)
    runner = FakeRunner(
        {
            "ffmpeg": writes_wav(),
            "whisper-cli": FakeReply(stdout="via ffmpeg.\n"),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    runtime = Runtime(
        platform="darwin",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(
            commands={
                "ffmpeg": "/usr/bin/ffmpeg",
                "whisper-cli": "/usr/bin/whisper-cli",
                **DARWIN,
            }
        ),
        runner=runner,
    )
    result = run(["dict", "--hold"], runtime)
    assert result.code == 0
    assert result.stdout == "via ffmpeg.\n"
    assert runner.programs[0] == "ffmpeg"
    assert runner.call_for("pbcopy") is not None
    assert runner.call_for("pbcopy").stdin == "via ffmpeg."
