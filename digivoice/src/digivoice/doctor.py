"""Host checks for whisper-cli, Piper, capture tools, and the default model."""

from __future__ import annotations

from pathlib import Path

from digivoice.models import DoctorCheck, DoctorReport, VoicePaths
from digivoice.paths import (
    DEFAULT_MODEL,
    DEFAULT_MODEL_FILE,
    linux_data_dir,
    mac_data_dir,
    piper_fallback,
    resolve_paths,
)
from digivoice.probe import CommandProbe

_REQUIRED = frozenset({"whisper-cli", "piper", "capture", "models"})


def _tool(check_id: str, found: str | None, missing: str) -> DoctorCheck:
    if found:
        return DoctorCheck(id=check_id, status="ok", detail=found)
    return DoctorCheck(id=check_id, status="missing", detail=missing)


def _models(paths: VoicePaths, probe: CommandProbe) -> DoctorCheck:
    models_dir = paths.models_dir
    model_path = str(Path(models_dir) / DEFAULT_MODEL_FILE)
    if not probe.is_dir(models_dir):
        return DoctorCheck(
            id="models",
            status="missing",
            detail=f"default model {DEFAULT_MODEL}: directory missing: {models_dir}",
        )
    if not probe.is_file(model_path):
        return DoctorCheck(
            id="models",
            status="missing",
            detail=f"default model {DEFAULT_MODEL} missing: {model_path}",
        )
    return DoctorCheck(
        id="models",
        status="ok",
        detail=f"{DEFAULT_MODEL} at {model_path}",
    )


def _history(paths: VoicePaths, probe: CommandProbe) -> DoctorCheck:
    state = "present" if probe.is_file(paths.history_file) else "not created yet"
    return DoctorCheck(
        id="history",
        status="info",
        detail=f"{state}: {paths.history_file}",
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
        _history(paths, probe),
        _paths(home, paths),
        DoctorCheck(
            id="tcc",
            status="info",
            detail=(
                "Mic and Accessibility prompts are not probed. dict degrades to "
                "stdout when a paste is denied. See digivoice/hammerspoon/README.md "
                "for Mic + Accessibility TCC on macOS."
            ),
        ),
    ]


def render_doctor(checks: list[DoctorCheck]) -> DoctorReport:
    ok = all(check.status == "ok" for check in checks if check.id in _REQUIRED)
    lines = ["digivoice doctor", ""]
    lines.extend(f"[{check.status}] {check.id}  {check.detail}" for check in checks)
    lines.append("")
    lines.append("result: ok" if ok else "result: not ready")
    return DoctorReport(ok=ok, checks=checks, text="\n".join(lines) + "\n")
