"""TTY settings as a path. Enter opens a folder or a chooser.

A value is saved only when that chooser is picked. Enter on the parent
does not toggle or cycle. After a choice or cancel, the parent stays on
the row that was opened. A model row opens the catalog. Size and the
recommended flag are on each row. A chooser opens on the saved row. A file
in the models directory, or the same filename under LM Studio, Ollama, or
MLX, is marked downloaded. The numbered menu still asks before it fetches
a missing speech or rewrite file. Esc goes up. The numbered ``setup`` wizard
stays for pipes and agents.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel, ConfigDict

from digivoice.bindings import binding_conflict, binding_warning, parse_binding, set_hotkey_capture
from digivoice.catalog import REWRITE_CATALOG, STT_CATALOG, VOICE_CATALOG, CatalogModel, find_voice
from digivoice.installed_models import InstalledModel, discover_installed_models, local_filenames
from digivoice.models import VoicePaths
from digivoice.nav import norm_path
from digivoice.paths import DEFAULT_MODEL
from digivoice.reload import run_reload
from digivoice.settings import (
    LOCAL_REWRITE_MODEL_FILE,
    PRESET_LABELS,
    SPEECH_SPEEDS,
    VoiceSettings,
    cycle_rewrite_timeout,
    format_rewrite_timeout,
    load_settings,
    save_settings,
    speech_speed_choice,
    speech_speed_label,
)
from digivoice.themes import PALETTE_IDS
from digivoice.tui import MenuBlock, capture_binding, choose

InstallFn = Callable[[VoicePaths, CatalogModel, TextIO | None], str]

_PRESETS: tuple[str, ...] = tuple(PRESET_LABELS)
_RUNNERS: tuple[str, ...] = ("auto", "ollama", "llama.cpp")
_POSITIONS: tuple[str, ...] = (
    "top-center",
    "top-left",
    "top-right",
    "middle-left",
    "middle-right",
    "bottom-center",
    "bottom-left",
    "bottom-right",
    "center",
)
_STT_IDS: tuple[str, ...] = tuple(item.id for item in STT_CATALOG)
_REWRITE_FILES: tuple[str, ...] = tuple(item.filename for item in REWRITE_CATALOG)
# Local Piper voices. The OpenTUI download page fetches these files. The
# numbered menu still saves a voice name without fetching.
_MODEL_FIELDS = frozenset({"stt_model", "rewrite_model", "tts_voice"})
_BOOL_FIELDS = frozenset(
    {
        "paste_on_stop",
        "rewrite_enabled",
        "live_banner",
        "banner_pinned",
        "banner_animations",
    }
)


class TreeRow(BaseModel):
    """One entry under a settings path."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    explain: str
    value: str = ""
    field: str = ""
    choice: str = ""
    downloaded: bool = False

    def label(self) -> str:
        if self.kind == "dir":
            head = f"{self.name}/"
        elif self.value:
            head = f"{self.name}  [{self.value}]"
        else:
            head = self.name
        return f"{head} ({self.explain})"

    def as_block(self, path: str) -> MenuBlock:
        """Action, slash path, then the value (or the note) as metadata."""
        meta = self.explain if self.kind == "note" else self.value
        if self.kind == "choice" and self.field in _MODEL_FIELDS and self.choice:
            leaf = self.choice
        else:
            leaf = self.name
        return MenuBlock(action=self.name, path=f"{path}/{leaf}", meta=meta)


def _norm(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    return "/" + "/".join(parts)


def _on_off(value: bool) -> str:
    return "on" if value else "off"


def _next(current: str, choices: tuple[str, ...]) -> str:
    try:
        index = choices.index(current)
    except ValueError:
        return choices[0]
    return choices[(index + 1) % len(choices)]


def rows_at(
    settings: VoiceSettings,
    path: str,
    models_dir: Path | None = None,
    installed: Sequence[InstalledModel] | None = None,
    on_disk: set[str] | None = None,
) -> list[TreeRow]:
    """Rows for one settings path. Unknown paths are empty."""
    here = _norm(path)
    if here == "/settings":
        return [
            TreeRow(
                name="speech",
                kind="dir",
                explain="Dictation model, Piper voice, reading speed, and what happens when a take stops.",
            ),
            TreeRow(
                name="rewrite",
                kind="dir",
                explain="Optional local cleanup of the words after dictation.",
            ),
            TreeRow(
                name="banner",
                kind="dir",
                explain="The on-screen status while you dictate.",
            ),
            TreeRow(
                name="hotkeys",
                kind="dir",
                explain="Mac key binds. Enter a row, then type the key.",
            ),
            TreeRow(
                name="theme",
                kind="dir",
                explain="Palette for the banner and this terminal. Mode stays dark, light, or system.",
            ),
        ]
    if here == "/settings/speech":
        voice = settings.tts_voice or "auto"
        return [
            TreeRow(
                name="model",
                kind="pick",
                value=_model_title("stt_model", settings.stt_model),
                explain="Local whisper file. Enter opens the list.",
            ),
            TreeRow(
                name="voice",
                kind="pick",
                value=voice,
                explain="Piper voice. Enter opens the list.",
            ),
            TreeRow(
                name="speed",
                kind="pick",
                value=speech_speed_label(settings.tts_speed),
                explain="How fast a readout plays. Enter opens the list.",
            ),
            TreeRow(
                name="paste",
                kind="pick",
                value=_on_off(settings.paste_on_stop),
                explain="Paste the words when dictation stops. Enter opens on or off.",
            ),
        ]
    if here == "/settings/speech/model":
        return _model_choices("stt_model", installed or (), models_dir, on_disk)
    if here == "/settings/speech/voice":
        return _voice_choices(settings, models_dir, on_disk)
    if here == "/settings/speech/speed":
        return _speed_choices()
    if here == "/settings/speech/paste":
        return _bool_choices(
            "paste_on_stop",
            "Paste the words when dictation stops.",
            "Leave the words in the banner only.",
        )
    if here == "/settings/rewrite":
        return [
            TreeRow(
                name="enabled",
                kind="pick",
                value=_on_off(settings.rewrite_enabled),
                explain=("On lightly fixes grammar and spelling. Off pastes the words as spoken."),
            ),
            TreeRow(
                name="style",
                kind="pick",
                value=settings.rewrite_preset,
                explain="How the cleaned-up text should read. Enter opens the list.",
            ),
            TreeRow(
                name="model",
                kind="pick",
                value=_model_title("rewrite_model", settings.rewrite_model or ""),
                explain="On-device model. Enter opens the list.",
            ),
            TreeRow(
                name="timeout",
                kind="pick",
                value=format_rewrite_timeout(settings.rewrite_timeout_seconds),
                explain="How long a rewrite may run. Enter opens off, 15, 30, or 60.",
            ),
        ]
    if here == "/settings/rewrite/enabled":
        return _bool_choices(
            "rewrite_enabled",
            "Lightly fix grammar and spelling. Do not add content.",
            "Paste the words as spoken.",
        )
    if here == "/settings/rewrite/style":
        return _style_choices()
    if here == "/settings/rewrite/model":
        return _model_choices("rewrite_model", installed or (), models_dir, on_disk)
    if here == "/settings/rewrite/timeout":
        return _timeout_choices()
    if here == "/settings/banner":
        return [
            TreeRow(
                name="show",
                kind="pick",
                value=_on_off(settings.live_banner),
                explain="Draw the banner during a take. Off hides it entirely.",
            ),
            TreeRow(
                name="pin",
                kind="pick",
                value=_on_off(settings.banner_pinned),
                explain="On keeps the icon visible. Off retracts it when voice is idle.",
            ),
            TreeRow(
                name="position",
                kind="pick",
                value=settings.banner_position,
                explain="Where the banner sits on the screen.",
            ),
            TreeRow(
                name="animations",
                kind="pick",
                value=_on_off(settings.banner_animations),
                explain="Animate the banner mark. Off holds a still frame.",
            ),
        ]
    if here == "/settings/banner/show":
        return _bool_choices(
            "live_banner",
            "Draw the banner during a take.",
            "Hide the banner entirely.",
        )
    if here == "/settings/banner/pin":
        return _bool_choices(
            "banner_pinned",
            "Keep the icon visible.",
            "Retract the icon when voice is idle.",
        )
    if here == "/settings/banner/position":
        return _named_choices("banner_position", _POSITIONS, "Where the banner sits.")
    if here == "/settings/banner/animations":
        return _bool_choices(
            "banner_animations",
            "Animate the banner mark.",
            "Hold a still frame.",
        )
    if here == "/settings/theme":
        palette = settings.theme_palette or "legacy"
        return [
            TreeRow(
                name="mode",
                kind="pick",
                value=settings.theme_mode,
                explain="dark, light, or system. system follows DIGIVOICE_THEME, then the OS.",
            ),
            TreeRow(
                name="palette",
                kind="pick",
                value=palette,
                explain="Named OpenCode palette. legacy keeps the built-in banner chrome.",
            ),
        ]
    if here == "/settings/theme/mode":
        return _named_choices(
            "theme_mode",
            ("dark", "light", "system"),
            "Which appearance mode the banner and the terminal use.",
        )
    if here == "/settings/theme/palette":
        names = ("legacy",) + PALETTE_IDS
        return _named_choices(
            "theme_palette",
            names,
            "One palette for the banner and the terminal.",
        )
    if here == "/settings/hotkeys":
        bindings = settings.hotkey_bindings
        return [
            TreeRow(
                name="dictation",
                kind="capture",
                field="dictation",
                value=bindings.dictation,
                explain="Starts and stops dictation. Press the key, or type its name.",
            ),
            TreeRow(
                name="speak",
                kind="capture",
                field="speak",
                value=bindings.speak,
                explain="Speaks the selection. Press the key, or type its name.",
            ),
            TreeRow(
                name="cancel",
                kind="capture",
                field="cancel",
                value=bindings.cancel,
                explain="Discards the active take. Press the key, or type its name.",
            ),
        ]
    return []


def _catalog_entry(field: str, value: str) -> CatalogModel | None:
    catalog = STT_CATALOG if field == "stt_model" else REWRITE_CATALOG
    for item in catalog:
        if item.id == value or item.filename == value:
            return item
    return None


def _short_title(title: str) -> str:
    return title.replace(" (default)", "")


def _display_name(title: str) -> str:
    """Model name with the language word removed. That word lives on the meta line."""
    name = _short_title(title).strip()
    for suffix in (" English", " multilingual"):
        if name.endswith(suffix):
            trimmed = name[: -len(suffix)].strip()
            return trimmed or name
    return name


def _plain(text: str) -> str:
    return text.replace(" (default)", "").replace("(", "").replace(")", "")


def _model_title(field: str, current: str) -> str:
    """Name shown on the model row. Empty current means the recommended file."""
    catalog = STT_CATALOG if field == "stt_model" else REWRITE_CATALOG
    recommended = DEFAULT_MODEL if field == "stt_model" else LOCAL_REWRITE_MODEL_FILE
    needle = current or recommended
    for item in catalog:
        if item.id == needle or item.filename == needle:
            return _display_name(item.title)
    candidate = Path(needle)
    if candidate.is_absolute():
        return candidate.stem or candidate.name
    return current or _display_name(catalog[0].title)


_STYLE_EXPLAIN: dict[str, str] = {
    "email": "Format as an email. Do not add a subject or new points.",
    "sms": "Keep it short, in the dictated words.",
    "professional": "Format as a short post. Do not add new points.",
    "coding": "Format the code or technical prose already dictated.",
    "blog": "Format as prose. Do not add a title or new points.",
    "none": "Light grammar and spelling only.",
}


def _bool_choices(field: str, on_explain: str, off_explain: str) -> list[TreeRow]:
    return [
        TreeRow(name="on", kind="choice", field=field, choice="on", explain=on_explain),
        TreeRow(name="off", kind="choice", field=field, choice="off", explain=off_explain),
    ]


def _named_choices(field: str, names: tuple[str, ...], explain: str) -> list[TreeRow]:
    return [
        TreeRow(name=name, kind="choice", field=field, choice=name, explain=explain)
        for name in names
    ]


def _timeout_choices() -> list[TreeRow]:
    """Rewrite may run with no timer, or for 15, 30, or 60 seconds."""
    return [
        TreeRow(
            name=name,
            kind="choice",
            field="rewrite_timeout_seconds",
            choice=name,
            explain="Do not stop a rewrite on a timer."
            if name == "off"
            else "Stop a rewrite after this many seconds.",
        )
        for name in ("off", "15", "30", "60")
    ]


def _style_choices() -> list[TreeRow]:
    return [
        TreeRow(
            name=name,
            kind="choice",
            field="rewrite_preset",
            choice=name,
            explain=_STYLE_EXPLAIN.get(name, "Rewrite style."),
        )
        for name in _PRESETS
    ]


def _language_label(languages: str) -> str:
    if languages == "en":
        return "English"
    return languages


_SOURCE_EXPLAIN = {
    "lmstudio": "Installed by LM Studio",
    "ollama": "Installed by Ollama",
    "mlxstudio": "Installed by MLX Studio",
}


def _on_disk(models_dir: Path | None, filename: str) -> bool:
    if models_dir is None or not filename:
        return False
    return (Path(models_dir) / Path(filename).name).is_file()


def _ready(
    models_dir: Path | None,
    filename: str,
    on_disk: set[str] | None = None,
) -> bool:
    """True when the models directory or an install root already has this file."""
    if _on_disk(models_dir, filename):
        return True
    if not filename or not on_disk:
        return False
    return Path(filename).name.casefold() in on_disk


def _model_choices(
    field: str,
    installed: Sequence[InstalledModel] = (),
    models_dir: Path | None = None,
    on_disk: set[str] | None = None,
) -> list[TreeRow]:
    catalog = STT_CATALOG if field == "stt_model" else REWRITE_CATALOG
    kind = "stt" if field == "stt_model" else "rewrite"
    recommended = DEFAULT_MODEL if field == "stt_model" else LOCAL_REWRITE_MODEL_FILE
    rows: list[TreeRow] = []
    seen: set[str] = set()
    for item in catalog:
        stored = item.id if field == "stt_model" else item.filename
        if stored in seen:
            continue
        seen.add(stored)
        is_rec = item.id == recommended or item.filename == recommended
        lang = _language_label(item.languages)
        size = (
            f"{lang} · {item.size_hint} · recommended" if is_rec else f"{lang} · {item.size_hint}"
        )
        rows.append(
            TreeRow(
                name=_display_name(item.title),
                kind="choice",
                field=field,
                value=size,
                choice=stored,
                explain=_plain(item.best_for),
                downloaded=_ready(models_dir, item.filename, on_disk),
            )
        )
    for item in installed:
        if item.kind != kind or item.path in seen:
            continue
        seen.add(item.path)
        lang = _language_label(item.languages)
        rows.append(
            TreeRow(
                name=item.name,
                kind="choice",
                field=field,
                value=f"{lang} · installed",
                choice=item.path,
                explain=_SOURCE_EXPLAIN.get(item.source, "Installed locally"),
                downloaded=True,
            )
        )
    return rows


def _voice_choices(
    settings: VoiceSettings,
    models_dir: Path | None,
    on_disk: set[str] | None = None,
) -> list[TreeRow]:
    """One row per Piper voice. `auto` is the saved empty value."""
    rows: list[TreeRow] = []
    seen: set[str] = set()

    def add(choice: str, name: str, explain: str, *, downloaded: bool = False) -> None:
        if not choice or choice in seen:
            return
        seen.add(choice)
        rows.append(
            TreeRow(
                name=name,
                kind="choice",
                field="tts_voice",
                choice=choice,
                value=explain,
                explain=explain,
                downloaded=downloaded,
            )
        )

    add("auto", "auto", "First Piper file on disk")
    for item in VOICE_CATALOG:
        add(
            item.filename,
            _display_name(item.title),
            "English",
            downloaded=_ready(models_dir, item.filename, on_disk),
        )
    if models_dir is not None and models_dir.is_dir():
        for path in sorted(models_dir.glob("*.onnx")):
            add(path.name, path.stem, "Installed Piper voice", downloaded=True)
    current = (settings.tts_voice or "").strip()
    if current:
        present = Path(current).expanduser().is_file() or _ready(models_dir, current, on_disk)
        add(current, Path(current).stem or current, "Saved Piper voice", downloaded=present)
    return rows


def _speed_choices() -> list[TreeRow]:
    """Playback speeds. The row name is the label (``1x``); the choice is the number."""
    return [
        TreeRow(
            name=speech_speed_label(speed),
            kind="choice",
            field="tts_speed",
            choice=speech_speed_choice(speed),
            explain="How fast a readout plays.",
        )
        for speed in SPEECH_SPEEDS
    ]


def _list_cursor(settings: VoiceSettings, path: str, rows: list[TreeRow]) -> int:
    here = _norm(path)
    current = ""
    if here == "/settings/speech/model":
        current = settings.stt_model
    elif here == "/settings/speech/voice":
        current = settings.tts_voice or "auto"
    elif here == "/settings/speech/speed":
        current = speech_speed_choice(settings.tts_speed)
    elif here == "/settings/speech/paste":
        current = _on_off(settings.paste_on_stop)
    elif here == "/settings/rewrite/enabled":
        current = _on_off(settings.rewrite_enabled)
    elif here == "/settings/rewrite/model":
        current = settings.rewrite_model or LOCAL_REWRITE_MODEL_FILE
    elif here == "/settings/rewrite/style":
        current = settings.rewrite_preset
    elif here == "/settings/rewrite/timeout":
        seconds = settings.rewrite_timeout_seconds
        current = "off" if seconds is None else str(int(seconds))
    elif here == "/settings/banner/show":
        current = _on_off(settings.live_banner)
    elif here == "/settings/banner/pin":
        current = _on_off(settings.banner_pinned)
    elif here == "/settings/banner/position":
        current = settings.banner_position
    elif here == "/settings/banner/animations":
        current = _on_off(settings.banner_animations)
    elif here == "/settings/theme/mode":
        current = settings.theme_mode
    elif here == "/settings/theme/palette":
        current = settings.theme_palette or "legacy"
    else:
        return 0
    for index, row in enumerate(rows):
        if row.choice == current:
            return index
    return 0


def _pending_download(
    paths: VoicePaths,
    row: TreeRow,
    on_disk: set[str] | None = None,
) -> CatalogModel | None:
    """Catalog file the OpenTUI download page should fetch. None when it is on disk."""
    if row.field == "tts_voice":
        if not row.choice or row.choice == "auto":
            return None
        entry = find_voice(row.choice)
        if entry is None:
            return None
        if _ready(Path(paths.models_dir), entry.filename, on_disk):
            return None
        return entry
    return _missing_catalog(paths, row, on_disk)


def _missing_catalog(
    paths: VoicePaths,
    row: TreeRow,
    on_disk: set[str] | None = None,
) -> CatalogModel | None:
    if row.field not in {"stt_model", "rewrite_model"}:
        return None
    entry = _catalog_entry(row.field, row.choice)
    if entry is None:
        return None
    if _ready(Path(paths.models_dir), entry.filename, on_disk):
        return None
    return entry


def _changed(settings: VoiceSettings, row: TreeRow, typed: str | None) -> VoiceSettings | None:
    data = settings.model_dump(mode="json")
    if row.kind == "choice":
        if not row.choice:
            return None
        if row.field == "tts_voice" and row.choice == "auto":
            data[row.field] = None
        elif row.field == "theme_palette" and row.choice == "legacy":
            data[row.field] = ""
        elif row.field in _BOOL_FIELDS:
            data[row.field] = row.choice == "on"
        else:
            data[row.field] = row.choice
        return VoiceSettings.model_validate(data)
    if row.kind == "capture":
        if typed is None or not typed.strip():
            return None
        cleaned = typed.strip()
        if parse_binding(cleaned) is None:
            return None
        bindings = dict(data.get("hotkey_bindings") or {})
        bindings[row.field] = cleaned
        data["hotkey_bindings"] = bindings
        return VoiceSettings.model_validate(data)
    if row.kind == "toggle":
        data[row.field] = not bool(getattr(settings, row.field))
    elif row.kind == "text":
        if typed is None:
            return None
        data[row.field] = typed or None
    elif row.kind == "cycle" and row.field == "rewrite_timeout_seconds":
        data[row.field] = cycle_rewrite_timeout(settings.rewrite_timeout_seconds)
    elif row.kind == "cycle" and _norm_field_is_route(row):
        routes = dict(settings.rewrite_app_routes)
        routes[row.field] = _next(routes.get(row.field, "none"), _PRESETS)
        data["rewrite_app_routes"] = routes
    elif row.kind == "cycle":
        choices = {
            "stt_model": _STT_IDS,
            "rewrite_preset": _PRESETS,
            "rewrite_model": _REWRITE_FILES,
            "rewrite_runner": _RUNNERS,
            "banner_position": _POSITIONS,
        }[row.field]
        current = "" if data.get(row.field) is None else str(data.get(row.field))
        data[row.field] = _next(current, choices)
    else:
        return None
    return VoiceSettings.model_validate(data)


def _norm_field_is_route(row: TreeRow) -> bool:
    return row.field not in {
        "stt_model",
        "rewrite_preset",
        "rewrite_model",
        "rewrite_runner",
        "rewrite_timeout_seconds",
        "banner_position",
    }


def _stack_for(
    settings: VoiceSettings,
    start: str,
    models_dir: Path | None = None,
    installed: Sequence[InstalledModel] | None = None,
) -> list[str]:
    """Folders from ``/settings`` down to ``start``. A leaf stays on its parent."""
    path = _norm(start)
    if not path.startswith("/settings"):
        return ["/settings"]
    chain = ["/settings"]
    cursor = "/settings"
    for part in [piece for piece in path.split("/") if piece][1:]:
        rows = rows_at(settings, cursor, models_dir, installed)
        match = next((row for row in rows if row.name == part), None)
        if match is None or match.kind not in {"dir", "pick"}:
            break
        cursor = f"{cursor}/{part}"
        chain.append(cursor)
    return chain


def browse_settings(
    paths: VoicePaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    *,
    install: InstallFn | None = None,
    start: str = "/settings",
    on_path: Callable[[str], None] | None = None,
    installed: Sequence[InstalledModel] | None = None,
    home: Path | None = None,
) -> None:
    """Walk ``/settings/...``. Esc at the root returns to the caller."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    settings = load_settings(paths)
    models_dir = Path(paths.models_dir)
    root = home or Path.home()
    present = local_filenames(root, os.environ)
    if installed is None:
        installed = discover_installed_models(root, os.environ)
    stack = _stack_for(settings, start, models_dir, installed)
    # Parent screens remember the row that was opened. A redraw does not jump to 0.
    cursors: dict[str, int] = {}
    while stack:
        path = stack[-1]
        rows = rows_at(settings, path, models_dir, installed, present)
        if not rows:
            stack.pop()
            continue
        title = path.rsplit("/", 1)[-1]
        picked = choose(
            title,
            stdin=stdin,
            stdout=stdout,
            subtitle=path,
            blocks=[row.as_block(path) for row in rows],
            start_at=cursors.get(path, _list_cursor(settings, path, rows)),
        )
        if picked is None:
            stack.pop()
            continue
        if isinstance(picked, str) and picked.startswith("/"):
            jumped = norm_path(picked)
            if jumped.startswith("/settings"):
                stack[:] = _stack_for(settings, jumped, models_dir, installed)
                continue
            if on_path is not None:
                on_path(jumped)
            return
        if not isinstance(picked, int) or not 0 <= picked < len(rows):
            continue
        cursors[path] = picked
        row = rows[picked]
        if row.kind in {"dir", "pick"}:
            stack.append(f"{path}/{row.name}")
            continue
        if row.kind == "capture":
            set_hotkey_capture(paths.data_dir, True)
            try:
                bound = capture_binding(
                    title,
                    [item.as_block(path) for item in rows],
                    picked,
                    stdin,
                    stdout,
                    subtitle=path,
                )
            finally:
                set_hotkey_capture(paths.data_dir, False)
            previous = str(getattr(settings.hotkey_bindings, row.field))
            current = {
                "dictation": settings.hotkey_bindings.dictation,
                "speak": settings.hotkey_bindings.speak,
                "cancel": settings.hotkey_bindings.cancel,
            }
            warning = binding_warning(row.field, bound, previous) if bound else None
            if warning is None and bound:
                warning = binding_conflict(row.field, bound, current)
            if warning:
                stdout.write(f"  {warning}\n")
                stdout.flush()
                continue
            nxt = _changed(settings, row, bound)
            if nxt is None:
                continue
            settings = nxt
            save_settings(paths, settings)
            run_reload(sys.platform, Path.home(), dict(os.environ))
            continue
        typed: str | None = None
        nxt = _changed(settings, row, typed)
        if nxt is None:
            continue
        if row.kind == "choice":
            missing = _missing_catalog(paths, row, present)
            if missing is not None:
                if install is None:
                    stdout.write(f"  {missing.filename} is not on disk\n")
                    stdout.flush()
                    continue
                answer = choose(
                    _short_title(missing.title),
                    [f"Download ({missing.size_hint})", "Back"],
                    stdin,
                    stdout,
                    subtitle="Nothing downloads until you confirm.",
                )
                if answer != 0:
                    continue
                try:
                    install(paths, missing, stdout)
                except (OSError, ValueError) as exc:
                    stdout.write(f"  could not install {missing.filename}: {exc}\n")
                    stdout.flush()
                    continue
            settings = nxt
            save_settings(paths, settings)
            stack.pop()
            continue
        settings = nxt
        save_settings(paths, settings)
