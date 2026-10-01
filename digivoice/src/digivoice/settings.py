"""Persistent digivoice settings (JSON under the data directory).

Agents and humans drive setup via `digivoice settings` / `settings set`.
Defaults keep rewrite disabled so a missing local LLM never breaks dictation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL, resolve_paths

SETTINGS_FILE_NAME = "settings.json"

RewritePreset = Literal["email", "sms", "professional", "coding", "blog", "none"]
RewriteRunnerKind = Literal["auto", "ollama", "llama.cpp"]
BannerDensity = Literal["mini", "peek", "full"]
BannerPosition = Literal[
    "top-center",
    "top-left",
    "top-right",
    "middle-left",
    "middle-right",
    "bottom-center",
    "bottom-left",
    "bottom-right",
    "center",
]

PRESET_LABELS: dict[str, str] = {
    "email": "Email — clear greeting, paragraphs, sign-off friendly",
    "sms": "SMS — short, plain, no fluff",
    "professional": "Professional posts — polished LinkedIn/X tone",
    "coding": "Coding-agent prompts — structured, actionable for CLI agents",
    "blog": "Blog — readable prose with light structure",
    "none": "None — no rewrite instructions beyond light cleanup",
}

HOTKEYS_DOCS = {
    "dict_toggle": "Right Option (keycode 61) — start/stop digivoice dict --toggle",
    "speak_selection": (
        "Double-tap Left Option (keycode 58, ~350ms) — digivoice speak --selection"
    ),
    "cancel": (
        "Esc while recording/transcribing/rewriting — discard the take (no paste, no history entry)"
    ),
}


# Default focused-app → preset map (substring match on app name). Editable via settings.
DEFAULT_REWRITE_APP_ROUTES: dict[str, str] = {
    "mail": "email",
    "outlook": "email",
    "spark": "email",
    "airmail": "email",
    "mimestream": "email",
    "messages": "sms",
    "whatsapp": "sms",
    "signal": "sms",
    "telegram": "sms",
    "imessage": "sms",
    "terminal": "coding",
    "iterm": "coding",
    "warp": "coding",
    "kitty": "coding",
    "alacritty": "coding",
    "vscode": "coding",
    "code": "coding",
    "cursor": "coding",
    "opencode": "coding",
    "ghostty": "coding",
    "safari": "professional",
    "chrome": "professional",
    "firefox": "professional",
    "arc": "professional",
    "brave": "professional",
    "edge": "professional",
}


class VoiceSettings(BaseModel):
    """User-editable digivoice config. Stored as settings.json under the data dir."""

    stt_model: str = DEFAULT_MODEL
    tts_voice: str | None = None
    rewrite_enabled: bool = False
    rewrite_preset: RewritePreset = "none"
    rewrite_model: str | None = None
    rewrite_runner: RewriteRunnerKind = "auto"
    rewrite_auto_route: bool = False
    # fragment (casefold substring of focused app name) → preset name. Not hard-coded in rewrite.
    rewrite_app_routes: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_REWRITE_APP_ROUTES)
    )
    rewrite_timeout_seconds: float = 30.0
    # Feature toggles agents can flip without touching code.
    paste_on_stop: bool = True
    # Word / spelling detection stubs (MVP off; settings only, not wired to STT yet).
    word_detection: bool = False
    spelling_detection: bool = False
    # Status overlay drawn by the Hammerspoon adapter (read from status.json). Display only.
    live_banner: bool = True
    banner_position: BannerPosition = "top-center"
    # Banner density: mini (grid only) | peek (short glimpse, auto-hides; default) | full (stays).
    banner_density: BannerDensity = "peek"
    # False renders the dot-matrix icon as a still frame instead of animating it.
    banner_animations: bool = True


def settings_path(paths: VoicePaths) -> Path:
    return Path(paths.data_dir) / SETTINGS_FILE_NAME


def default_settings() -> VoiceSettings:
    return VoiceSettings()


def load_settings(paths: VoicePaths) -> VoiceSettings:
    target = settings_path(paths)
    if not target.is_file():
        return default_settings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_settings()
    if not isinstance(raw, dict):
        return default_settings()
    try:
        return VoiceSettings.model_validate(raw)
    except ValidationError:
        return default_settings()


def save_settings(paths: VoicePaths, settings: VoiceSettings) -> Path:
    target = settings_path(paths)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def resolve_settings(
    platform: str,
    home: Path,
    env: Mapping[str, str],
) -> tuple[VoicePaths, VoiceSettings]:
    paths = resolve_paths(platform, home, env)
    return paths, load_settings(paths)


def settings_public_dict(settings: VoiceSettings, paths: VoicePaths) -> dict[str, Any]:
    """Machine-readable dump including paths and hotkey docs (not persisted)."""
    data = settings.model_dump(mode="json")
    data["paths"] = {
        "data_dir": paths.data_dir,
        "models_dir": paths.models_dir,
        "recordings_dir": paths.recordings_dir,
        "history_file": paths.history_file,
        "settings_file": str(settings_path(paths)),
    }
    data["hotkeys"] = dict(HOTKEYS_DOCS)
    data["presets"] = dict(PRESET_LABELS)
    data["rewrite_model_hint"] = (
        f"Place a local GGUF or Ollama model under {paths.models_dir}/ "
        "(or set rewrite_model to an ollama tag / absolute path). "
        "Weights are not bundled; doctor reports when rewrite is enabled but the runner/model is missing."
    )
    return data


_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})


def parse_setting_value(key: str, raw: str) -> Any:
    """Coerce a CLI string into the type VoiceSettings expects for `key`."""
    fields = VoiceSettings.model_fields
    if key not in fields:
        raise KeyError(key)
    text = raw.strip()
    if key in {"tts_voice", "rewrite_model"} and text.lower() in {"", "none", "null"}:
        return None
    bool_keys = {name for name, field in fields.items() if field.annotation is bool}
    if key in bool_keys:
        lower = text.casefold()
        if lower in _BOOL_TRUE:
            return True
        if lower in _BOOL_FALSE:
            return False
        raise ValueError(f"{key} expects true/false, got {raw!r}")
    if key == "rewrite_timeout_seconds":
        return float(text)
    if key == "rewrite_app_routes":
        parsed = json.loads(text)
        if not isinstance(parsed, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
        ):
            raise ValueError("rewrite_app_routes expects a JSON object of string→string")
        return parsed
    # Literals and Optional[str] handled by model_validate after set.
    return text


def set_setting(paths: VoicePaths, key: str, raw: str) -> VoiceSettings:
    if key not in VoiceSettings.model_fields:
        raise KeyError(key)
    current = load_settings(paths)
    value = parse_setting_value(key, raw)
    updated = current.model_copy(update={key: value})
    # Re-validate (Literal presets, etc.).
    settings = VoiceSettings.model_validate(updated.model_dump())
    save_settings(paths, settings)
    return settings


def format_settings_text(settings: VoiceSettings, paths: VoicePaths) -> str:
    data = settings_public_dict(settings, paths)
    lines = [
        "digivoice settings",
        f"file: {data['paths']['settings_file']}",
        "",
        "models / features",
        f"  stt_model:              {settings.stt_model}",
        f"  tts_voice:              {settings.tts_voice or '(auto / DIGIVOICE_PIPER_VOICE)'}",
        f"  rewrite_enabled:        {settings.rewrite_enabled}",
        f"  rewrite_preset:        {settings.rewrite_preset}",
        f"  rewrite_model:         {settings.rewrite_model or '(unset — see doctor)'}",
        f"  rewrite_runner:        {settings.rewrite_runner}",
        f"  rewrite_auto_route:    {settings.rewrite_auto_route}",
        f"  rewrite_app_routes:    {len(settings.rewrite_app_routes)} fragment→preset entries",
        f"  rewrite_timeout_seconds: {settings.rewrite_timeout_seconds}",
        f"  paste_on_stop:          {settings.paste_on_stop}",
        f"  word_detection:         {settings.word_detection}",
        f"  spelling_detection:     {settings.spelling_detection}",
        f"  live_banner:            {settings.live_banner}",
        f"  banner_position:        {settings.banner_position}",
        f"  banner_density:         {settings.banner_density}",
        f"  banner_animations:      {settings.banner_animations}",
        "",
        "paths",
        f"  data_dir:       {paths.data_dir}",
        f"  models_dir:     {paths.models_dir}",
        f"  recordings_dir: {paths.recordings_dir}",
        f"  history_file:   {paths.history_file}",
        "",
        "hotkeys (locked sample)",
    ]
    for name, doc in HOTKEYS_DOCS.items():
        lines.append(f"  {name}: {doc}")
    lines.append("")
    lines.append("rewrite presets")
    for name, label in PRESET_LABELS.items():
        lines.append(f"  {name}: {label}")
    lines.append("")
    lines.append(data["rewrite_model_hint"])
    lines.append("")
    lines.append("interrupt: on stop/early-stop, digivoice keeps the wav and pastes what was")
    lines.append("captured (default). Resume-same-take is not supported — paste + new take.")
    lines.append("")
    return "\n".join(lines)
