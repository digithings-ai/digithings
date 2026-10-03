"""Install the local toolchain, the default models, and the Hammerspoon adapter.

`digivoice install` fetches bun, the OpenTUI packages, whisper-cli, Piper, sox,
`ggml-base.en.bin`, and the Lessac Piper voice, then copies this checkout's
banner adapter into `~/.hammerspoon/digivoice`. On an arm64 Mac it installs
the native arm64 Piper build, a same-arch `libespeak-ng.1.dylib`, and a
same-arch `libpiper_phonemize.1.dylib` beside that binary. A missing
same-arch espeak library is `brew install espeak-ng`. On a
terminal it asks first:
auto installs that default set, or the user picks local speech, voice, and
rewrite models. A pick does not delete models already on disk. `digivoice
update` refreshes a step whose pin changed and stays non-interactive. Tests
pass `fetch` and `runner` so nothing here has to touch the network.
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
from typing import TextIO
from urllib.request import Request, urlopen

from digivoice.catalog import (
    REWRITE_CATALOG,
    STT_CATALOG,
    VOICE_CATALOG,
    CatalogModel,
    find_rewrite,
    find_stt,
    find_voice,
)
from digivoice.models import InstallReport, InstallSelection, InstallStamp, InstallStep, VoicePaths
from digivoice.paths import DEFAULT_MODEL, local_bin, piper_fallback, vendor_dir
from digivoice.probe import CommandProbe
from digivoice.reload import reload_hammerspoon
from digivoice.runner import CommandRunner, error_tail
from digivoice.settings import load_settings, save_settings
from digivoice.speak import (
    find_espeak_library,
    library_matches_binary,
    macho_cpu,
    place_espeak_beside,
    place_macho_library,
)

FetchFn = Callable[[str, Path], None]

BUN_VERSION = "1.4.2"
WHISPER_TAG = "v1.9.2"
PIPER_TAG = "2023.11.14-2"
# rhasspy/piper 2023.11.14-2 built both macOS assets on Intel, so its
# piper_macos_aarch64.tar.gz is Mach-O x86_64. This is that same asset from
# the build that actually produced arm64 (rhasspy/piper#284).
PIPER_MACOS_ARM64_URL = (
    "https://github.com/dharmab/piper/releases/download/"
    "2024.12.14.1-alpha2/piper_macos_aarch64.tar.gz"
)
# That arm64 archive links @rpath/libpiper_phonemize.1.dylib and does not
# ship the file (its CMake install copies *.so and *.dll only). This jar's
# macos-arm64 build is Mach-O arm64, install name @rpath/libpiper_phonemize.1.dylib,
# and exports the piper phonemize symbols that binary links. It also ships
# arm64 libonnxruntime.1.14.1.dylib, which piper and phonemize both load.
PHONEMIZE_MACOS_ARM64_URL = (
    "https://github.com/GiviMAD/piper-jni/releases/download/"
    "piper_jni_1.2.0-a0f09cd/piper-jni-1.2.0-a0f09cd.jar"
)
_PHONEMIZE_LIBRARY = "libpiper_phonemize.1.dylib"
_ONNX_LIBRARY = "libonnxruntime.1.14.1.dylib"
_ARM64_PIPER_LIBRARIES = (_PHONEMIZE_LIBRARY, _ONNX_LIBRARY)
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
    if platform == "darwin" and arch == "aarch64":
        return PIPER_MACOS_ARM64_URL
    if platform == "darwin":
        name = "piper_macos_x64"
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
    selection: InstallSelection | None = None,
) -> InstallReport:
    """Install every local piece. A failed step does not skip the rest.

    `refresh` is what `digivoice update` passes. A step that is already at the
    pinned version stays. A missing or older step is fetched again.

    `selection` is the wizard choice. Auto, and a missing selection, install
    the default speech and voice files only. A pick downloads the named local
    catalog files and leaves every other model file on disk.
    """
    worker = fetch or http_fetch
    source = adapter_source if adapter_source is not None else adapter_source_dir()
    chosen = selection if selection is not None else InstallSelection()
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
    if platform == "darwin" and _arch(machine) == "aarch64":
        _attempt(
            steps,
            "phonemize",
            lambda: _install_phonemize(home, probe, worker),
        )
    if platform == "darwin":
        _attempt(
            steps,
            "espeak",
            lambda: _install_espeak(home, probe, runner, refresh, machine),
        )
    _attempt(steps, "sox", lambda: _install_sox(home, probe, runner, refresh))
    if chosen.auto:
        _attempt(steps, "stt", lambda: _install_stt(home, models_dir, worker, refresh))
        _attempt(steps, "voice", lambda: _install_voice(home, models_dir, worker, refresh))
    else:
        _install_picked(steps, models_dir, worker, chosen)
    _attempt(steps, "adapter", lambda: _install_adapter(home, source, probe, runner))
    return InstallReport(steps=steps)


_MODE_TEXT = """\
digivoice install

macOS is the desktop this app runs on. Hotkeys and paste go through Hammerspoon.

  1) Auto — ggml-base.en.bin, the Lessac voice, and the local toolchain
  2) Pick — choose local speech, voice, and rewrite models

Auto does not download a rewrite model. A pick does not delete models already on disk.
Choice [1/auto, 2/pick, or blank to cancel]: """


def run_install_wizard(
    stdin: TextIO,
    stdout: TextIO,
    *,
    models_dir: Path,
) -> InstallSelection | None:
    """Ask auto or pick. None means the user cancelled. No network."""
    while True:
        stdout.write(_MODE_TEXT)
        stdout.flush()
        raw = _read_line(stdin)
        if raw is None:
            return None
        mode = _parse_mode(raw)
        if mode == "cancel":
            return None
        if mode == "auto":
            return InstallSelection(auto=True)
        if mode == "pick":
            break
        stdout.write("Enter 1 or auto, or 2 or pick.\n")
    speech = _prompt_catalog(
        stdin,
        stdout,
        "Speech models",
        STT_CATALOG,
        models_dir,
    )
    if speech is None:
        return None
    voice = _prompt_catalog(stdin, stdout, "Voice models", VOICE_CATALOG, models_dir)
    if voice is None:
        return None
    rewrite = _prompt_catalog(
        stdin,
        stdout,
        "Rewrite models (local files only; rewrite stays off until you enable it)",
        REWRITE_CATALOG,
        models_dir,
    )
    if rewrite is None:
        return None
    return InstallSelection(auto=False, speech=speech, voice=voice, rewrite=rewrite)


def _read_line(stdin: TextIO) -> str | None:
    try:
        raw = stdin.readline()
    except (OSError, ValueError):
        return None
    if raw == "":
        return None
    return raw.strip()


def _parse_mode(raw: str) -> str | None:
    text = raw.casefold()
    if text in {"", "q", "quit", "cancel"}:
        return "cancel"
    if text in {"1", "auto"}:
        return "auto"
    if text in {"2", "pick"}:
        return "pick"
    return None


def _parse_indexes(raw: str, count: int) -> list[int] | None:
    indexes: list[int] = []
    for part in raw.replace(",", " ").split():
        if not part.isdigit():
            return None
        number = int(part)
        if number < 1 or number > count:
            return None
        index = number - 1
        if index not in indexes:
            indexes.append(index)
    return indexes


def _prompt_catalog(
    stdin: TextIO,
    stdout: TextIO,
    title: str,
    entries: tuple[CatalogModel, ...],
    models_dir: Path,
) -> list[str] | None:
    """Numbers from the catalog. Blank installs none. EOF cancels."""
    while True:
        stdout.write(f"\n{title}\n")
        stdout.write("Numbers separated by commas. Blank installs none of these.\n")
        for index, entry in enumerate(entries, start=1):
            on_disk = " · on disk" if _nonempty(models_dir / entry.filename) else ""
            label = entry.title
            if entry.id == DEFAULT_MODEL or entry.filename.startswith(f"{VOICE_NAME}."):
                if "default" not in label.casefold():
                    label = f"{label} (default)"
            stdout.write(f"  {index}) {label} · {entry.size_hint} · {entry.filename}{on_disk}\n")
        stdout.write("Choice: ")
        stdout.flush()
        raw = _read_line(stdin)
        if raw is None:
            return None
        if raw == "":
            return []
        indexes = _parse_indexes(raw, len(entries))
        if indexes is None:
            stdout.write("Enter numbers from the list, separated by commas.\n")
            continue
        return [entries[index].id for index in indexes]


def _install_picked(
    steps: list[InstallStep],
    models_dir: Path,
    fetch: FetchFn,
    selection: InstallSelection,
) -> None:
    _attempt_catalog(steps, "stt", selection.speech, models_dir, fetch)
    _attempt_catalog(steps, "voice", selection.voice, models_dir, fetch)
    _attempt_catalog(steps, "rewrite", selection.rewrite, models_dir, fetch)
    _apply_pick(models_dir, selection)


def _attempt_catalog(
    steps: list[InstallStep],
    kind: str,
    model_ids: list[str],
    models_dir: Path,
    fetch: FetchFn,
) -> None:
    for model_id in model_ids:
        step_id = f"{kind}:{model_id}"
        _attempt(
            steps,
            step_id,
            lambda model_id=model_id, step_id=step_id: _install_catalog_choice(
                kind, model_id, step_id, models_dir, fetch
            ),
        )


def _catalog_entry(kind: str, model_id: str) -> CatalogModel:
    if kind == "stt":
        entry = find_stt(model_id)
    elif kind == "voice":
        entry = find_voice(model_id)
    else:
        entry = find_rewrite(model_id)
    if entry is None:
        raise InstallError(f"no local {kind} model {model_id}")
    return entry


def _install_catalog_choice(
    kind: str,
    model_id: str,
    step_id: str,
    models_dir: Path,
    fetch: FetchFn,
) -> InstallStep:
    """Download one catalog file. Other files in the models directory stay."""
    entry = _catalog_entry(kind, model_id)
    dest = _safe_model_path(models_dir, entry.filename)
    pieces: list[tuple[str, Path]] = [(entry.url, dest)]
    if entry.sidecar_url:
        pieces.append((entry.sidecar_url, dest.with_name(dest.name + ".json")))
    pending = [(url, path) for url, path in pieces if not _nonempty(path)]
    if not pending:
        return InstallStep(id=step_id, status="present", detail=str(dest))
    for url, path in pending:
        _download(fetch, url, path)
    return InstallStep(id=step_id, status="installed", detail=str(dest))


def _safe_model_path(models_dir: Path, filename: str) -> Path:
    name = Path(filename).name
    if not name or name != filename or name in {".", ".."}:
        raise InstallError(f"model filename is not a local file: {filename}")
    return models_dir / name


def _apply_pick(models_dir: Path, selection: InstallSelection) -> None:
    """Point settings at the first picked file that landed. Leave the rest alone."""
    if selection.auto:
        return
    paths = _paths_for_models(models_dir)
    current = load_settings(paths)
    updates: dict[str, str] = {}
    speech = _first_on_disk(models_dir, "stt", selection.speech)
    if speech is not None:
        updates["stt_model"] = speech.id
    voice = _first_on_disk(models_dir, "voice", selection.voice)
    if voice is not None:
        updates["tts_voice"] = voice.filename
    rewrite = _first_on_disk(models_dir, "rewrite", selection.rewrite)
    if rewrite is not None:
        updates["rewrite_model"] = rewrite.filename
    if not updates:
        return
    save_settings(paths, current.model_copy(update=updates))


def _first_on_disk(models_dir: Path, kind: str, model_ids: list[str]) -> CatalogModel | None:
    for model_id in model_ids:
        try:
            entry = _catalog_entry(kind, model_id)
        except InstallError:
            continue
        if _nonempty(models_dir / entry.filename):
            return entry
    return None


def _paths_for_models(models_dir: Path) -> VoicePaths:
    data = models_dir.parent
    return VoicePaths(
        data_dir=str(data),
        models_dir=str(models_dir),
        recordings_dir=str(data / "recordings"),
        history_file=str(data / "history.jsonl"),
    )


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
    replace = _x86_piper_on_arm64_mac(home, platform, machine, existing)
    if not replace and _up_to_date(
        refresh=refresh,
        present=existing is not None,
        stamp=_load_stamp(home).piper,
        pin=PIPER_TAG,
    ):
        return InstallStep(id="piper", status="present", detail=existing or "")
    url = piper_archive_url(platform, machine)
    root = vendor_dir(home) / "piper"
    staging = vendor_dir(home) / "piper.incoming"
    try:
        _extract_url(fetch, url, staging)
        staged = _find_file(staging, "piper")
        if staged is None:
            raise InstallError("archive did not contain piper")
        if platform == "darwin" and _arch(machine) == "aarch64" and macho_cpu(staged) == "x86_64":
            raise InstallError("piper archive is x86_64, not arm64")
        if root.exists():
            shutil.rmtree(root)
        staging.rename(root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    binary = _find_file(root, "piper")
    if binary is None:
        raise InstallError("archive did not contain piper")
    link = _link_binary(piper_fallback(home), binary)
    _remember(home, piper=PIPER_TAG)
    return InstallStep(id="piper", status="installed", detail=link)


def _install_phonemize(home: Path, probe: CommandProbe, fetch: FetchFn) -> InstallStep:
    """Put same-arch Piper dylibs beside the real arm64 binary.

    The dharmab archive is searched first. A missing library is taken from
    the arm64 piper-jni jar. An x86_64 library is not copied.
    """
    binary = _find_piper(home, probe)
    if binary is None or macho_cpu(Path(binary).resolve()) != "arm64":
        return InstallStep(id="phonemize", status="present", detail="piper is not arm64")
    missing = [
        name for name in _ARM64_PIPER_LIBRARIES if _copy_piper_library(home, binary, name) is None
    ]
    if not missing:
        return InstallStep(
            id="phonemize",
            status="present",
            detail=str(Path(binary).resolve().parent / _PHONEMIZE_LIBRARY),
        )
    staging = vendor_dir(home) / "phonemize.incoming"
    try:
        _extract_url(fetch, PHONEMIZE_MACOS_ARM64_URL, staging)
        for name in missing:
            found = _find_file(staging, name)
            if found is None:
                raise InstallError(f"archive did not contain {name}")
            placed = place_macho_library(binary, found, name)
            if placed is None:
                raise InstallError(f"{name} is not the same architecture as piper")
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return InstallStep(
        id="phonemize",
        status="installed",
        detail=str(Path(binary).resolve().parent / _PHONEMIZE_LIBRARY),
    )


def _copy_piper_library(home: Path, binary: str, name: str) -> Path | None:
    """A same-arch library already beside piper, or one copied out of vendor/piper."""
    beside = _beside_matching(binary, name)
    if beside is not None:
        return beside
    vendor = vendor_dir(home) / "piper"
    if not vendor.is_dir():
        return None
    for path in vendor.rglob(name):
        if not path.is_file() or path.name != name:
            continue
        placed = place_macho_library(binary, path, name)
        if placed is not None:
            return placed
    return None


def _beside_matching(binary: str, name: str) -> Path | None:
    path = Path(binary)
    if not path.exists():
        return None
    dest = path.resolve().parent / name
    if not dest.is_file() or not library_matches_binary(binary, dest):
        return None
    cpu = macho_cpu(path.resolve())
    if cpu is None or macho_cpu(dest) != cpu:
        return None
    return dest


def _install_espeak(
    home: Path,
    probe: CommandProbe,
    runner: CommandRunner,
    refresh: bool,
    machine: str,
) -> InstallStep:
    """macOS Piper needs a same-arch libespeak-ng beside the real binary."""
    binary = _find_piper(home, probe) or str(piper_fallback(home))
    found = find_espeak_library(home, binary, platform="darwin")
    stamp = _load_stamp(home).espeak
    if found is not None and (not refresh or stamp != "brew"):
        placed = place_espeak_beside(binary, found)
        detail = str(placed if placed is not None else found)
        return InstallStep(id="espeak", status="present", detail=detail)
    if found is None and _binary_is_x86_on_arm64(binary, machine):
        return InstallStep(
            id="espeak",
            status="failed",
            detail="Homebrew espeak-ng is arm64 and cannot load into this x86_64 Piper",
        )
    upgrade = found is not None and refresh and stamp == "brew"
    step = _brew(probe, runner, "espeak-ng", "espeak", upgrade=upgrade)
    _remember(home, espeak="brew")
    found = find_espeak_library(home, binary, platform="darwin")
    if found is not None:
        place_espeak_beside(binary, found)
    return step


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


def _x86_piper_on_arm64_mac(
    home: Path,
    platform: str,
    machine: str,
    existing: str | None,
) -> bool:
    """An x86_64 Piper this install wrote under vendor, on an arm64 Mac."""
    if platform != "darwin" or existing is None or _arch(machine) != "aarch64":
        return False
    path = Path(existing).resolve()
    vendor = (vendor_dir(home) / "piper").resolve()
    if path != vendor and vendor not in path.parents:
        return False
    return macho_cpu(path) == "x86_64"


def _binary_is_x86_on_arm64(binary: str, machine: str) -> bool:
    if _arch(machine) != "aarch64":
        return False
    path = Path(binary)
    target = path.resolve() if path.exists() else path
    return target.is_file() and macho_cpu(target) == "x86_64"


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
