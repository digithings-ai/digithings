"""TTY settings as a path. Enter opens a folder or changes the value. Esc goes up.

Each row carries a one-line explanation. Bools toggle. Short lists cycle.
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
from digivoice.settings import (
    PRESET_LABELS,
    VoiceSettings,
    cycle_rewrite_timeout,
    format_rewrite_timeout,
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
                kind="cycle",
                field="stt_model",
                value=settings.stt_model,
                explain="Which local whisper file transcribes. Enter cycles the suggested list.",
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
            TreeRow(
                name="words",
                kind="toggle",
                field="word_detection",
                value=_on_off(settings.word_detection),
                explain="Flag odd words after dictation. Stored only, not wired to speech yet.",
            ),
            TreeRow(
                name="spelling",
                kind="toggle",
                field="spelling_detection",
                value=_on_off(settings.spelling_detection),
                explain="Flag spelling after dictation. Stored only, not wired to speech yet.",
            ),
        ]
    if here == "/settings/rewrite":
        model = settings.rewrite_model or "auto"
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
                kind="cycle",
                field="rewrite_preset",
                value=settings.rewrite_preset,
                explain="How the cleaned-up text should read.",
            ),
            TreeRow(
                name="model",
                kind="cycle",
                field="rewrite_model",
                value=model,
                explain="On-device model file. Enter cycles the suggested list. Never a cloud URL.",
            ),
            TreeRow(
                name="runner",
                kind="cycle",
                field="rewrite_runner",
                value=settings.rewrite_runner,
                explain="llama.cpp or local ollama on this machine.",
            ),
            TreeRow(
                name="match-app",
                kind="toggle",
                field="rewrite_auto_route",
                value=_on_off(settings.rewrite_auto_route),
                explain="On uses the front app's style. Off always uses the style above.",
            ),
            TreeRow(
                name="timeout",
                kind="cycle",
                field="rewrite_timeout_seconds",
                value=format_rewrite_timeout(settings.rewrite_timeout_seconds),
                explain="How long rewrite may run. Off, or 15, 30, or 60 seconds.",
            ),
            TreeRow(
                name="apps",
                kind="dir",
                explain="Front-app name to rewrite style. Enter cycles that app's style.",
            ),
        ]
    if here == "/settings/rewrite/apps":
        rows: list[TreeRow] = []
        for name in sorted(settings.rewrite_app_routes):
            rows.append(
                TreeRow(
                    name=name,
                    kind="cycle",
                    field=name,
                    value=settings.rewrite_app_routes[name],
                    explain="When this app is in front, rewrite uses this style.",
                )
            )
        return rows
    if here == "/settings/banner":
        return [
            TreeRow(
                name="show",
                kind="toggle",
                field="live_banner",
                value=_on_off(settings.live_banner),
                explain="Draw the banner. Off hides it.",
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
                explain="Retract hides until needed. Full stays up.",
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


def _changed(settings: VoiceSettings, row: TreeRow, typed: str | None) -> VoiceSettings | None:
    data = settings.model_dump(mode="json")
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
        picked = choose(
            title,
            [row.label() for row in rows],
            stdin,
            stdout,
            subtitle="Enter opens a folder or changes the value. Esc goes up.",
            detail=True,
        )
        if picked is None:
            stack.pop()
            continue
        row = rows[picked]
        if row.kind == "dir":
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
        if row.field in {"stt_model", "rewrite_model"} and install is not None:
            entry = _catalog_entry(row.field, str(getattr(nxt, row.field) or ""))
            if entry is not None:
                dest = Path(paths.models_dir) / entry.filename
                if not dest.is_file():
                    try:
                        install(paths, entry, stdout)
                    except (OSError, ValueError) as exc:
                        stdout.write(f"  could not install {entry.filename}: {exc}\n")
                        stdout.flush()
                        continue
        settings = nxt
        save_settings(paths, settings)
