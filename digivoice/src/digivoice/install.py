"""Install the local toolchain and the default models. No cloud STT or TTS.

`digivoice install` fetches bun, the OpenTUI packages, whisper-cli, Piper, sox,
`ggml-base.en.bin`, and the Lessac Piper voice. Rewrite GGUF stays off.
Tests pass `fetch` and `runner` so nothing here has to touch the network.
"""

from __future__ import annotations

import io
import os
import shutil
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen

from digivoice.catalog import find_stt
from digivoice.models import InstallReport, InstallStep
from digivoice.paths import DEFAULT_MODEL, local_bin, piper_fallback, vendor_dir
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

FetchFn = Callable[[str, Path], None]

BUN_VERSION = "1.4.2"
WHISPER_TAG = "v1.9.2"
PIPER_TAG = "2023.11.14-2"
VOICE_NAME = "en_US-lessac-medium"
INSTALL_TIMEOUT = 600.0
_BUN_RELEASE = f"https://github.com/oven-sh/bun/releases/download/bun-v{BUN_VERSION}"
_WHISPER_RELEASE = f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_TAG}"
_PIPER_RELEASE = f"https://github.com/rhasspy/piper/releases/download/{PIPER_TAG}"
_VOICE_RELEASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"


class InstallError(Exception):
    """One install step cannot continue. Other steps still run."""


def bun_archive_url(platform: str, machine: str) -> str:
    return f"{_BUN_RELEASE}/bun-{_host_triple(platform, machine)}.zip"


def whisper_archive_url(platform: str, machine: str) -> str | None:
    """Linux publishes a whisper-cli build. macOS uses Homebrew instead."""
    if platform == "darwin":
        return None
    _require_desktop(platform)
    name = "arm64" if _arch(machine) == "aarch64" else "x64"
    return f"{_WHISPER_RELEASE}/whisper-bin-ubuntu-{name}.tar.gz"


def piper_archive_url(platform: str, machine: str) -> str:
    _require_desktop(platform)
    arch = _arch(machine)
    if platform == "darwin":
        name = "piper_macos_aarch64" if arch == "aarch64" else "piper_macos_x64"
    else:
        name = "piper_linux_aarch64" if arch == "aarch64" else "piper_linux_x86_64"
    return f"{_PIPER_RELEASE}/{name}.tar.gz"


def voice_urls() -> tuple[str, str]:
    onnx = f"{_VOICE_RELEASE}/{VOICE_NAME}.onnx"
    return onnx, f"{onnx}.json"


def stt_url() -> str:
    entry = find_stt(DEFAULT_MODEL)
    if entry is None:
        raise InstallError(f"catalog has no {DEFAULT_MODEL}")
    return entry.url


def http_fetch(url: str, dest: Path) -> None:
    """Stream one URL to `dest`. Callers inject a fake in tests."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    request = Request(url, headers={"User-Agent": "digivoice-install"})
    try:
        with urlopen(request, timeout=INSTALL_TIMEOUT) as response, tmp.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise InstallError(f"download was empty: {dest.name}")
    tmp.replace(dest)


def run_install(
    *,
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    runner: CommandRunner,
    models_dir: Path,
    tui_root: Path,
    fetch: FetchFn | None = None,
) -> InstallReport:
    """Install every local piece. A failed step does not skip the rest."""
    worker = fetch or http_fetch
    steps: list[InstallStep] = []
    _attempt(steps, "bun", lambda: _install_bun(home, platform, machine, probe, worker))
    _attempt(steps, "opentui", lambda: _install_opentui(home, probe, runner, tui_root))
    _attempt(
        steps,
        "whisper-cli",
        lambda: _install_whisper(home, platform, machine, probe, runner, worker),
    )
    _attempt(steps, "piper", lambda: _install_piper(home, platform, machine, probe, worker))
    _attempt(steps, "sox", lambda: _install_sox(probe, runner))
    _attempt(steps, "stt", lambda: _install_stt(models_dir, worker))
    _attempt(steps, "voice", lambda: _install_voice(models_dir, worker))
    return InstallReport(steps=steps)


def render_install(report: InstallReport) -> str:
    lines = ["digivoice install"]
    lines.extend(f"{step.id}  {step.status}  {step.detail}" for step in report.steps)
    if not report.ok:
        lines.append("digivoice install: one or more steps failed")
    return "\n".join(lines) + "\n"


def _attempt(steps: list[InstallStep], step_id: str, action: Callable[[], InstallStep]) -> None:
    try:
        steps.append(action())
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        steps.append(InstallStep(id=step_id, status="failed", detail=detail))


def _install_bun(
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    fetch: FetchFn,
) -> InstallStep:
    existing = _find_bun(home, probe)
    if existing:
        return InstallStep(id="bun", status="present", detail=existing)
    url = bun_archive_url(platform, machine)
    root = vendor_dir(home) / "bun"
    _extract_url(fetch, url, root)
    binary = _find_file(root, "bun")
    if binary is None:
        raise InstallError("archive did not contain bun")
    link = _link_binary(local_bin(home) / "bun", binary)
    return InstallStep(id="bun", status="installed", detail=link)


def _install_opentui(
    home: Path,
    probe: CommandProbe,
    runner: CommandRunner,
    tui_root: Path,
) -> InstallStep:
    package = tui_root / "node_modules" / "@opentui" / "core"
    if package.is_dir():
        return InstallStep(id="opentui", status="present", detail=str(package))
    if not (tui_root / "package.json").is_file():
        raise InstallError(f"OpenTUI package is not in this checkout: {tui_root}")
    bun = _find_bun(home, probe)
    if not bun:
        raise InstallError("bun is not available")
    result = runner([bun, "--cwd", str(tui_root), "install"], timeout=INSTALL_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise InstallError(f"bun install failed ({reason})")
    if not package.is_dir():
        raise InstallError("bun install did not install @opentui/core")
    return InstallStep(id="opentui", status="installed", detail=str(package))


def _install_whisper(
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    runner: CommandRunner,
    fetch: FetchFn,
) -> InstallStep:
    existing = _find_whisper(home, probe)
    if existing:
        return InstallStep(id="whisper-cli", status="present", detail=existing)
    url = whisper_archive_url(platform, machine)
    if url is None:
        return _brew(probe, runner, "whisper-cpp", "whisper-cli")
    root = vendor_dir(home) / "whisper"
    _extract_url(fetch, url, root)
    binary = _find_file(root, "whisper-cli")
    if binary is None:
        raise InstallError("archive did not contain whisper-cli")
    link = _link_binary(local_bin(home) / "whisper-cli", binary)
    return InstallStep(id="whisper-cli", status="installed", detail=link)


def _install_piper(
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    fetch: FetchFn,
) -> InstallStep:
    existing = _find_piper(home, probe)
    if existing:
        return InstallStep(id="piper", status="present", detail=existing)
    url = piper_archive_url(platform, machine)
    root = vendor_dir(home) / "piper"
    _extract_url(fetch, url, root)
    binary = _find_file(root, "piper")
    if binary is None:
        raise InstallError("archive did not contain piper")
    link = _link_binary(piper_fallback(home), binary)
    return InstallStep(id="piper", status="installed", detail=link)


def _install_sox(probe: CommandProbe, runner: CommandRunner) -> InstallStep:
    found = probe.lookup("sox")
    if found:
        return InstallStep(id="sox", status="present", detail=found)
    return _brew(probe, runner, "sox", "sox")


def _install_stt(models_dir: Path, fetch: FetchFn) -> InstallStep:
    dest = models_dir / f"{DEFAULT_MODEL}.bin"
    if _nonempty(dest):
        return InstallStep(id="stt", status="present", detail=str(dest))
    _download(fetch, stt_url(), dest)
    return InstallStep(id="stt", status="installed", detail=str(dest))


def _install_voice(models_dir: Path, fetch: FetchFn) -> InstallStep:
    onnx_url, json_url = voice_urls()
    onnx = models_dir / f"{VOICE_NAME}.onnx"
    sidecar = models_dir / f"{VOICE_NAME}.onnx.json"
    wrote = False
    if not _nonempty(onnx):
        _download(fetch, onnx_url, onnx)
        wrote = True
    if not _nonempty(sidecar):
        _download(fetch, json_url, sidecar)
        wrote = True
    status = "installed" if wrote else "present"
    return InstallStep(id="voice", status=status, detail=str(onnx))


def _brew(probe: CommandProbe, runner: CommandRunner, formula: str, step_id: str) -> InstallStep:
    brew = probe.lookup("brew")
    if not brew:
        raise InstallError(
            f"{formula} is not on PATH and Homebrew is not available. "
            "Install Homebrew, then rerun digivoice install."
        )
    result = runner([brew, "install", formula], timeout=INSTALL_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise InstallError(f"brew install {formula} failed ({reason})")
    return InstallStep(id=step_id, status="installed", detail=f"brew install {formula}")


def _find_bun(home: Path, probe: CommandProbe) -> str | None:
    found = probe.lookup("bun")
    if found:
        return found
    for candidate in (local_bin(home) / "bun", home / ".bun" / "bin" / "bun"):
        ready = _executable(candidate)
        if ready:
            return ready
    return None


def _find_whisper(home: Path, probe: CommandProbe) -> str | None:
    for name in ("whisper-cli", "whisper-cpp"):
        found = probe.lookup(name)
        if found:
            return found
    return _executable(local_bin(home) / "whisper-cli")


def _find_piper(home: Path, probe: CommandProbe) -> str | None:
    found = probe.lookup("piper")
    if found:
        return found
    return _executable(piper_fallback(home))


def _executable(path: Path) -> str | None:
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


def _nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _download(fetch: FetchFn, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    scratch = dest.with_name(dest.name + ".part")
    fetch(url, scratch)
    if not _nonempty(scratch):
        scratch.unlink(missing_ok=True)
        raise InstallError(f"download did not write {dest.name}")
    scratch.replace(dest)


def _extract_url(fetch: FetchFn, url: str, root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    blob = root.with_name(root.name + ".download")
    try:
        fetch(url, blob)
        data = blob.read_bytes()
    finally:
        blob.unlink(missing_ok=True)
    if not data:
        raise InstallError(f"download was empty: {url}")
    _extract_bytes(data, root)


def _extract_bytes(data: bytes, dest: Path) -> None:
    if data[:2] == b"PK":
        _extract_zip(data, dest)
        return
    _extract_tar(data, dest)


def _extract_zip(data: bytes, dest: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        _reject_members([info.filename for info in archive.infolist()], dest)
        archive.extractall(dest)


def _extract_tar(data: bytes, dest: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            _reject_members([member.name for member in archive.getmembers()], dest)
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    _reject_members([member.linkname], dest)
            archive.extractall(dest, filter="data")
    except (tarfile.TarError, tarfile.FilterError, ValueError) as exc:
        raise InstallError(f"archive rejected: {exc}") from exc


def _reject_members(names: list[str], dest: Path) -> None:
    root = dest.resolve()
    for name in names:
        parts = Path(name).parts
        if not name or name.startswith(("/", "\\")) or ".." in parts:
            raise InstallError(f"archive path escapes the destination: {name}")
        target = (dest / name).resolve()
        if target != root and root not in target.parents:
            raise InstallError(f"archive path escapes the destination: {name}")


def _find_file(root: Path, name: str) -> Path | None:
    matches = [path for path in root.rglob(name) if path.is_file() and path.name == name]
    return matches[0] if matches else None


def _link_binary(link: Path, binary: Path) -> str:
    binary.chmod(binary.stat().st_mode | 0o755)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(binary.resolve())
    return str(link)


def _host_triple(platform: str, machine: str) -> str:
    _require_desktop(platform)
    arch = "aarch64" if _arch(machine) == "aarch64" else "x64"
    prefix = "darwin" if platform == "darwin" else "linux"
    return f"{prefix}-{arch}"


def _arch(machine: str) -> str:
    name = machine.lower()
    if name in {"aarch64", "arm64"}:
        return "aarch64"
    if name in {"x86_64", "amd64"}:
        return "x64"
    raise InstallError(f"unsupported machine {machine}")


def _require_desktop(platform: str) -> None:
    if platform not in {"darwin", "linux"}:
        raise InstallError(f"unsupported platform {platform}")
