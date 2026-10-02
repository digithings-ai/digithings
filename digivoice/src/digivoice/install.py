"""Install the local toolchain, the default models, and the Hammerspoon adapter.

`digivoice install` fetches bun, the OpenTUI packages, whisper-cli, Piper, sox,
`ggml-base.en.bin`, and the Lessac Piper voice, then copies this checkout's
banner adapter into `~/.hammerspoon/digivoice`. `digivoice update` refreshes a
step whose pin changed. Rewrite GGUF stays off. Tests pass `fetch` and `runner`
so nothing here has to touch the network.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen

from digivoice.catalog import find_stt
from digivoice.models import InstallReport, InstallStamp, InstallStep
from digivoice.paths import DEFAULT_MODEL, local_bin, piper_fallback, vendor_dir
from digivoice.probe import CommandProbe
from digivoice.reload import reload_hammerspoon
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


def adapter_source_dir() -> Path:
    """Repo `digivoice/hammerspoon`, next to the Python package."""
    return Path(__file__).resolve().parents[2] / "hammerspoon"


def hammerspoon_adapter_dir(home: Path) -> Path:
    """Where Hammerspoon loads the adapter. Not a cloud path."""
    return home / ".hammerspoon" / "digivoice"


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
    refresh: bool = False,
    adapter_source: Path | None = None,
) -> InstallReport:
    """Install every local piece. A failed step does not skip the rest.

    `refresh` is what `digivoice update` passes. A step that is already at the
    pinned version stays. A missing or older step is fetched again.
    """
    worker = fetch or http_fetch
    source = adapter_source if adapter_source is not None else adapter_source_dir()
    steps: list[InstallStep] = []
    _attempt(steps, "bun", lambda: _install_bun(home, platform, machine, probe, worker, refresh))
    _attempt(
        steps,
        "opentui",
        lambda: _install_opentui(home, probe, runner, tui_root, refresh),
    )
    _attempt(
        steps,
        "whisper-cli",
        lambda: _install_whisper(home, platform, machine, probe, runner, worker, refresh),
    )
    _attempt(
        steps,
        "piper",
        lambda: _install_piper(home, platform, machine, probe, worker, refresh),
    )
    _attempt(steps, "sox", lambda: _install_sox(home, probe, runner, refresh))
    _attempt(steps, "stt", lambda: _install_stt(home, models_dir, worker, refresh))
    _attempt(steps, "voice", lambda: _install_voice(home, models_dir, worker, refresh))
    _attempt(steps, "adapter", lambda: _install_adapter(home, source, probe, runner))
    return InstallReport(steps=steps)


def render_install(report: InstallReport, *, heading: str = "digivoice install") -> str:
    lines = [heading]
    lines.extend(f"{step.id}  {step.status}  {step.detail}" for step in report.steps)
    if not report.ok:
        lines.append(f"{heading}: one or more steps failed")
    return "\n".join(lines) + "\n"


def _attempt(steps: list[InstallStep], step_id: str, action: Callable[[], InstallStep]) -> None:
    try:
        steps.append(action())
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        steps.append(InstallStep(id=step_id, status="failed", detail=detail))


def _stamp_path(home: Path) -> Path:
    return vendor_dir(home) / "install.json"


def _load_stamp(home: Path) -> InstallStamp:
    path = _stamp_path(home)
    if not path.is_file():
        return InstallStamp()
    try:
        return InstallStamp.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return InstallStamp()


def _remember(home: Path, **fields: str) -> None:
    current = _load_stamp(home).model_copy(update=fields)
    path = _stamp_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current.model_dump_json(), encoding="utf-8")


def _up_to_date(*, refresh: bool, present: bool, stamp: str, pin: str) -> bool:
    """A first install skips whatever is already on disk and does not stamp it.

    Update (`refresh`) fetches again when the file is missing or the stamp
    differs from the pin we last wrote.
    """
    if not present:
        return False
    if not refresh:
        return True
    return stamp == pin


def _opentui_pin(tui_root: Path) -> str:
    package = tui_root / "package.json"
    if not package.is_file():
        return ""
    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    deps = payload.get("dependencies")
    if not isinstance(deps, dict):
        return ""
    spec = deps.get("@opentui/core")
    return spec if isinstance(spec, str) else ""


def _install_bun(
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    fetch: FetchFn,
    refresh: bool,
) -> InstallStep:
    existing = _find_bun(home, probe)
    if _up_to_date(
        refresh=refresh,
        present=existing is not None,
        stamp=_load_stamp(home).bun,
        pin=BUN_VERSION,
    ):
        return InstallStep(id="bun", status="present", detail=existing or "")
    url = bun_archive_url(platform, machine)
    root = vendor_dir(home) / "bun"
    _extract_url(fetch, url, root)
    binary = _find_file(root, "bun")
    if binary is None:
        raise InstallError("archive did not contain bun")
    link = _link_binary(local_bin(home) / "bun", binary)
    _remember(home, bun=BUN_VERSION)
    return InstallStep(id="bun", status="installed", detail=link)


def _install_opentui(
    home: Path,
    probe: CommandProbe,
    runner: CommandRunner,
    tui_root: Path,
    refresh: bool,
) -> InstallStep:
    package = tui_root / "node_modules" / "@opentui" / "core"
    pin = _opentui_pin(tui_root)
    if _up_to_date(
        refresh=refresh,
        present=package.is_dir(),
        stamp=_load_stamp(home).opentui,
        pin=pin,
    ):
        return InstallStep(id="opentui", status="present", detail=str(package))
    if not (tui_root / "package.json").is_file():
        raise InstallError(f"OpenTUI package is not in this checkout: {tui_root}")
    bun = _find_bun(home, probe)
    if not bun:
        raise InstallError("bun is not available")
    # `install` is the bun subcommand. `--cwd` after it selects the package.
    # Before it, Bun 1.4.2 treats `install` as a missing script name.
    result = runner([bun, "install", "--cwd", str(tui_root)], timeout=INSTALL_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise InstallError(f"bun install failed ({reason})")
    if not package.is_dir():
        raise InstallError("bun install did not install @opentui/core")
    _remember(home, opentui=pin)
    return InstallStep(id="opentui", status="installed", detail=str(package))


def _install_whisper(
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    runner: CommandRunner,
    fetch: FetchFn,
    refresh: bool,
) -> InstallStep:
    existing = _find_whisper(home, probe)
    stamp = _load_stamp(home).whisper
    if platform == "darwin":
        return _install_whisper_brew(home, probe, runner, existing, stamp, refresh)
    if _up_to_date(
        refresh=refresh,
        present=existing is not None,
        stamp=stamp,
        pin=WHISPER_TAG,
    ):
        return InstallStep(id="whisper-cli", status="present", detail=existing or "")
    url = whisper_archive_url(platform, machine)
    if url is None:
        raise InstallError("whisper-cli has no archive for this platform")
    root = vendor_dir(home) / "whisper"
    _extract_url(fetch, url, root)
    binary = _find_file(root, "whisper-cli")
    if binary is None:
        raise InstallError("archive did not contain whisper-cli")
    link = _link_binary(local_bin(home) / "whisper-cli", binary)
    _remember(home, whisper=WHISPER_TAG)
    return InstallStep(id="whisper-cli", status="installed", detail=link)


def _install_whisper_brew(
    home: Path,
    probe: CommandProbe,
    runner: CommandRunner,
    existing: str | None,
    stamp: str,
    refresh: bool,
) -> InstallStep:
    """macOS whisper-cli comes from Homebrew. Update upgrades the bottle we installed."""
    if existing and not refresh:
        return InstallStep(id="whisper-cli", status="present", detail=existing)
    if existing and refresh and stamp not in {"", "brew"}:
        step = _brew(probe, runner, "whisper-cpp", "whisper-cli")
    else:
        upgrade = refresh and existing is not None and stamp in {"", "brew"}
        step = _brew_whisper(probe, runner, upgrade=upgrade, stamp=stamp)
    _remember(home, whisper="brew")
    return step


def _brew_whisper(
    probe: CommandProbe,
    runner: CommandRunner,
    *,
    upgrade: bool,
    stamp: str,
) -> InstallStep:
    """Homebrew whisper-cpp. An unstamped binary tries upgrade, then install."""
    if upgrade and stamp == "":
        try:
            return _brew(probe, runner, "whisper-cpp", "whisper-cli", upgrade=True)
        except InstallError:
            return _brew(probe, runner, "whisper-cpp", "whisper-cli")
    return _brew(probe, runner, "whisper-cpp", "whisper-cli", upgrade=upgrade)


def _install_piper(
    home: Path,
    platform: str,
    machine: str,
    probe: CommandProbe,
    fetch: FetchFn,
    refresh: bool,
) -> InstallStep:
    existing = _find_piper(home, probe)
    if _up_to_date(
        refresh=refresh,
        present=existing is not None,
        stamp=_load_stamp(home).piper,
        pin=PIPER_TAG,
    ):
        return InstallStep(id="piper", status="present", detail=existing or "")
    url = piper_archive_url(platform, machine)
    root = vendor_dir(home) / "piper"
    _extract_url(fetch, url, root)
    binary = _find_file(root, "piper")
    if binary is None:
        raise InstallError("archive did not contain piper")
    link = _link_binary(piper_fallback(home), binary)
    _remember(home, piper=PIPER_TAG)
    return InstallStep(id="piper", status="installed", detail=link)


def _install_sox(
    home: Path,
    probe: CommandProbe,
    runner: CommandRunner,
    refresh: bool,
) -> InstallStep:
    found = probe.lookup("sox")
    stamp = _load_stamp(home).sox
    if found and (not refresh or stamp != "brew"):
        return InstallStep(id="sox", status="present", detail=found)
    upgrade = bool(found) and refresh and stamp == "brew"
    step = _brew(probe, runner, "sox", "sox", upgrade=upgrade)
    _remember(home, sox="brew")
    return step


def _install_stt(home: Path, models_dir: Path, fetch: FetchFn, refresh: bool) -> InstallStep:
    dest = models_dir / f"{DEFAULT_MODEL}.bin"
    pin = stt_url()
    if _up_to_date(
        refresh=refresh,
        present=_nonempty(dest),
        stamp=_load_stamp(home).stt,
        pin=pin,
    ):
        return InstallStep(id="stt", status="present", detail=str(dest))
    _download(fetch, pin, dest)
    _remember(home, stt=pin)
    return InstallStep(id="stt", status="installed", detail=str(dest))


def _install_voice(home: Path, models_dir: Path, fetch: FetchFn, refresh: bool) -> InstallStep:
    onnx_url, json_url = voice_urls()
    onnx = models_dir / f"{VOICE_NAME}.onnx"
    sidecar = models_dir / f"{VOICE_NAME}.onnx.json"
    stamp = _load_stamp(home).voice
    both = _nonempty(onnx) and _nonempty(sidecar)
    if _up_to_date(refresh=refresh, present=both, stamp=stamp, pin=onnx_url):
        return InstallStep(id="voice", status="present", detail=str(onnx))
    replace = refresh and stamp != onnx_url
    if replace or not _nonempty(onnx):
        _download(fetch, onnx_url, onnx)
    if replace or not _nonempty(sidecar):
        _download(fetch, json_url, sidecar)
    _remember(home, voice=onnx_url)
    return InstallStep(id="voice", status="installed", detail=str(onnx))


def _install_adapter(
    home: Path,
    source: Path,
    probe: CommandProbe,
    runner: CommandRunner,
) -> InstallStep:
    dest = hammerspoon_adapter_dir(home)
    changed = _sync_adapter(dest, source)
    message, ok = reload_hammerspoon(runner, probe.lookup("hs"))
    detail = f"{dest} — {message}"
    if not ok:
        raise InstallError(detail)
    status = "installed" if changed else "present"
    return InstallStep(id="adapter", status=status, detail=detail)


def _sync_adapter(dest: Path, source: Path) -> bool:
    """Copy sibling `*.lua` into `dest`. True when a file changed.

    A symlink that already points at `source` is left alone. A real directory
    is updated in place, including deletion of lua that this checkout no longer
    ships, so an old hover control cannot stay behind.
    """
    root = source.resolve()
    if not root.is_dir():
        raise InstallError(f"adapter source is missing: {source}")
    lua_files = sorted(path for path in root.glob("*.lua") if path.is_file())
    if not lua_files:
        raise InstallError(f"adapter source has no lua: {source}")
    if dest.is_symlink():
        try:
            current = dest.resolve(strict=True)
        except OSError:
            current = None
        if current == root:
            return False
        dest.unlink()
    elif dest.exists() and not dest.is_dir():
        dest.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    names = {path.name for path in lua_files}
    changed = False
    for path in lua_files:
        target = dest / path.name
        data = path.read_bytes()
        same = target.is_file() and not target.is_symlink() and target.read_bytes() == data
        if same:
            continue
        if target.is_symlink() or target.exists():
            target.unlink()
        target.write_bytes(data)
        changed = True
    for extra in list(dest.glob("*.lua")):
        if extra.name not in names:
            extra.unlink()
            changed = True
    return changed


def _brew(
    probe: CommandProbe,
    runner: CommandRunner,
    formula: str,
    step_id: str,
    *,
    upgrade: bool = False,
) -> InstallStep:
    brew = probe.lookup("brew")
    if not brew:
        raise InstallError(
            f"{formula} is not on PATH and Homebrew is not available. "
            "Install Homebrew, then rerun digivoice install."
        )
    verb = "upgrade" if upgrade else "install"
    result = runner([brew, verb, formula], timeout=INSTALL_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise InstallError(f"brew {verb} {formula} failed ({reason})")
    return InstallStep(id=step_id, status="installed", detail=f"brew {verb} {formula}")


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
