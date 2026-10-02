"""Host checks for whisper-cli, Piper, capture tools, the default model,
settings validity, hotkey docs, and the Hammerspoon adapter."""

from __future__ import annotations

import json
from pathlib import Path

from digivoice.catalog import stt_model_path
from digivoice.models import DoctorCheck, DoctorReport, VoicePaths
from digivoice.paths import (
    DEFAULT_MODEL,
    linux_data_dir,
    mac_data_dir,
    piper_fallback,
    resolve_paths,
)
from digivoice.probe import CommandProbe
from digivoice.rewrite import rewrite_doctor_detail
from digivoice.runner import run_command
from digivoice.settings import HOTKEYS_DOCS, VoiceSettings, load_settings, settings_path

_REQUIRED = frozenset({"whisper-cli", "piper", "capture", "models"})


def _tool(check_id: str, found: str | None, missing: str) -> DoctorCheck:
    if found:
        return DoctorCheck(id=check_id, status="ok", detail=found)
    return DoctorCheck(id=check_id, status="missing", detail=missing)


def _models(paths: VoicePaths, probe: CommandProbe) -> DoctorCheck:
    models_dir = paths.models_dir
    try:
        settings = load_settings(paths)
        model_id = settings.stt_model
    except Exception:
        model_id = DEFAULT_MODEL
    model_path = str(stt_model_path(models_dir, model_id))
    if not probe.is_dir(models_dir):
        return DoctorCheck(
            id="models",
            status="missing",
            detail=f"model {model_id}: directory missing: {models_dir}",
        )
    if not probe.is_file(model_path):
        return DoctorCheck(
            id="models",
            status="missing",
            detail=f"model {model_id} missing: {model_path}",
        )
    return DoctorCheck(
        id="models",
        status="ok",
        detail=f"{model_id} at {model_path}",
    )


def _history(paths: VoicePaths, probe: CommandProbe) -> DoctorCheck:
    state = "present" if probe.is_file(paths.history_file) else "not created yet"
    return DoctorCheck(
        id="history",
        status="info",
        detail=f"{state}: {paths.history_file}",
    )


def _settings_check(paths: VoicePaths) -> DoctorCheck:
    """Validate settings.json: ok when valid, missing when corrupt, info when absent."""
    target = settings_path(paths)
    if not target.is_file():
        return DoctorCheck(
            id="settings",
            status="info",
            detail=f"no settings.json yet ({target}); using defaults",
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DoctorCheck(
            id="settings",
            status="missing",
            detail=f"invalid settings.json ({target}): {exc}; using defaults",
        )
    try:
        settings = VoiceSettings.model_validate(raw)
    except Exception as exc:
        return DoctorCheck(
            id="settings",
            status="missing",
            detail=f"invalid settings.json ({target}): {exc}; using defaults",
        )
    return DoctorCheck(
        id="settings",
        status="ok",
        detail=(
            f"valid settings.json ({target}; "
            f"banner_pinned={str(settings.banner_pinned).lower()}, "
            f"banner_position={settings.banner_position}, "
            f"rewrite_enabled={str(settings.rewrite_enabled).lower()})"
        ),
    )


def _hotkeys_check() -> DoctorCheck:
    if not HOTKEYS_DOCS:
        return DoctorCheck(id="hotkeys", status="missing", detail="no hotkey docs compiled in")
    summary = "; ".join(f"{name}: {doc}" for name, doc in HOTKEYS_DOCS.items())
    return DoctorCheck(
        id="hotkeys",
        status="ok",
        detail=f"sample binds documented ({summary}; see hammerspoon/README)",
    )


def _hammerspoon_check(home: Path, paths: VoicePaths, probe: CommandProbe) -> DoctorCheck:
    """Adapter presence: ~/.hammerspoon/digivoice or the data-dir hammerspoon path."""
    user_dir = str(home / ".hammerspoon" / "digivoice")
    user_init = str(home / ".hammerspoon" / "digivoice" / "init.lua")
    data_dir = str(Path(paths.data_dir) / "hammerspoon")
    data_init = str(Path(paths.data_dir) / "hammerspoon" / "init.lua")
    for candidate in (user_dir, data_dir):
        if probe.is_dir(candidate):
            return DoctorCheck(id="hammerspoon", status="ok", detail=f"adapter at {candidate}")
    for candidate in (user_init, data_init):
        if probe.is_file(candidate):
            return DoctorCheck(id="hammerspoon", status="ok", detail=f"adapter at {candidate}")
    return DoctorCheck(
        id="hammerspoon",
        status="missing",
        detail=(f"no adapter at {user_dir} or {data_dir} (copy digivoice/hammerspoon there)"),
    )


def _paths(home: Path, paths: VoicePaths) -> DoctorCheck:
    mac_models = mac_data_dir(home) / "models"
    linux_models = linux_data_dir(home, None) / "models"
    detail = (
        f"active data {paths.data_dir}; macOS {mac_models}; "
        f"Linux {linux_models} (or $XDG_DATA_HOME/digivoice/models); "
        f"dictation wavs {paths.recordings_dir}"
    )
    return DoctorCheck(id="paths", status="info", detail=detail)


def _detection_check(paths: VoicePaths) -> DoctorCheck:
    """Word/spelling detection stubs: settings only, never required for ok."""
    try:
        settings = load_settings(paths)
        word = bool(settings.word_detection)
        spelling = bool(settings.spelling_detection)
    except Exception:
        word, spelling = False, False
    if not word and not spelling:
        return DoctorCheck(
            id="detection",
            status="info",
            detail=(
                "word_detection=false spelling_detection=false "
                "(stubs; not wired to STT yet — settings only)"
            ),
        )
    return DoctorCheck(
        id="detection",
        status="info",
        detail=(
            f"word_detection={str(word).lower()} spelling_detection={str(spelling).lower()} "
            "(stub; STT pipeline still uses whisper as today — no behavior change yet)"
        ),
    )


def _rewrite_check(paths: VoicePaths, probe: CommandProbe) -> DoctorCheck:
    settings = load_settings(paths)
    status, detail = rewrite_doctor_detail(paths, settings, probe, run_command)
    return DoctorCheck(id="rewrite", status=status, detail=detail)


def doctor_checks(
    platform: str,
    home: Path,
    env: dict[str, str],
    probe: CommandProbe,
) -> list[DoctorCheck]:
    paths = resolve_paths(platform, home, env)
    piper_home = str(piper_fallback(home))
    piper = probe.lookup("piper")
    if piper is None and probe.executable(piper_home):
        piper = piper_home
    sox = probe.lookup("sox")
    ffmpeg = probe.lookup("ffmpeg")
    return [
        _tool(
            "whisper-cli",
            probe.lookup("whisper-cli"),
            "not on PATH (whisper.cpp binary name is whisper-cli)",
        ),
        _tool("piper", piper, f"not on PATH and not executable at {piper_home}"),
        _tool("sox", sox, "not on PATH"),
        _tool("ffmpeg", ffmpeg, "not on PATH"),
        _tool("capture", sox or ffmpeg, "need sox or ffmpeg for microphone capture"),
        _models(paths, probe),
        _settings_check(paths),
        _hotkeys_check(),
        _hammerspoon_check(home, paths, probe),
        _history(paths, probe),
        _paths(home, paths),
        _rewrite_check(paths, probe),
        _detection_check(paths),
        DoctorCheck(
            id="tcc",
            status="info",
            detail=(
                "Mic and Accessibility prompts are not probed. dict degrades to "
                "stdout when a paste is denied. See digivoice/hammerspoon/README.md "
                "for Mic + Accessibility TCC on macOS."
            ),
        ),
        DoctorCheck(
            id="interrupt",
            status="info",
            detail=(
                "On stop/early-stop, digivoice keeps the wav and pastes what was "
                "captured (paste_on_stop default). Resume-same-take is not supported "
                "— paste + start a new take. Esc (or `digivoice cancel`) discards the "
                "take instead: no paste, no history entry, wav deleted."
            ),
        ),
    ]


def doctor_ready(checks: list[DoctorCheck]) -> bool:
    """True when every required check is ok. Info rows do not block it."""
    return all(check.status == "ok" for check in checks if check.id in _REQUIRED)


def render_doctor(checks: list[DoctorCheck]) -> DoctorReport:
    ok = doctor_ready(checks)
    lines = ["digivoice doctor", ""]
    lines.extend(f"[{check.status}] {check.id}  {check.detail}" for check in checks)
    lines.append("")
    lines.append("result: ok" if ok else "result: not ready")
    return DoctorReport(ok=ok, checks=checks, text="\n".join(lines) + "\n")
