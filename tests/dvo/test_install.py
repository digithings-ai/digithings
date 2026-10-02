"""digivoice install uses injected fetch and runner. No network and no real install."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from digivoice.catalog import find_stt
from digivoice.cli import Runtime, run
from digivoice.install import (
    bun_archive_url,
    piper_archive_url,
    run_install,
    voice_urls,
    whisper_archive_url,
)
from digivoice.models import InstallReport, InstallStep
from digivoice.paths import DEFAULT_MODEL_FILE

from tests.dvo.fakes import FakeCall, FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit

STT_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
VOICE_ONNX = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx"
)
VOICE_JSON = VOICE_ONNX + ".json"
BUN_LINUX = "https://github.com/oven-sh/bun/releases/download/bun-v1.4.2/bun-linux-aarch64.zip"
WHISPER_LINUX = (
    "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/"
    "whisper-bin-ubuntu-arm64.tar.gz"
)
PIPER_LINUX = (
    "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz"
)
BUN_DARWIN = "https://github.com/oven-sh/bun/releases/download/bun-v1.4.2/bun-darwin-aarch64.zip"
PIPER_DARWIN = (
    "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_aarch64.tar.gz"
)


def _tar(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _linux_bodies() -> dict[str, bytes]:
    return {
        BUN_LINUX: _zip({"bun-linux-aarch64/bun": b"bun"}),
        WHISPER_LINUX: _tar(
            {
                "whisper-bin-ubuntu-arm64/whisper-cli": b"whisper",
                "whisper-bin-ubuntu-arm64/libggml.so": b"lib",
            }
        ),
        PIPER_LINUX: _tar(
            {
                "piper/piper": b"piper",
                "piper/espeak-ng-data/phontab": b"data",
            }
        ),
        STT_URL: b"ggml-base",
        VOICE_ONNX: b"onnx",
        VOICE_JSON: b"{}",
    }


def _tui(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text('{"name":"digivoice-tui"}\n', encoding="utf-8")
    return path


def _runner(tui: Path) -> FakeRunner:
    def install_opentui(call: FakeCall) -> FakeReply:
        cwd = Path(call.argv[call.argv.index("--cwd") + 1])
        assert cwd == tui
        (cwd / "node_modules" / "@opentui" / "core").mkdir(parents=True)
        return FakeReply()

    return FakeRunner({"bun": install_opentui})


def _install(
    home: Path,
    tui: Path,
    *,
    platform: str,
    machine: str,
    bodies: dict[str, bytes],
    probe: FakeProbe | None = None,
    runner: FakeRunner | None = None,
    fail_urls: set[str] | None = None,
) -> tuple[InstallReport, list[str]]:
    fetched: list[str] = []
    blocked = fail_urls or set()

    def fetch(url: str, dest: Path) -> None:
        fetched.append(url)
        if url in blocked:
            raise OSError(f"blocked {url}")
        if url not in bodies:
            raise AssertionError(f"unexpected fetch {url}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bodies[url])

    report = run_install(
        home=home,
        platform=platform,
        machine=machine,
        probe=probe or FakeProbe(),
        runner=runner or _runner(tui),
        models_dir=home / "models",
        tui_root=tui,
        fetch=fetch,
    )
    return report, fetched


def _step(report: InstallReport, step_id: str) -> InstallStep:
    return next(step for step in report.steps if step.id == step_id)


def test_archive_urls_follow_the_host() -> None:
    assert bun_archive_url("linux", "aarch64") == BUN_LINUX
    assert bun_archive_url("linux", "x86_64").endswith("/bun-linux-x64.zip")
    assert bun_archive_url("darwin", "arm64") == BUN_DARWIN
    assert bun_archive_url("darwin", "x86_64").endswith("/bun-darwin-x64.zip")
    assert whisper_archive_url("linux", "aarch64") == WHISPER_LINUX
    whisper_x64 = whisper_archive_url("linux", "x86_64")
    assert whisper_x64 is not None
    assert whisper_x64.endswith("/whisper-bin-ubuntu-x64.tar.gz")
    assert whisper_archive_url("darwin", "arm64") is None
    assert piper_archive_url("linux", "aarch64") == PIPER_LINUX
    assert piper_archive_url("linux", "x86_64").endswith("/piper_linux_x86_64.tar.gz")
    assert piper_archive_url("darwin", "arm64") == PIPER_DARWIN
    assert piper_archive_url("darwin", "x86_64").endswith("/piper_macos_x64.tar.gz")
    assert voice_urls() == (VOICE_ONNX, VOICE_JSON)
    entry = find_stt("ggml-base.en")
    assert entry is not None
    assert entry.url == STT_URL


def _block_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("network")


def test_linux_install_fetches_the_local_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.install.urlopen", _block_network)
    tui = _tui(tmp_path / "tui")
    report, fetched = _install(
        tmp_path / "home",
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
    )
    assert report.ok
    assert fetched == [BUN_LINUX, WHISPER_LINUX, PIPER_LINUX, STT_URL, VOICE_ONNX, VOICE_JSON]
    assert all("gguf" not in url.casefold() and "otter" not in url.casefold() for url in fetched)
    home = tmp_path / "home"
    whisper = home / ".local" / "bin" / "whisper-cli"
    piper = home / ".local" / "bin" / "piper"
    assert whisper.is_symlink()
    assert whisper.resolve().read_bytes() == b"whisper"
    assert whisper.resolve().parent.joinpath("libggml.so").is_file()
    assert piper.is_symlink()
    assert piper.resolve().parent.joinpath("espeak-ng-data", "phontab").is_file()
    assert (home / ".local" / "bin" / "bun").is_symlink()
    assert (home / "models" / DEFAULT_MODEL_FILE).read_bytes() == b"ggml-base"
    assert (home / "models" / "en_US-lessac-medium.onnx.json").read_bytes() == b"{}"
    assert (tui / "node_modules" / "@opentui" / "core").is_dir()
    assert _step(report, "sox").status == "present"


def test_macos_without_a_cli_tarball_uses_brew(tmp_path: Path) -> None:
    tui = _tui(tmp_path / "tui")
    bodies = {
        BUN_DARWIN: _zip({"bun-darwin-aarch64/bun": b"bun"}),
        PIPER_DARWIN: _tar({"piper/piper": b"piper", "piper/espeak-ng-data/phontab": b"data"}),
        STT_URL: b"ggml-base",
        VOICE_ONNX: b"onnx",
        VOICE_JSON: b"{}",
    }
    report, fetched = _install(
        tmp_path / "home",
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
    )
    assert report.ok
    assert WHISPER_LINUX not in fetched
    assert fetched == [BUN_DARWIN, PIPER_DARWIN, STT_URL, VOICE_ONNX, VOICE_JSON]
    assert _step(report, "whisper-cli").detail == "brew install whisper-cpp"
    assert _step(report, "sox").detail == "brew install sox"


def test_missing_homebrew_fails_those_steps_and_keeps_going(tmp_path: Path) -> None:
    tui = _tui(tmp_path / "tui")
    bodies = {
        BUN_DARWIN: _zip({"bun-darwin-aarch64/bun": b"bun"}),
        PIPER_DARWIN: _tar({"piper/piper": b"piper"}),
        STT_URL: b"ggml-base",
        VOICE_ONNX: b"onnx",
        VOICE_JSON: b"{}",
    }
    report, _fetched = _install(
        tmp_path / "home",
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
    )
    assert not report.ok
    assert "Homebrew" in _step(report, "whisper-cli").detail
    assert "Homebrew" in _step(report, "sox").detail
    assert _step(report, "stt").status == "installed"
    assert _step(report, "bun").status == "installed"


def test_a_failed_download_does_not_stop_the_other_steps(tmp_path: Path) -> None:
    tui = _tui(tmp_path / "tui")
    report, fetched = _install(
        tmp_path / "home",
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        fail_urls={VOICE_ONNX},
    )
    assert not report.ok
    assert _step(report, "voice").status == "failed"
    assert "Homebrew" in _step(report, "sox").detail
    assert _step(report, "stt").status == "installed"
    assert _step(report, "whisper-cli").status == "installed"
    assert VOICE_JSON not in fetched


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    tui = _tui(tmp_path / "tui")
    bodies = _linux_bodies()
    bodies[BUN_LINUX] = _zip({"../escaped": b"nope"})
    report, _fetched = _install(
        tmp_path / "home",
        tui,
        platform="linux",
        machine="aarch64",
        bodies=bodies,
    )
    assert _step(report, "bun").status == "failed"
    assert "escapes" in _step(report, "bun").detail
    assert _step(report, "piper").status == "installed"
    assert list(tmp_path.rglob("escaped")) == []


def test_present_tools_are_not_fetched_again(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True)
    for name in ("bun", "whisper-cli", "piper"):
        binary = bindir / name
        binary.write_bytes(b"#!/bin/sh\n")
        binary.chmod(0o755)
    models = home / "models"
    models.mkdir()
    (models / DEFAULT_MODEL_FILE).write_bytes(b"ggml")
    (models / "en_US-lessac-medium.onnx").write_bytes(b"onnx")
    (models / "en_US-lessac-medium.onnx.json").write_bytes(b"{}")
    tui = _tui(tmp_path / "tui")
    (tui / "node_modules" / "@opentui" / "core").mkdir(parents=True)
    report, fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies={},
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
    )
    assert report.ok
    assert fetched == []
    assert {step.status for step in report.steps} == {"present"}


def test_cli_install_uses_the_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_run_install(**kwargs: object) -> InstallReport:
        seen.update(kwargs)
        return InstallReport(
            steps=[InstallStep(id="stt", status="installed", detail=str(tmp_path / "model"))]
        )

    monkeypatch.setattr("digivoice.cli.run_install", fake_run_install)
    result = run(
        ["install"],
        Runtime(platform="linux", home=tmp_path, env={}, probe=FakeProbe(), runner=FakeRunner()),
    )
    assert result.code == 0
    assert "stt" in result.stdout
    assert "installed" in result.stdout
    assert seen["home"] == tmp_path
    assert seen["platform"] == "linux"
    assert seen["machine"]
    assert "fetch" not in seen


def test_cli_install_exits_1_when_a_step_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "digivoice.cli.run_install",
        lambda **kwargs: InstallReport(
            steps=[InstallStep(id="sox", status="failed", detail="Homebrew is not available")]
        ),
    )
    result = run(
        ["install"],
        Runtime(platform="darwin", home=tmp_path, env={}, probe=FakeProbe()),
    )
    assert result.code == 1
    assert "one or more steps failed" in result.stdout
    assert "Homebrew" in result.stdout
