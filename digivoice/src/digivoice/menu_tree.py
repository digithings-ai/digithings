"""TTY settings as a path. Enter opens a folder, a list, or changes a value.

A model row opens the catalog. Size and the recommended flag are on each
row. A missing file downloads only after confirm. Esc goes up.
The numbered ``setup`` wizard stays for pipes and agents.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel, ConfigDict

from digivoice.catalog import REWRITE_CATALOG, STT_CATALOG, CatalogModel
from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL
from digivoice.settings import (
    LOCAL_REWRITE_MODEL_FILE,
    PRESET_LABELS,
    VoiceSettings,
    cycle_rewrite_timeout,
    load_settings,
    save_settings,
)
from digivoice.tui import choose

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
_DENSITIES: tuple[str, ...] = ("retract", "full")
_STT_IDS: tuple[str, ...] = tuple(item.id for item in STT_CATALOG)
_REWRITE_FILES: tuple[str, ...] = tuple(item.filename for item in REWRITE_CATALOG)


class TreeRow(BaseModel):
    """One entry under a settings path."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    explain: str
    value: str = ""
    field: str = ""
    choice: str = ""

    def label(self) -> str:
        if self.kind == "dir":
            head = f"{self.name}/"
        elif self.value:
            head = f"{self.name}  [{self.value}]"
        else:
            head = self.name
        return f"{head} ({self.explain})"


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


def rows_at(settings: VoiceSettings, path: str) -> list[TreeRow]:
    """Rows for one settings path. Unknown paths are empty."""
    here = _norm(path)
    if here == "/settings":
        return [
            TreeRow(
                name="speech",
                kind="dir",
                explain="Dictation model, Piper voice, and what happens when a take stops.",
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
                explain="How the Mac keys are bound. Nothing here is editable.",
            ),
        ]
    if here == "/settings/speech":
        voice = settings.tts_voice or "auto"
        return [
            TreeRow(
                name="model",
                kind="pick",
                value=_model_title("stt_model", settings.stt_model),
                explain="Local whisper file. Enter opens the list. A download asks first.",
            ),
            TreeRow(
                name="voice",
                kind="text",
                field="tts_voice",
                value=voice,
                explain="Piper voice file. Blank means auto. Enter types a name.",
            ),
            TreeRow(
                name="paste",
                kind="toggle",
                field="paste_on_stop",
                value=_on_off(settings.paste_on_stop),
                explain="Paste the words when dictation stops.",
            ),
        ]
    if here == "/settings/speech/model":
        return _model_choices("stt_model")
    if here == "/settings/rewrite":
        return [
            TreeRow(
                name="enabled",
                kind="toggle",
                field="rewrite_enabled",
                value=_on_off(settings.rewrite_enabled),
                explain="On rewrites with the local model. Off pastes the words as spoken.",
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
                explain="On-device model. Enter opens the list. A download asks first.",
            ),
        ]
    if here == "/settings/rewrite/style":
        return _style_choices()
    if here == "/settings/rewrite/model":
        return _model_choices("rewrite_model")
    if here == "/settings/banner":
        return [
            TreeRow(
                name="show",
                kind="toggle",
                field="live_banner",
                value=_on_off(settings.live_banner),
                explain="Draw the banner during a take. Off hides it entirely.",
            ),
            TreeRow(
                name="pin",
                kind="toggle",
                field="banner_pinned",
                value=_on_off(settings.banner_pinned),
                explain="Keep the banner on screen. Off shows it only while a take is active.",
            ),
            TreeRow(
                name="position",
                kind="cycle",
                field="banner_position",
                value=settings.banner_position,
                explain="Where the banner sits on the screen.",
            ),
            TreeRow(
                name="density",
                kind="cycle",
                field="banner_density",
                value=settings.banner_density,
                explain="Retract hides after a take. Full stays until you collapse it.",
            ),
            TreeRow(
                name="animations",
                kind="toggle",
                field="banner_animations",
                value=_on_off(settings.banner_animations),
                explain="Animate the banner mark. Off holds a still frame.",
            ),
        ]
    if here == "/settings/hotkeys":
        return [
            TreeRow(
                name="dictation",
                kind="note",
                explain="Right Option starts and stops dictation.",
            ),
            TreeRow(
                name="speak",
                kind="note",
                explain="Double-tap Left Option speaks the selection.",
            ),
            TreeRow(
                name="cancel",
                kind="note",
                explain="Esc during a take discards it. Nothing is pasted.",
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


def _plain(text: str) -> str:
    return text.replace(" (default)", "").replace("(", "").replace(")", "")


def _model_title(field: str, current: str) -> str:
    """Name shown on the model row. Empty current means the recommended file."""
    catalog = STT_CATALOG if field == "stt_model" else REWRITE_CATALOG
    recommended = DEFAULT_MODEL if field == "stt_model" else LOCAL_REWRITE_MODEL_FILE
    needle = current or recommended
    for item in catalog:
        if item.id == needle or item.filename == needle:
            return _short_title(item.title)
    return current or _short_title(catalog[0].title)


_STYLE_EXPLAIN: dict[str, str] = {
    "email": "Clear greeting, paragraphs, and a sign-off.",
    "sms": "Short and plain.",
    "professional": "Polished tone for a post.",
    "coding": "Structured notes for a coding agent.",
    "blog": "Readable prose.",
    "none": "Light cleanup only.",
}


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


def _model_choices(field: str) -> list[TreeRow]:
    catalog = STT_CATALOG if field == "stt_model" else REWRITE_CATALOG
    recommended = DEFAULT_MODEL if field == "stt_model" else LOCAL_REWRITE_MODEL_FILE
    rows: list[TreeRow] = []
    for item in catalog:
        is_rec = item.id == recommended or item.filename == recommended
        size = f"{item.size_hint} · recommended" if is_rec else item.size_hint
        stored = item.id if field == "stt_model" else item.filename
        rows.append(
            TreeRow(
                name=_short_title(item.title),
                kind="choice",
                field=field,
                value=size,
                choice=stored,
                explain=_plain(item.best_for),
            )
        )
    return rows


def _list_cursor(settings: VoiceSettings, path: str, rows: list[TreeRow]) -> int:
    here = _norm(path)
    if here == "/settings/speech/model":
        current = settings.stt_model
    elif here == "/settings/rewrite/model":
        current = settings.rewrite_model or LOCAL_REWRITE_MODEL_FILE
    elif here == "/settings/rewrite/style":
        current = settings.rewrite_preset
    else:
        return 0
    for index, row in enumerate(rows):
        if row.choice == current:
            return index
    return 0


def _missing_catalog(paths: VoicePaths, row: TreeRow) -> CatalogModel | None:
    if row.field not in {"stt_model", "rewrite_model"}:
        return None
    entry = _catalog_entry(row.field, row.choice)
    if entry is None:
        return None
    dest = Path(paths.models_dir) / entry.filename
    if dest.is_file():
        return None
    return entry


def _changed(settings: VoiceSettings, row: TreeRow, typed: str | None) -> VoiceSettings | None:
    data = settings.model_dump(mode="json")
    if row.kind == "choice":
        if not row.choice:
            return None
        data[row.field] = row.choice
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
            "banner_density": _DENSITIES,
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
        "banner_density",
    }


def _read_voice(stdin: TextIO, stdout: TextIO, current: str | None) -> str | None:
    hint = current if current else "auto"
    stdout.write(f"  voice [{hint}]  blank keeps it, none clears it\n")
    stdout.flush()
    try:
        raw = stdin.readline()
    except (OSError, ValueError):
        return None
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.casefold() in {"none", "null", "-"}:
        return ""
    return text


def browse_settings(
    paths: VoicePaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    *,
    install: InstallFn | None = None,
    start: str = "/settings",
) -> None:
    """Walk ``/settings/...``. Esc at the root returns to the caller."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    settings = load_settings(paths)
    stack = [_norm(start)]
    while stack:
        path = stack[-1]
        rows = rows_at(settings, path)
        if not rows:
            stack.pop()
            continue
        title = path
        choosing = any(row.kind == "choice" for row in rows)
        subtitle = (
            "Enter selects. A missing file asks before it downloads. Esc goes up."
            if choosing
            else "Enter opens a folder or changes the value. Esc goes up."
        )
        picked = choose(
            title,
            [row.label() for row in rows],
            stdin,
            stdout,
            subtitle=subtitle,
            detail=True,
            start_at=_list_cursor(settings, path, rows),
        )
        if picked is None:
            stack.pop()
            continue
        row = rows[picked]
        if row.kind in {"dir", "pick"}:
            stack.append(f"{path}/{row.name}")
            continue
        if row.kind == "note":
            continue
        typed: str | None = None
        if row.kind == "text":
            typed = _read_voice(stdin, stdout, settings.tts_voice)
        nxt = _changed(settings, row, typed)
        if nxt is None:
            continue
        if row.kind == "choice":
            missing = _missing_catalog(paths, row)
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
