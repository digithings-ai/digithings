"""Persistent digivoice settings (JSON under the data directory).

Agents and humans drive setup via `digivoice settings` / `settings set`.
Defaults keep rewrite disabled so a missing local LLM never breaks dictation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL, resolve_paths

SETTINGS_FILE_NAME = "settings.json"
# Playback speed. 1 is normal, 2 is twice as fast, 0.5 is half speed.
SPEECH_SPEEDS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)

RewritePreset = Literal["email", "sms", "professional", "coding", "blog", "none"]
RewriteRunnerKind = Literal["auto", "ollama", "llama.cpp"]
BannerDensity = Literal["retract", "full"]

REWRITE_TIMEOUT_PRESETS: tuple[float, ...] = (15.0, 30.0, 60.0)
_TIMEOUT_OFF = frozenset({"", "off", "disabled", "none", "null", "0", "0.0"})
LOCAL_REWRITE_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# Old settings.json files may still name a density. It is ignored and not shown.
_IGNORED_SETTING_KEYS: frozenset[str] = frozenset({"banner_density"})
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


class HotkeyBindings(BaseModel):
    """Remaps stored in settings.json. The sample adapter documents its own binds."""

    model_config = ConfigDict(extra="ignore")

    dictation: str = "Right Option"
    speak: str = "Double-tap Left Option"
    cancel: str = "Esc"


def is_remote_rewrite_model(value: str) -> bool:
    """True when the value points at a URL, cloud host, or ollama registry tag."""
    text = value.strip()
    if not text:
        return False
    lower = text.casefold()
    if "://" in lower or lower.startswith("http"):
        return True
    if any(token in lower for token in ("openrouter", "openai.com", "anthropic", "ollama.com")):
        return True
    if ":" in text and "/" not in text and not lower.endswith((".gguf", ".bin")):
        return True
    return False


def is_local_rewrite_model(value: str, models_dir: str | Path) -> bool:
    """True for a models_dir file, an absolute .gguf/.bin, or a local GGUF blob."""
    text = value.strip()
    if not text or is_remote_rewrite_model(text):
        return False
    parts = Path(text).parts
    if ".." in parts:
        return False
    root = Path(models_dir).expanduser().resolve()
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        suffix = candidate.suffix.casefold()
        if suffix in {".gguf", ".bin"}:
            return True
        return _file_starts_with(candidate, b"GGUF")
    try:
        (root / text).resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _file_starts_with(path: Path, magic: bytes) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(magic)) == magic
    except OSError:
        return False


def parse_rewrite_timeout(value: object) -> float | None:
    """None (off) or one of 15 / 30 / 60. Rejects free-form seconds."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().casefold().removesuffix("s")
        if text in _TIMEOUT_OFF:
            return None
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError("rewrite_timeout_seconds must be off or 15, 30, or 60") from exc
    elif isinstance(value, bool):
        raise ValueError("rewrite_timeout_seconds must be off or 15, 30, or 60")
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        raise ValueError("rewrite_timeout_seconds must be off or 15, 30, or 60")
    if number == 0:
        return None
    if number in REWRITE_TIMEOUT_PRESETS:
        return float(int(number))
    raise ValueError("rewrite_timeout_seconds must be off or 15, 30, or 60")


def cycle_rewrite_timeout(current: float | None) -> float | None:
    """Cycle off → 15 → 30 → 60 → off."""
    if current is None:
        return REWRITE_TIMEOUT_PRESETS[0]
    try:
        index = REWRITE_TIMEOUT_PRESETS.index(float(current))
    except ValueError:
        return REWRITE_TIMEOUT_PRESETS[0]
    nxt = index + 1
    if nxt >= len(REWRITE_TIMEOUT_PRESETS):
        return None
    return REWRITE_TIMEOUT_PRESETS[nxt]


def format_rewrite_timeout(value: float | None) -> str:
    if value is None:
        return "off"
    return f"{int(value)}s"


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


def speech_speed_choice(value: float) -> str:
    """Token for a playback speed: ``1``, ``0.5``, ``1.25``."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def speech_speed_label(value: float) -> str:
    """Chooser label: ``1x``, ``0.5x``, ``2x``."""
    return f"{speech_speed_choice(value)}x"


def parse_speech_speed(value: object) -> float:
    """Snap a settings value onto a playback speed. Anything else is refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("tts_speed expects a playback speed")
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError("tts_speed expects a playback speed") from exc
    for allowed in SPEECH_SPEEDS:
        if abs(number - allowed) < 1e-6:
            return allowed
    choices = ", ".join(speech_speed_choice(item) for item in SPEECH_SPEEDS)
    raise ValueError(f"tts_speed must be one of {choices}")


class VoiceSettings(BaseModel):
    """User-editable digivoice config. Stored as settings.json under the data dir."""

    stt_model: str = DEFAULT_MODEL
    tts_voice: str | None = None
    # Playback speed for a readout. Piper length scale is 1 / tts_speed.
    tts_speed: float = 1.0
    rewrite_enabled: bool = False
    rewrite_preset: RewritePreset = "none"
    rewrite_model: str | None = None
    rewrite_runner: RewriteRunnerKind = "auto"
    rewrite_auto_route: bool = False
    # fragment (casefold substring of focused app name) → preset name. Not hard-coded in rewrite.
    rewrite_app_routes: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_REWRITE_APP_ROUTES)
    )
    rewrite_timeout_seconds: float | None = None
    # Feature toggles agents can flip without touching code.
    paste_on_stop: bool = True
    # Word / spelling detection stubs (MVP off; settings only, not wired to STT yet).
    word_detection: bool = False
    spelling_detection: bool = False
    # Status overlay drawn by the Hammerspoon adapter (read from status.json). Display only.
    live_banner: bool = True
    banner_position: BannerPosition = "top-center"
    # Kept so an old settings.json still loads. The icon is the only look; this value is ignored.
    banner_density: BannerDensity = Field(default="retract", exclude=True)
    # False renders the dot-matrix icon as a still frame instead of animating it.
    banner_animations: bool = True
    # Pin keeps the status banner on screen. Off shows it only during a take.
    banner_pinned: bool = False
    # Appearance. system follows DIGIVOICE_THEME, then the OS. Empty palette keeps legacy chrome.
    theme_mode: Literal["dark", "light", "system"] = "system"
    theme_palette: str = ""
    # TUI remaps. Saved with the rest of settings.json. Blank keys are rejected.
    hotkey_bindings: HotkeyBindings = Field(default_factory=HotkeyBindings)

    @field_validator("tts_speed", mode="before")
    @classmethod
    def _speech_speed_is_a_step(cls, value: object) -> float:
        return parse_speech_speed(value)

    @field_validator("banner_density", mode="before")
    @classmethod
    def _ignore_banner_density(cls, value: object) -> str:
        """Any leftover density, including unknown values, does not change the icon."""
        _ = value
        return "retract"

    @field_validator("rewrite_timeout_seconds", mode="before")
    @classmethod
    def _timeout_is_preset_or_off(cls, value: object) -> float | None:
        return parse_rewrite_timeout(value)

    @field_validator("rewrite_model", mode="before")
    @classmethod
    def _rewrite_model_is_local(cls, value: object) -> str | None:
        if value in (None, "", "none", "null"):
            return None
        text = str(value).strip()
        if not text:
            return None
        if is_remote_rewrite_model(text):
            raise ValueError(
                "rewrite_model must be a local file shipped with digivoice "
                "(no URLs, cloud hosts, or ollama tags)"
            )
        if ".." in Path(text).parts:
            raise ValueError("rewrite_model must stay under the digivoice models directory")
        return text


def settings_path(paths: VoicePaths) -> Path:
    return Path(paths.data_dir) / SETTINGS_FILE_NAME


def default_settings() -> VoiceSettings:
    return VoiceSettings()


def visible_setting_keys() -> list[str]:
    """Keys a person can read or change. Density stays loadable and is not one of them."""
    return sorted(name for name in VoiceSettings.model_fields if name not in _IGNORED_SETTING_KEYS)


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
        f"Post-process uses a local GGUF under {paths.models_dir}/ "
        f"(suggested list in setup; default {LOCAL_REWRITE_MODEL_FILE}; "
        "no cloud, URL, or ollama-tag models)."
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
    if key in {"tts_voice"} and text.lower() in {"", "none", "null"}:
        return None
    if key == "rewrite_model":
        if text.lower() in {"", "none", "null"}:
            return None
        if is_remote_rewrite_model(text) or ".." in Path(text).parts:
            raise ValueError(
                "rewrite_model must be a local file shipped with digivoice "
                "(no URLs, cloud hosts, or ollama tags)"
            )
        return text
    if key == "theme_palette":
        from digivoice.themes import PALETTE_IDS

        if text.lower() in {"", "none", "legacy"}:
            return ""
        if text not in PALETTE_IDS:
            raise ValueError(f"theme_palette must be one of the built-in palettes, got {raw!r}")
        return text
    bool_keys = {name for name, field in fields.items() if field.annotation is bool}
    if key in bool_keys:
        lower = text.casefold()
        if lower in _BOOL_TRUE:
            return True
        if lower in _BOOL_FALSE:
            return False
        raise ValueError(f"{key} expects true/false, got {raw!r}")
    if key == "rewrite_timeout_seconds":
        return parse_rewrite_timeout(text)
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
    if key not in VoiceSettings.model_fields or key in _IGNORED_SETTING_KEYS:
        raise KeyError(key)
    current = load_settings(paths)
    value = parse_setting_value(key, raw)
    updated = current.model_copy(update={key: value})
    # Re-validate (Literal presets, etc.).
    settings = VoiceSettings.model_validate(updated.model_dump())
    save_settings(paths, settings)
    return settings


def format_settings_compact(settings: VoiceSettings, paths: VoicePaths) -> str:
    """Scannable grouped summary for the TUI Settings pane (not the full dump)."""
    tts = settings.tts_voice or "(auto)"
    rewrite = (
        f"{settings.rewrite_preset} via {settings.rewrite_runner}"
        if settings.rewrite_enabled
        else "off"
    )
    return "\n".join(
        [
            "■ Models",
            f"  □ stt ..... {settings.stt_model}",
            f"  □ tts ..... {tts}",
            f"  □ rewrite . {rewrite}",
            "",
            "■ Features",
            f"  □ paste on stop . {str(settings.paste_on_stop).lower()}",
            f"  □ live banner .. {str(settings.live_banner).lower()}",
            "",
            "■ Banner",
            f"  □ pin {str(settings.banner_pinned).lower()} ({settings.banner_position})",
            f"  □ animations ... {str(settings.banner_animations).lower()}",
            "",
            "■ Paths",
            f"  □ data ..... {paths.data_dir}",
            f"  □ models ... {paths.models_dir}",
        ]
    )


def format_settings_text(settings: VoiceSettings, paths: VoicePaths) -> str:
    data = settings_public_dict(settings, paths)
    lines = [
        "digivoice settings",
        f"file: {data['paths']['settings_file']}",
        "",
        "models / features",
        f"  stt_model:              {settings.stt_model}",
        f"  tts_voice:              {settings.tts_voice or '(auto / DIGIVOICE_PIPER_VOICE)'}",
        f"  tts_speed:              {speech_speed_label(settings.tts_speed)}",
        f"  rewrite_enabled:        {settings.rewrite_enabled}",
        f"  rewrite_preset:        {settings.rewrite_preset}",
        f"  rewrite_model:         {settings.rewrite_model or LOCAL_REWRITE_MODEL_FILE}",
        f"  rewrite_runner:        {settings.rewrite_runner}",
        f"  rewrite_auto_route:    {settings.rewrite_auto_route}",
        f"  rewrite_app_routes:    {len(settings.rewrite_app_routes)} fragment→preset entries",
        f"  rewrite_timeout_seconds: {format_rewrite_timeout(settings.rewrite_timeout_seconds)}",
        f"  paste_on_stop:          {settings.paste_on_stop}",
        f"  word_detection:         {settings.word_detection}",
        f"  spelling_detection:     {settings.spelling_detection}",
        f"  live_banner:            {settings.live_banner}",
        f"  banner_position:        {settings.banner_position}",
        f"  banner_animations:      {settings.banner_animations}",
        f"  banner_pinned:          {settings.banner_pinned}",
        f"  theme_mode:             {settings.theme_mode}",
        f"  theme_palette:          {settings.theme_palette or '(legacy)'}",
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
