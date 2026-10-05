"""Local post-STT rewrite: presets, fail-soft, auto-route, fake runner."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.models import VoicePaths
from digivoice.paths import resolve_paths
from digivoice.rewrite import (
    preset_for_app,
    resolve_preset,
    rewrite_transcript,
)
from digivoice.settings import DEFAULT_REWRITE_APP_ROUTES, VoiceSettings, save_settings

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner, writes_wav

pytestmark = pytest.mark.unit

TRANSCRIPT = "hey ship the release notes tomorrow please"


class FakeRewrite:
    name = "fake"

    def __init__(self, text: str = "SHIP THE RELEASE NOTES TOMORROW.", fail: bool = False) -> None:
        self._text = text
        self._fail = fail
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return True

    def rewrite(self, system: str, user: str, *, timeout: float) -> str:
        self.calls.append((system, user))
        if self._fail:
            raise RuntimeError("boom")
        return self._text


def _paths(tmp_path: Path) -> VoicePaths:
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def test_preset_for_app_routes() -> None:
    routes = dict(DEFAULT_REWRITE_APP_ROUTES)
    assert preset_for_app("Mail", routes) == "email"
    assert preset_for_app("Messages", routes) == "sms"
    assert preset_for_app("Cursor", routes) == "coding"
    assert preset_for_app("iTerm2", routes) == "coding"
    assert preset_for_app("Safari", routes) == "professional"
    assert preset_for_app("Calculator", routes) is None


def test_preset_for_app_uses_settings_routes_not_hardcoded() -> None:
    custom = {"notes": "blog", "slack": "sms"}
    assert preset_for_app("Apple Notes", custom) == "blog"
    assert preset_for_app("Slack", custom) == "sms"
    assert preset_for_app("Mail", custom) is None  # defaults not applied when custom passed


def test_resolve_preset_auto_route() -> None:
    settings = VoiceSettings(rewrite_preset="blog", rewrite_auto_route=True)
    assert resolve_preset(settings, "Mail") == "email"
    assert resolve_preset(settings, None) == "blog"
    off = VoiceSettings(rewrite_preset="sms", rewrite_auto_route=False)
    assert resolve_preset(off, "Mail") == "sms"
    custom = VoiceSettings(
        rewrite_preset="none",
        rewrite_auto_route=True,
        rewrite_app_routes={"zettelkasten": "blog"},
    )
    assert resolve_preset(custom, "Zettelkasten") == "blog"
    assert resolve_preset(custom, "Mail") == "none"


def test_rewrite_disabled_returns_raw(tmp_path: Path) -> None:
    result = rewrite_transcript(
        TRANSCRIPT,
        paths=_paths(tmp_path),
        settings=VoiceSettings(rewrite_enabled=False),
        probe=FakeProbe(),
        runner=FakeRunner(),
    )
    assert result.applied is False
    assert result.text == TRANSCRIPT
    assert "disabled" in result.detail


def test_rewrite_applies_with_fake_runner(tmp_path: Path) -> None:
    fake = FakeRewrite("Polished email body.")
    result = rewrite_transcript(
        TRANSCRIPT,
        paths=_paths(tmp_path),
        settings=VoiceSettings(rewrite_enabled=True, rewrite_preset="email"),
        probe=FakeProbe(),
        runner=FakeRunner(),
        rewrite_runner=fake,
    )
    assert result.applied is True
    assert result.text == "Polished email body."
    assert result.preset == "email"
    assert fake.calls
    assert (
        "email" in fake.calls[0][0].casefold()
        or "professional email" in fake.calls[0][0].casefold()
    )


def test_rewrite_fails_soft(tmp_path: Path) -> None:
    fake = FakeRewrite(fail=True)
    result = rewrite_transcript(
        TRANSCRIPT,
        paths=_paths(tmp_path),
        settings=VoiceSettings(rewrite_enabled=True),
        probe=FakeProbe(),
        runner=FakeRunner(),
        rewrite_runner=fake,
    )
    assert result.applied is False
    assert result.text == TRANSCRIPT
    assert "failed" in result.detail


def test_rewrite_unavailable_runner_uses_raw(tmp_path: Path) -> None:
    result = rewrite_transcript(
        TRANSCRIPT,
        paths=_paths(tmp_path),
        settings=VoiceSettings(rewrite_enabled=True, rewrite_model="missing.gguf"),
        probe=FakeProbe(),
        runner=FakeRunner(),
    )
    assert result.applied is False
    assert result.text == TRANSCRIPT
    assert "unavailable" in result.detail


def test_dict_pipeline_rewrites_before_history(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"fake")
    paths = _paths(tmp_path)
    save_settings(
        paths,
        VoiceSettings(rewrite_enabled=True, rewrite_preset="sms"),
    )
    fake = FakeRewrite("ship release notes tomorrow")
    runner = FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout=TRANSCRIPT)})
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(
            commands={
                "sox": "/usr/bin/sox",
                "whisper-cli": "/usr/bin/whisper-cli",
            }
        ),
        runner=runner,
        rewrite_runner=fake,
    )
    result = run(["dict", "--hold"], runtime)
    assert result.code == 0
    assert result.stdout == "ship release notes tomorrow\n"
    assert "rewrote" in result.stderr
    entry = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert "ship release notes tomorrow" in entry


def test_dict_no_rewrite_flag(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"fake")
    paths = _paths(tmp_path)
    save_settings(paths, VoiceSettings(rewrite_enabled=True))
    fake = FakeRewrite("should not appear")
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands={"sox": "/usr/bin/sox", "whisper-cli": "/usr/bin/whisper-cli"}),
        runner=FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout=TRANSCRIPT)}),
        rewrite_runner=fake,
    )
    result = run(["dict", "--hold", "--no-rewrite"], runtime)
    assert result.code == 0
    assert result.stdout == f"{TRANSCRIPT}\n"
    assert fake.calls == []
