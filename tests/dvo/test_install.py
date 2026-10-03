"""digivoice install uses injected fetch and runner. No network and no real install."""

from __future__ import annotations

import io
import json
import struct
import tarfile
import zipfile
from pathlib import Path

import pytest
from digivoice.catalog import find_rewrite, find_stt, find_voice
from digivoice.cli import Runtime, run
from digivoice.install import (
    adapter_source_dir,
    bun_archive_url,
    hammerspoon_adapter_dir,
    piper_archive_url,
    run_install,
    run_install_wizard,
    voice_urls,
    whisper_archive_url,
)
from digivoice.models import InstallReport, InstallSelection, InstallStamp, InstallStep, VoicePaths
from digivoice.paths import DEFAULT_MODEL_FILE, vendor_dir
from digivoice.reload import reload_hammerspoon
from digivoice.settings import default_settings, load_settings, save_settings

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
    "https://github.com/dharmab/piper/releases/download/"
    "2024.12.14.1-alpha2/piper_macos_aarch64.tar.gz"
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
        assert call.argv[1] == "install"
        flag = call.argv.index("--cwd")
        assert flag > 1
        cwd = Path(call.argv[flag + 1])
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
    refresh: bool = False,
    adapter_source: Path | None = None,
    selection: InstallSelection | None = None,
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
        refresh=refresh,
        adapter_source=adapter_source,
        selection=selection,
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
    assert piper_archive_url("darwin", "aarch64") == PIPER_DARWIN
    intel = piper_archive_url("darwin", "x86_64")
    assert intel.endswith("/piper_macos_x64.tar.gz")
    assert "2023.11.14-2" in intel
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
    adapter = hammerspoon_adapter_dir(home)
    assert adapter.is_relative_to(tmp_path)
    source = adapter_source_dir()
    for name in ("init.lua", "banner_core.lua", "hotkeys.lua"):
        assert (adapter / name).read_bytes() == (source / name).read_bytes()
    installed = "\n".join(path.read_text(encoding="utf-8") for path in adapter.glob("*.lua"))
    assert "pin button" in installed
    assert "copy button" not in installed
    assert "hover" not in installed.casefold()


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


def test_missing_homebrew_fails_those_steps_and_keeps_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: ())
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
    assert "Homebrew" in _step(report, "espeak").detail
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
    assert hammerspoon_adapter_dir(home).is_relative_to(tmp_path)
    assert all(step.status == "present" for step in report.steps if step.id != "adapter")
    assert _step(report, "adapter").status == "installed"


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
    assert seen["selection"] is None


def _lua_tree(path: Path, text: str = "-- status icon only\n") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in ("init.lua", "banner_core.lua", "hotkeys.lua"):
        (path / name).write_text(text, encoding="utf-8")
    return path


def _runner_with_hs(tui: Path, hs: FakeReply | None = None) -> FakeRunner:
    runner = _runner(tui)
    runner._responses["hs"] = FakeReply() if hs is None else hs
    return runner


def test_update_refetches_only_an_outdated_pin(tmp_path: Path) -> None:
    home = tmp_path / "home"
    tui = _tui(tmp_path / "tui")
    source = _lua_tree(tmp_path / "lua")
    kwargs = {
        "platform": "linux",
        "machine": "aarch64",
        "bodies": _linux_bodies(),
        "probe": FakeProbe(commands={"sox": "/usr/bin/sox"}),
        "adapter_source": source,
    }
    report, fetched = _install(home, tui, **kwargs)
    assert report.ok
    assert fetched == [BUN_LINUX, WHISPER_LINUX, PIPER_LINUX, STT_URL, VOICE_ONNX, VOICE_JSON]
    stamp = InstallStamp.model_validate_json(
        (vendor_dir(home) / "install.json").read_text(encoding="utf-8")
    )
    assert stamp.bun == "1.4.2"
    assert "otter" not in stamp.model_dump_json().casefold()
    again, fetched_again = _install(home, tui, refresh=True, **kwargs)
    assert again.ok
    assert fetched_again == []
    assert {step.status for step in again.steps} == {"present"}
    stamp.bun = "0.0.1"
    (vendor_dir(home) / "install.json").write_text(stamp.model_dump_json(), encoding="utf-8")
    refreshed, fetched_bun = _install(home, tui, refresh=True, **kwargs)
    assert refreshed.ok
    assert fetched_bun == [BUN_LINUX]
    assert _step(refreshed, "bun").status == "installed"
    assert _step(refreshed, "whisper-cli").status == "present"
    assert _step(refreshed, "adapter").status == "present"


def test_update_upgrades_homebrew_tools_this_install_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: ())
    home = tmp_path / "home"
    tui = _tui(tmp_path / "tui")
    bodies = {
        BUN_DARWIN: _zip({"bun-darwin-aarch64/bun": b"bun"}),
        PIPER_DARWIN: _tar({"piper/piper": b"piper", "piper/espeak-ng-data/phontab": b"data"}),
        STT_URL: b"ggml-base",
        VOICE_ONNX: b"onnx",
        VOICE_JSON: b"{}",
    }
    source = _lua_tree(tmp_path / "lua")
    first, _fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        adapter_source=source,
    )
    assert _step(first, "whisper-cli").detail == "brew install whisper-cpp"
    assert _step(first, "sox").detail == "brew install sox"
    runner = _runner(tui)
    second, fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(
            commands={
                "brew": "/opt/homebrew/bin/brew",
                "whisper-cli": "/opt/homebrew/bin/whisper-cli",
                "sox": "/opt/homebrew/bin/sox",
            }
        ),
        runner=runner,
        refresh=True,
        adapter_source=source,
    )
    assert second.ok
    assert fetched == []
    brew_calls = [call.argv[1:] for call in runner.calls if call.program == "brew"]
    assert brew_calls == [
        ["upgrade", "whisper-cpp"],
        ["install", "espeak-ng"],
        ["upgrade", "sox"],
    ]


def test_unstamped_whisper_upgrade_falls_back_to_install(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True)
    for name in ("bun", "whisper-cli", "piper"):
        binary = bindir / name
        binary.write_bytes(b"#!/bin/sh\n")
        binary.chmod(0o755)
    (bindir / "libespeak-ng.1.dylib").write_bytes(b"lib")
    models = home / "models"
    models.mkdir()
    (models / DEFAULT_MODEL_FILE).write_bytes(b"ggml")
    (models / "en_US-lessac-medium.onnx").write_bytes(b"onnx")
    (models / "en_US-lessac-medium.onnx.json").write_bytes(b"{}")
    tui = _tui(tmp_path / "tui")
    (tui / "node_modules" / "@opentui" / "core").mkdir(parents=True)
    stamp = InstallStamp(
        bun="1.4.2",
        piper="2023.11.14-2",
        stt=STT_URL,
        voice=VOICE_ONNX,
    )
    stamp_path = vendor_dir(home) / "install.json"
    stamp_path.parent.mkdir(parents=True)
    stamp_path.write_text(stamp.model_dump_json(), encoding="utf-8")
    verbs: list[str] = []

    def brew(call: FakeCall) -> FakeReply:
        verbs.append(call.argv[1])
        if call.argv[1] == "upgrade":
            return FakeReply(code=1, stderr="missing")
        return FakeReply()

    report, fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies={},
        probe=FakeProbe(
            commands={
                "brew": "/opt/homebrew/bin/brew",
                "whisper-cli": str(bindir / "whisper-cli"),
                "sox": "/usr/bin/sox",
            }
        ),
        runner=FakeRunner({"brew": brew}),
        refresh=True,
        adapter_source=_lua_tree(tmp_path / "lua"),
    )
    assert fetched == []
    assert verbs == ["upgrade", "install"]
    assert _step(report, "whisper-cli").detail == "brew install whisper-cpp"
    assert _step(report, "sox").status == "present"
    assert report.ok


def test_symlink_to_the_checkout_is_left_and_reloaded(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = _lua_tree(tmp_path / "checkout")
    dest = hammerspoon_adapter_dir(home)
    dest.parent.mkdir(parents=True)
    dest.symlink_to(source)
    tui = _tui(tmp_path / "tui")
    runner = _runner_with_hs(tui)
    report, _fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox", "hs": "/usr/bin/hs"}),
        runner=runner,
        adapter_source=source,
    )
    assert report.ok
    assert dest.is_symlink()
    assert dest.resolve() == source.resolve()
    assert _step(report, "adapter").status == "present"
    assert ".hammerspoon/digivoice" in _step(report, "adapter").detail
    assert ["hs", "-c", "hs.reload()"] in [call.argv for call in runner.calls]


def test_stale_adapter_directory_drops_the_hover_controls(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = _lua_tree(tmp_path / "source", "-- status icon only\n")
    dest = hammerspoon_adapter_dir(home)
    dest.mkdir(parents=True)
    (dest / "init.lua").write_text("-- copy button\n", encoding="utf-8")
    (dest / "banner_core.lua").write_text("-- close button\n", encoding="utf-8")
    (dest / "hotkeys.lua").write_text("-- old\n", encoding="utf-8")
    (dest / "hover.lua").write_text("-- copy button\n-- X\n", encoding="utf-8")
    tui = _tui(tmp_path / "tui")
    runner = _runner_with_hs(tui)
    report, _fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox", "hs": "/usr/bin/hs"}),
        runner=runner,
        adapter_source=source,
    )
    assert report.ok
    assert not dest.is_symlink()
    assert _step(report, "adapter").status == "installed"
    assert (dest / "init.lua").read_text(encoding="utf-8") == "-- status icon only\n"
    assert not (dest / "hover.lua").exists()
    assert "copy button" not in "\n".join(
        path.read_text(encoding="utf-8") for path in dest.glob("*.lua")
    )
    assert ["hs", "-c", "hs.reload()"] in [call.argv for call in runner.calls]


def test_symlink_to_another_tree_is_replaced_not_followed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    other = _lua_tree(tmp_path / "old", "-- copy button\n")
    source = _lua_tree(tmp_path / "source", "-- status icon only\n")
    dest = hammerspoon_adapter_dir(home)
    dest.parent.mkdir(parents=True)
    dest.symlink_to(other)
    tui = _tui(tmp_path / "tui")
    report, _fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        adapter_source=source,
    )
    assert report.ok
    assert not dest.is_symlink()
    assert (dest / "init.lua").read_text(encoding="utf-8") == "-- status icon only\n"
    assert (other / "init.lua").read_text(encoding="utf-8") == "-- copy button\n"


def test_reload_failure_keeps_the_new_adapter(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = _lua_tree(tmp_path / "source")
    tui = _tui(tmp_path / "tui")
    runner = _runner_with_hs(tui, FakeReply(code=1, stderr="hs down"))
    report, _fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox", "hs": "/usr/bin/hs"}),
        runner=runner,
        adapter_source=source,
    )
    assert not report.ok
    assert _step(report, "adapter").status == "failed"
    assert "reload failed" in _step(report, "adapter").detail
    assert _step(report, "stt").status == "installed"
    assert (
        (hammerspoon_adapter_dir(home) / "init.lua")
        .read_text(encoding="utf-8")
        .startswith("-- status")
    )


def test_opentui_argv_is_package_install_not_a_script(tmp_path: Path) -> None:
    tui = _tui(tmp_path / "tui")
    package = json.loads((tui / "package.json").read_text(encoding="utf-8"))
    scripts = package.get("scripts", {})
    assert "install" not in scripts
    seen: list[list[str]] = []

    def install_opentui(call: FakeCall) -> FakeReply:
        seen.append(call.argv)
        (tui / "node_modules" / "@opentui" / "core").mkdir(parents=True)
        return FakeReply()

    report, _fetched = _install(
        tmp_path / "home",
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        runner=FakeRunner({"bun": install_opentui}),
        adapter_source=_lua_tree(tmp_path / "lua"),
    )
    assert _step(report, "opentui").status == "installed"
    argv = seen[0]
    assert argv[1] == "install"
    assert argv[2] == "--cwd"
    assert Path(argv[3]) == tui
    assert argv[-1] != "install"


def test_adapter_treats_dropped_mach_reply_as_reloaded(tmp_path: Path) -> None:
    home = tmp_path / "home"
    tui = _tui(tmp_path / "tui")
    stderr = "CFMessagePort: dropping corrupt reply Mach message\n"
    runner = _runner_with_hs(tui, FakeReply(code=1, stderr=stderr))
    report, _fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox", "hs": "/usr/bin/hs"}),
        runner=runner,
        adapter_source=_lua_tree(tmp_path / "lua"),
    )
    assert report.ok
    step = _step(report, "adapter")
    assert step.status == "installed"
    assert "hammerspoon .. reloaded" in step.detail
    assert "reload failed" not in step.detail
    assert (hammerspoon_adapter_dir(home) / "init.lua").is_file()


def test_reload_timeout_stays_a_failure_with_a_dropped_reply() -> None:
    runner = FakeRunner(
        {
            "hs": FakeReply(
                code=124,
                stderr="CFMessagePort: dropping corrupt reply Mach message",
            )
        }
    )
    message, ok = reload_hammerspoon(runner, "/usr/bin/hs")
    assert ok is False
    assert "timed out" in message


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


def test_cli_update_refreshes_the_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_run_install(**kwargs: object) -> InstallReport:
        seen.update(kwargs)
        return InstallReport(
            steps=[
                InstallStep(
                    id="adapter",
                    status="installed",
                    detail=str(tmp_path / ".hammerspoon" / "digivoice"),
                )
            ]
        )

    monkeypatch.setattr("digivoice.cli.run_install", fake_run_install)
    runtime = Runtime(
        platform="linux", home=tmp_path, env={}, probe=FakeProbe(), runner=FakeRunner()
    )
    result = run(["update"], runtime)
    assert result.code == 0
    assert seen["refresh"] is True
    assert "fetch" not in seen
    assert "selection" not in seen
    assert result.stdout.startswith("digivoice update\n")
    assert ".hammerspoon/digivoice" in result.stdout
    for path in ("/update", "/system/update"):
        seen.clear()
        followed = run([path], runtime)
        assert followed.code == 0
        assert seen["refresh"] is True
        assert ".hammerspoon/digivoice" in followed.stdout


def test_cli_update_exits_1_when_a_step_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "digivoice.cli.run_install",
        lambda **kwargs: InstallReport(
            steps=[InstallStep(id="adapter", status="failed", detail="reload failed")]
        ),
    )
    result = run(["update"], Runtime(platform="linux", home=tmp_path, env={}, probe=FakeProbe()))
    assert result.code == 1
    assert "digivoice update: one or more steps failed" in result.stdout


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _voice_paths(home: Path) -> VoicePaths:
    return VoicePaths(
        data_dir=str(home),
        models_dir=str(home / "models"),
        recordings_dir=str(home / "recordings"),
        history_file=str(home / "history.jsonl"),
    )


def test_explicit_auto_matches_the_default_install(tmp_path: Path) -> None:
    kwargs = {
        "platform": "linux",
        "machine": "aarch64",
        "bodies": _linux_bodies(),
        "probe": FakeProbe(commands={"sox": "/usr/bin/sox"}),
        "adapter_source": _lua_tree(tmp_path / "lua"),
    }
    _, fetched_default = _install(tmp_path / "default", _tui(tmp_path / "tui-default"), **kwargs)
    _, fetched_auto = _install(
        tmp_path / "auto",
        _tui(tmp_path / "tui-auto"),
        selection=InstallSelection(auto=True),
        **kwargs,
    )
    assert fetched_auto == fetched_default
    assert all(not url.casefold().endswith(".gguf") for url in fetched_auto)


def test_pick_downloads_chosen_models_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.install.urlopen", _block_network)
    home = tmp_path / "home"
    models = home / "models"
    models.mkdir(parents=True)
    (models / "ggml-tiny.en.bin").write_bytes(b"tiny-stays")
    (models / "notes.gguf").write_bytes(b"notes-stay")
    small = find_stt("ggml-small.en")
    medium = find_stt("ggml-medium.en")
    amy = find_voice("en_US-amy-medium.onnx")
    qwen = find_rewrite("qwen2.5-0.5b-instruct-q4_k_m")
    assert small is not None and medium is not None and amy is not None and qwen is not None
    bodies = _linux_bodies()
    bodies[small.url] = b"small"
    bodies[medium.url] = b"medium"
    bodies[amy.url] = b"amy"
    bodies[amy.sidecar_url] = b"{amy}"
    bodies[qwen.url] = b"qwen"
    tui = _tui(tmp_path / "tui")
    source = _lua_tree(tmp_path / "lua")
    report, fetched = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=bodies,
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        adapter_source=source,
        selection=InstallSelection(
            auto=False,
            speech=["ggml-small.en", "ggml-medium.en"],
            voice=["en_US-amy-medium.onnx"],
            rewrite=["qwen2.5-0.5b-instruct-q4_k_m"],
        ),
    )
    assert report.ok
    assert _step(report, "stt:ggml-small.en").status == "installed"
    assert (models / "ggml-tiny.en.bin").read_bytes() == b"tiny-stays"
    assert (models / "notes.gguf").read_bytes() == b"notes-stay"
    assert (models / "ggml-small.en.bin").read_bytes() == b"small"
    assert (models / "ggml-medium.en.bin").read_bytes() == b"medium"
    assert (models / "en_US-amy-medium.onnx").read_bytes() == b"amy"
    assert (models / "en_US-amy-medium.onnx.json").read_bytes() == b"{amy}"
    assert (models / qwen.filename).read_bytes() == b"qwen"
    assert not (models / DEFAULT_MODEL_FILE).exists()
    assert not (models / "en_US-lessac-medium.onnx").exists()
    assert STT_URL not in fetched
    assert VOICE_ONNX not in fetched
    assert qwen.url in fetched
    assert all("openrouter" not in url and "api.openai.com" not in url for url in fetched)
    settings = load_settings(_voice_paths(home))
    assert settings.stt_model == "ggml-small.en"
    assert settings.tts_voice == "en_US-amy-medium.onnx"
    assert settings.rewrite_model == qwen.filename
    assert settings.rewrite_enabled is False
    _refresh, fetched_again = _install(
        home,
        tui,
        platform="linux",
        machine="aarch64",
        bodies=bodies,
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        adapter_source=source,
        refresh=True,
    )
    assert fetched_again == [STT_URL, VOICE_ONNX, VOICE_JSON]
    assert (models / "ggml-tiny.en.bin").read_bytes() == b"tiny-stays"
    assert (models / "notes.gguf").read_bytes() == b"notes-stay"
    assert (models / "ggml-small.en.bin").read_bytes() == b"small"
    assert (models / qwen.filename).read_bytes() == b"qwen"
    assert (models / DEFAULT_MODEL_FILE).read_bytes() == b"ggml-base"


def test_pick_does_not_replace_a_model_already_on_disk(tmp_path: Path) -> None:
    home = tmp_path / "home"
    models = home / "models"
    models.mkdir(parents=True)
    (models / "ggml-small.en.bin").write_bytes(b"already-small")
    (models / "en_US-amy-medium.onnx").write_bytes(b"keep-onnx")
    medium = find_stt("ggml-medium.en")
    amy = find_voice("en_US-amy-medium.onnx")
    assert medium is not None and amy is not None
    bodies = _linux_bodies()
    bodies[medium.url] = b"medium"
    bodies[amy.sidecar_url] = b"{amy}"
    _report, fetched = _install(
        home,
        _tui(tmp_path / "tui"),
        platform="linux",
        machine="aarch64",
        bodies=bodies,
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        adapter_source=_lua_tree(tmp_path / "lua"),
        selection=InstallSelection(
            auto=False,
            speech=["ggml-small.en", "ggml-medium.en"],
            voice=["en_US-amy-medium.onnx"],
        ),
    )
    assert (models / "ggml-small.en.bin").read_bytes() == b"already-small"
    assert (models / "en_US-amy-medium.onnx").read_bytes() == b"keep-onnx"
    assert (models / "en_US-amy-medium.onnx.json").read_bytes() == b"{amy}"
    small = find_stt("ggml-small.en")
    assert small is not None
    assert small.url not in fetched
    assert amy.url not in fetched
    assert amy.sidecar_url in fetched
    assert medium.url in fetched
    assert _step(_report, "stt:ggml-small.en").status == "present"


def test_pick_keeps_settings_it_does_not_change(tmp_path: Path) -> None:
    home = tmp_path / "home"
    qwen = find_rewrite("qwen2.5-0.5b-instruct-q4_k_m")
    assert qwen is not None
    save_settings(
        _voice_paths(home),
        default_settings().model_copy(update={"banner_pinned": True, "rewrite_enabled": True}),
    )
    bodies = _linux_bodies()
    bodies[qwen.url] = b"qwen"
    _install(
        home,
        _tui(tmp_path / "tui"),
        platform="linux",
        machine="aarch64",
        bodies=bodies,
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        adapter_source=_lua_tree(tmp_path / "lua"),
        selection=InstallSelection(auto=False, rewrite=["qwen2.5-0.5b-instruct-q4_k_m"]),
    )
    settings = load_settings(_voice_paths(home))
    assert settings.banner_pinned is True
    assert settings.rewrite_enabled is True
    assert settings.rewrite_model == qwen.filename
    assert settings.stt_model == "ggml-base.en"
    assert settings.tts_voice is None


def test_unknown_model_fails_that_step_and_leaves_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.install.urlopen", _block_network)
    home = tmp_path / "home"
    models = home / "models"
    models.mkdir(parents=True)
    (models / "ggml-tiny.en.bin").write_bytes(b"tiny-stays")
    report, fetched = _install(
        home,
        _tui(tmp_path / "tui"),
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        adapter_source=_lua_tree(tmp_path / "lua"),
        selection=InstallSelection(auto=False, speech=["not-a-real-model"]),
    )
    assert not report.ok
    failed = _step(report, "stt:not-a-real-model")
    assert failed.status == "failed"
    assert "no local stt model" in failed.detail
    assert (models / "ggml-tiny.en.bin").read_bytes() == b"tiny-stays"
    assert _step(report, "adapter").status == "installed"
    assert STT_URL not in fetched


def test_wizard_auto_is_the_defaults(tmp_path: Path) -> None:
    out = io.StringIO()
    picked = run_install_wizard(io.StringIO("auto\n"), out, models_dir=tmp_path)
    assert picked == InstallSelection(auto=True)
    text = out.getvalue()
    assert "macOS" in text
    assert "Hammerspoon" in text
    assert "1) Auto" in text
    assert "2) Pick" in text


def test_wizard_pick_reads_speech_voice_and_rewrite(tmp_path: Path) -> None:
    (tmp_path / "ggml-tiny.en.bin").write_bytes(b"x")
    out = io.StringIO()
    picked = run_install_wizard(io.StringIO("2\n1,3\n2\n\n"), out, models_dir=tmp_path)
    assert picked is not None
    assert picked.auto is False
    assert picked.speech == ["ggml-tiny.en", "ggml-small.en"]
    assert picked.voice == ["en_US-amy-medium.onnx"]
    assert picked.rewrite == []
    text = out.getvalue()
    assert "ggml-tiny.en.bin · on disk" in text
    assert "ggml-base.en.bin · on disk" not in text
    assert "Lessac medium (default)" in text


def test_wizard_blank_or_eof_cancels(tmp_path: Path) -> None:
    assert run_install_wizard(io.StringIO("\n"), io.StringIO(), models_dir=tmp_path) is None
    assert run_install_wizard(io.StringIO("pick\n1\n"), io.StringIO(), models_dir=tmp_path) is None
    out = io.StringIO()
    picked = run_install_wizard(io.StringIO("nope\nauto\n"), out, models_dir=tmp_path)
    assert picked == InstallSelection(auto=True)
    assert "Enter 1 or auto" in out.getvalue()


def test_cli_tty_wizard_picks_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_run_install(**kwargs: object) -> InstallReport:
        seen.update(kwargs)
        return InstallReport(steps=[InstallStep(id="stt", status="present", detail="ok")])

    monkeypatch.setattr("digivoice.cli.run_install", fake_run_install)
    monkeypatch.setattr("digivoice.cli.sys.stdin", _Tty("pick\n2\n1\n1\n"))
    monkeypatch.setattr("digivoice.cli.sys.stdout", io.StringIO())
    result = run(
        ["install"],
        Runtime(platform="darwin", home=tmp_path, env={}, probe=FakeProbe(), runner=FakeRunner()),
    )
    assert result.code == 0
    selection = seen["selection"]
    assert isinstance(selection, InstallSelection)
    assert selection.auto is False
    assert selection.speech == ["ggml-base.en"]
    assert selection.voice == ["en_US-lessac-medium.onnx"]
    assert selection.rewrite == ["qwen2.5-0.5b-instruct-q4_k_m"]


def test_cli_auto_and_noninteractive_skip_the_wizard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def fake_run_install(**kwargs: object) -> InstallReport:
        seen.update(kwargs)
        return InstallReport(steps=[InstallStep(id="stt", status="installed", detail="ok")])

    monkeypatch.setattr("digivoice.cli.run_install", fake_run_install)
    stdout = io.StringIO()
    monkeypatch.setattr("digivoice.cli.sys.stdout", stdout)

    def run_install_argv(argv: list[str], env: dict[str, str]) -> None:
        seen.clear()
        monkeypatch.setattr("digivoice.cli.sys.stdin", _Tty("pick\n1\n1\n1\n"))
        result = run(
            argv,
            Runtime(
                platform="darwin",
                home=tmp_path,
                env=env,
                probe=FakeProbe(),
                runner=FakeRunner(),
            ),
        )
        assert result.code == 0
        assert seen["selection"] is None
        assert "cancelled" not in result.stdout

    run_install_argv(["install", "--auto"], {})
    run_install_argv(["install"], {"DIGIVOICE_INSTALL_NONINTERACTIVE": "1"})


def test_cli_wizard_cancel_does_not_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run_install(**kwargs: object) -> InstallReport:
        raise AssertionError("install ran")

    monkeypatch.setattr("digivoice.cli.run_install", fake_run_install)
    monkeypatch.setattr("digivoice.cli.sys.stdin", _Tty("\n"))
    monkeypatch.setattr("digivoice.cli.sys.stdout", io.StringIO())
    result = run(
        ["install"],
        Runtime(platform="darwin", home=tmp_path, env={}, probe=FakeProbe()),
    )
    assert result.code == 0
    assert result.stdout == "digivoice install: cancelled\n"


def _darwin_bodies(piper: dict[str, bytes] | None = None) -> dict[str, bytes]:
    members = piper or {
        "piper/piper": b"piper",
        "piper/espeak-ng-data/phontab": b"data",
    }
    return {
        BUN_DARWIN: _zip({"bun-darwin-aarch64/bun": b"bun"}),
        PIPER_DARWIN: _tar(members),
        STT_URL: b"ggml-base",
        VOICE_ONNX: b"onnx",
        VOICE_JSON: b"{}",
    }


def _brew_verbs(runner: FakeRunner) -> list[list[str]]:
    return [call.argv[1:] for call in runner.calls if call.program == "brew"]


def test_macos_install_brews_espeak_only_when_the_library_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: ())
    tui = _tui(tmp_path / "tui")
    runner = _runner(tui)
    report, fetched = _install(
        tmp_path / "home",
        tui,
        platform="darwin",
        machine="arm64",
        bodies=_darwin_bodies(),
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        runner=runner,
    )
    assert report.ok
    assert _step(report, "espeak").detail == "brew install espeak-ng"
    assert not any("espeak" in url for url in fetched)
    assert ["install", "espeak-ng"] in _brew_verbs(runner)
    assert ["upgrade", "espeak-ng"] not in _brew_verbs(runner)


def test_macos_install_keeps_espeak_already_on_the_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libdir = tmp_path / "homebrew" / "lib"
    libdir.mkdir(parents=True)
    library = libdir / "libespeak-ng.1.dylib"
    library.write_bytes(b"lib")
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: (libdir,))
    tui = _tui(tmp_path / "tui")
    runner = _runner(tui)
    report, _fetched = _install(
        tmp_path / "home",
        tui,
        platform="darwin",
        machine="arm64",
        bodies=_darwin_bodies(),
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        runner=runner,
    )
    assert _step(report, "espeak").status == "present"
    assert _step(report, "espeak").detail == str(library)
    assert ["install", "espeak-ng"] not in _brew_verbs(runner)
    assert ["upgrade", "espeak-ng"] not in _brew_verbs(runner)


def test_macos_install_keeps_espeak_shipped_beside_piper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: ())
    tui = _tui(tmp_path / "tui")
    runner = _runner(tui)
    report, _fetched = _install(
        tmp_path / "home",
        tui,
        platform="darwin",
        machine="arm64",
        bodies=_darwin_bodies(
            {
                "piper/piper": b"piper",
                "piper/libespeak-ng.1.dylib": b"lib",
                "piper/espeak-ng-data/phontab": b"data",
            }
        ),
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        runner=runner,
    )
    assert _step(report, "espeak").status == "present"
    assert _step(report, "espeak").detail.endswith("libespeak-ng.1.dylib")
    assert ["install", "espeak-ng"] not in _brew_verbs(runner)


def test_macos_update_upgrades_espeak_this_install_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirs: list[Path] = []
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: tuple(dirs))
    home = tmp_path / "home"
    tui = _tui(tmp_path / "tui")
    bodies = _darwin_bodies()
    source = _lua_tree(tmp_path / "lua")
    first, _fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        adapter_source=source,
    )
    assert _step(first, "espeak").detail == "brew install espeak-ng"
    libdir = tmp_path / "later" / "lib"
    libdir.mkdir(parents=True)
    (libdir / "libespeak-ng.1.dylib").write_bytes(b"lib")
    dirs.append(libdir)
    runner = _runner(tui)
    second, fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(
            commands={
                "brew": "/opt/homebrew/bin/brew",
                "whisper-cli": "/opt/homebrew/bin/whisper-cli",
                "sox": "/opt/homebrew/bin/sox",
            }
        ),
        runner=runner,
        refresh=True,
        adapter_source=source,
    )
    assert second.ok
    assert fetched == []
    assert _brew_verbs(runner) == [
        ["upgrade", "whisper-cpp"],
        ["upgrade", "espeak-ng"],
        ["upgrade", "sox"],
    ]


def _macho(cpu: str) -> bytes:
    code = {"arm64": 0x0100000C, "x86_64": 0x01000007}[cpu]
    return struct.pack("<II", 0xFEEDFACF, code)


def test_arm64_install_copies_same_arch_espeak_beside_the_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libdir = tmp_path / "homebrew" / "lib"
    libdir.mkdir(parents=True)
    library = libdir / "libespeak-ng.1.dylib"
    library.write_bytes(_macho("arm64") + b"espeak")
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: (libdir,))
    home = tmp_path / "home"
    tui = _tui(tmp_path / "tui")
    runner = _runner(tui)
    bodies = _darwin_bodies(
        {
            "piper/piper": _macho("arm64") + b"piper",
            "piper/espeak-ng-data/phontab": b"data",
        }
    )
    report, fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        runner=runner,
    )
    assert PIPER_DARWIN in fetched
    real = home / ".local" / "share" / "digivoice" / "vendor" / "piper" / "piper"
    beside = real / "libespeak-ng.1.dylib"
    assert beside.read_bytes() == library.read_bytes()
    assert _step(report, "espeak").status == "present"
    assert _step(report, "espeak").detail == str(beside)
    assert ["install", "espeak-ng"] not in _brew_verbs(runner)


def test_arm64_update_replaces_an_x86_64_vendor_piper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: ())
    home = tmp_path / "home"
    real = home / ".local" / "share" / "digivoice" / "vendor" / "piper" / "piper"
    real.mkdir(parents=True)
    binary = real / "piper"
    original = _macho("x86_64") + b"old"
    binary.write_bytes(original)
    binary.chmod(0o755)
    link = home / ".local" / "bin" / "piper"
    link.parent.mkdir(parents=True)
    link.symlink_to(binary)
    stamp = InstallStamp(piper="2023.11.14-2")
    stamp_path = vendor_dir(home) / "install.json"
    stamp_path.write_text(stamp.model_dump_json(), encoding="utf-8")
    tui = _tui(tmp_path / "tui")
    bodies = _darwin_bodies({"piper/piper": _macho("arm64") + b"new"})
    report, fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        runner=_runner(tui),
        refresh=True,
        adapter_source=_lua_tree(tmp_path / "lua"),
    )
    assert PIPER_DARWIN in fetched
    assert _step(report, "piper").status == "installed"
    installed = link.resolve().read_bytes()
    assert installed.startswith(_macho("arm64"))
    assert installed != original


def test_x86_64_archive_on_arm64_keeps_the_vendor_piper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libdir = tmp_path / "homebrew" / "lib"
    libdir.mkdir(parents=True)
    (libdir / "libespeak-ng.1.dylib").write_bytes(_macho("arm64"))
    monkeypatch.setattr("digivoice.speak.espeak_library_dirs", lambda: (libdir,))
    home = tmp_path / "home"
    real = home / ".local" / "share" / "digivoice" / "vendor" / "piper" / "piper"
    real.mkdir(parents=True)
    binary = real / "piper"
    original = _macho("x86_64") + b"keep"
    binary.write_bytes(original)
    binary.chmod(0o755)
    link = home / ".local" / "bin" / "piper"
    link.parent.mkdir(parents=True)
    link.symlink_to(binary)
    stamp_path = vendor_dir(home) / "install.json"
    stamp_path.write_text(InstallStamp(piper="2023.11.14-2").model_dump_json(), encoding="utf-8")
    tui = _tui(tmp_path / "tui")
    runner = _runner(tui)
    bodies = _darwin_bodies({"piper/piper": _macho("x86_64") + b"wrong"})
    report, _fetched = _install(
        home,
        tui,
        platform="darwin",
        machine="arm64",
        bodies=bodies,
        probe=FakeProbe(commands={"brew": "/opt/homebrew/bin/brew"}),
        runner=runner,
        refresh=True,
    )
    assert binary.read_bytes() == original
    assert _step(report, "piper").status == "failed"
    assert "x86_64" in _step(report, "piper").detail
    assert _step(report, "espeak").status == "failed"
    assert ["install", "espeak-ng"] not in _brew_verbs(runner)


_CHECKOUT_INSTALL = (
    'uv tool install --editable ./digivoice && export PATH="$HOME/.local/bin:$PATH"'
    " && digivoice install --auto"
)
_RELEASE_INSTALL = (
    "uv tool install --from "
    '"git+https://github.com/digithings-ai/digithings.git@<tag>#subdirectory=digivoice"'
    " digivoice && digivoice install --auto"
)


def test_documented_install_is_one_auto_command() -> None:
    """Checkout and release-tag installs are each one line, and both use --auto."""
    readme = Path(__file__).resolve().parents[2] / "digivoice" / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.index("## Install")
    section = text[start : text.index("## Requirements")]
    commands = [block.split("```", 1)[0].strip() for block in section.split("```bash\n")[1:]]
    assert commands == [_CHECKOUT_INSTALL, _RELEASE_INSTALL]
    assert all("\n" not in command for command in commands)
    architecture = (
        Path(__file__).resolve().parents[2] / "digivoice" / "ARCHITECTURE.md"
    ).read_text(encoding="utf-8")
    assert _CHECKOUT_INSTALL in architecture
    assert _RELEASE_INSTALL in architecture


def test_linux_install_does_not_install_espeak(tmp_path: Path) -> None:
    tui = _tui(tmp_path / "tui")
    report, _fetched = _install(
        tmp_path / "home",
        tui,
        platform="linux",
        machine="aarch64",
        bodies=_linux_bodies(),
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
    )
    assert report.ok
    assert all(step.id != "espeak" for step in report.steps)
