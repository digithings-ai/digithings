"""Interactive `digivoice setup` wizard plus the non-interactive agent path.

The wizard walks every VoiceSettings field grouped into Models / Features /
Hotkeys (docs) / Review & save / Doctor / Quit, per
`digivoice/mocks/cli-setup-wizard.md`. Agents and CI drive the same content
without a TTY via `digivoice setup --print` (or
`DIGIVOICE_SETUP_NONINTERACTIVE=1`).

Speech stays local: nothing here calls cloud STT/TTS. Model menus list
suggested local files (STT ggml + rewrite GGUF). Select downloads the
file into the models dir and wires settings. No cloud / user-hosted
endpoints.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from digivoice.catalog import (
    REWRITE_CATALOG,
    STT_CATALOG,
    CatalogModel,
    install_catalog_model,
    rewrite_catalog,
    stt_catalog,
)
from digivoice.menu_tree import browse_settings
from digivoice.models import VoicePaths
from digivoice.rewrite import LOCAL_REWRITE_MODEL_FILE
from digivoice.settings import (
    HOTKEYS_DOCS,
    PRESET_LABELS,
    BannerDensity,
    BannerPosition,
    RewritePreset,
    RewriteRunnerKind,
    VoiceSettings,
    cycle_rewrite_timeout,
    format_rewrite_timeout,
    format_settings_text,
    load_settings,
    save_settings,
    settings_path,
    settings_public_dict,
)
from digivoice.tui import (
    TUI_FOOTER_HINT,
    _is_tty,
    _pause,
    _write_info_frame,
    choose,
    choose_many,
    fullscreen_enter,
    fullscreen_leave,
    pixel_wordmark,
    tui_header_lines,
)

SETUP_MENU = (
    "Models (STT / TTS)",
    "Post-process (rewrite + auto-route)",
    "Features (paste, banner, detection)",
    "Hotkeys (docs)",
    "Review & save",
    "Doctor (run health checks)",
    "Quit",
)

HARDWARE_EPIC_POINTER = "See epic #4939 / CHR-853 — full hardware-aware catalog not rebuilt here."

_BANNER_POSITIONS: tuple[str, ...] = (
    "top-center",
    "top-left",
    "top-right",
    "bottom-center",
    "bottom-left",
    "bottom-right",
    "center",
)
_REWRITE_PRESETS: tuple[str, ...] = ("email", "sms", "professional", "coding", "blog", "none")
_REWRITE_RUNNERS: tuple[str, ...] = ("auto", "ollama", "llama.cpp")

MODEL_FIELDS = (
    "stt_model",
    "tts_voice",
)
POSTPROCESS_FIELDS = (
    "rewrite_enabled",
    "rewrite_preset",
    "rewrite_model",
    "rewrite_runner",
    "rewrite_auto_route",
    "rewrite_app_routes",
    "rewrite_timeout_seconds",
)
# Legacy full Models list (STT/TTS + rewrite) for JSON-dump compatibility.
LEGACY_MODEL_FIELDS = MODEL_FIELDS + POSTPROCESS_FIELDS
FEATURE_FIELDS = (
    "paste_on_stop",
    "word_detection",
    "spelling_detection",
    "live_banner",
    "banner_position",
    "banner_animations",
)


def recommend_models(chip: str | None = None, ram_gb: float | None = None) -> dict[str, Any]:
    """Suggested local STT + rewrite catalog. Static data (no weight downloads)."""
    _ = (chip, ram_gb)
    return {
        "tiers": [
            {
                "tier": item.id,
                "model": item.id,
                "note": item.title,
                "best_for": item.best_for,
                "languages": item.languages,
                "size_hint": item.size_hint,
            }
            for item in STT_CATALOG
        ],
        "rewrite": [item.as_dict() for item in REWRITE_CATALOG],
        "pointer": HARDWARE_EPIC_POINTER,
    }


def setup_menu_tree() -> list[str]:
    return list(SETUP_MENU)


def render_setup_overview(settings: VoiceSettings, paths: VoicePaths) -> str:
    """Current settings + wizard menu tree. No prompts; used by --print."""
    lines = [
        "┌─ digivoice setup ──────────────────────────────────────┐",
        "│  digivoice · local speech config                       │",
        f"│  settings: {settings_path(paths)}".ljust(56) + "│",
        "│  ↑↓ move · Enter select · Esc back · q quit            │",
        "└────────────────────────────────────────────────────────┘",
        "",
    ]
    for index, item in enumerate(SETUP_MENU):
        marker = "▶" if index == 0 else " "
        lines.append(f"  {marker} {item}")
    lines += [
        "",
        "— Models —",
        f"  stt_model ............... {settings.stt_model}",
        f"  tts_voice ............... {settings.tts_voice or '(auto / DIGIVOICE_PIPER_VOICE)'}",
        "",
        "— Post-process —",
        "  Clean up after dictation rewrites the words when on; off pastes them as spoken.",
        "  Select a suggested local model to download and wire it. Never a cloud URL.",
        f"  rewrite_enabled ......... {str(settings.rewrite_enabled).lower()}",
        f"  rewrite_preset .......... {settings.rewrite_preset}",
        f"  rewrite_model ........... {settings.rewrite_model or LOCAL_REWRITE_MODEL_FILE}",
        f"  rewrite_runner .......... {settings.rewrite_runner}",
        f"  rewrite_auto_route ...... {str(settings.rewrite_auto_route).lower()}",
        f"  rewrite_timeout_seconds . {format_rewrite_timeout(settings.rewrite_timeout_seconds)}",
        f"  rewrite_app_routes ...... {len(settings.rewrite_app_routes)} fragment→preset entries",
        "",
        "— Features —",
        f"  paste_on_stop ...... {str(settings.paste_on_stop).lower()}",
        f"  word_detection ..... {str(settings.word_detection).lower()}",
        f"  spelling_detection . {str(settings.spelling_detection).lower()}",
        f"  live_banner ........ {str(settings.live_banner).lower()}",
        f"  banner_position .... {settings.banner_position}",
        f"  banner_animations .. {str(settings.banner_animations).lower()}",
        "",
        "— Hotkeys (locked sample) —",
    ]
    for name, doc in HOTKEYS_DOCS.items():
        lines.append(f"  {name}: {doc}")
    lines += [
        "",
        "— Models (suggested local list) —",
        f"  {HARDWARE_EPIC_POINTER}",
        "  STT:",
    ]
    for tier in recommend_models()["tiers"]:
        lines.append(
            f"  {tier['model']} — best for: {tier.get('best_for', tier['note'])} "
            f"({tier.get('languages', '')}, {tier.get('size_hint', '')})"
        )
    lines.append("  Post-process rewrite:")
    for item in recommend_models()["rewrite"]:
        lines.append(
            f"  {item['filename']} — best for: {item['best_for']} "
            f"({item['languages']}, {item['size_hint']})"
        )
    lines += [
        "",
        "Drive without a TTY: `digivoice setup --print` (or "
        "DIGIVOICE_SETUP_NONINTERACTIVE=1), `digivoice setup --json`, "
        "or `digivoice settings set <key> <value>`.",
        "",
    ]
    return "\n".join(lines)


def setup_public_dict(settings: VoiceSettings, paths: VoicePaths) -> dict[str, Any]:
    """Machine-readable dump: settings + menu tree + hardware stub."""
    data = settings_public_dict(settings, paths)
    data["setup_menu"] = setup_menu_tree()
    data["model_fields"] = list(MODEL_FIELDS)
    data["postprocess_fields"] = list(POSTPROCESS_FIELDS)
    data["legacy_model_fields"] = list(LEGACY_MODEL_FIELDS)
    data["feature_fields"] = list(FEATURE_FIELDS)
    data["hardware_recommendations"] = recommend_models()
    return data


# TUI primitives live in digivoice.tui (shared with the home shell); the
# setup-only names below stay here. Re-exports keep old import paths working.
__all__ = [
    "FEATURE_FIELDS",
    "HARDWARE_EPIC_POINTER",
    "LEGACY_MODEL_FIELDS",
    "MODEL_FIELDS",
    "POSTPROCESS_FIELDS",
    "SETUP_MENU",
    "TUI_FOOTER_HINT",
    "choose",
    "choose_many",
    "pixel_wordmark",
    "postprocess_menu_options",
    "recommend_models",
    "render_setup_overview",
    "run_interactive_setup",
    "setup_menu_tree",
    "setup_public_dict",
    "tui_header_lines",
]


def _prompt_text(
    label: str,
    current: str | None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> str | None:
    stdout = stdout or sys.stdout
    hint = current if current is not None else "(unset)"
    stdout.write(f"  {label} [{hint}] (blank keeps current; 'none' clears)\n")
    stdout.flush()
    stdin = stdin or sys.stdin
    try:
        raw = stdin.readline()
    except (OSError, ValueError):
        return None
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None  # keep current
    if text.lower() in {"none", "null", "-"}:
        return ""
    return text


def _prompt_bool(
    label: str,
    current: bool,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> bool | None:
    picked = choose(f"{label} (now {str(current).lower()})", ["true", "false"], stdin, stdout)
    if picked is None:
        return None
    return picked == 0


def _prompt_literal(
    label: str,
    current: str,
    choices: tuple[str, ...],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> str | None:
    picked = choose(f"{label} (now {current})", list(choices), stdin, stdout)
    if picked is None:
        return None
    return choices[picked]


def _catalog_labels(entries: tuple[CatalogModel, ...], paths: VoicePaths | None) -> list[str]:
    labels: list[str] = []
    root = Path(paths.models_dir) if paths is not None else None
    for item in entries:
        present = root is not None and (root / item.filename).is_file()
        mark = "installed" if present else "download + wire"
        labels.append(f"{item.id} — {item.best_for} ({item.languages}, {item.size_hint}) [{mark}]")
    return labels


def _install_with_progress(
    paths: VoicePaths,
    entry: CatalogModel,
    stdout: TextIO | None,
) -> str:
    stdout = stdout or sys.stdout

    def progress(got: int, total: int | None) -> None:
        if total:
            pct = min(100, int(got * 100 / total))
            filled = round(24 * pct / 100)
            bar = "█" * filled + "░" * (24 - filled)
            msg = f"{bar}  {pct}%"
        else:
            msg = f"{'░' * 24}  {got} bytes"
        title = f"Downloading {entry.title.replace(' (default)', '')}"
        if _is_tty(stdout):
            _write_info_frame(stdout, title, [msg, entry.filename], footer="working…", wait=False)
        else:
            stdout.write(f"  {title}  {msg}\n")
            stdout.flush()

    dest = install_catalog_model(paths, entry, progress=progress)
    if _is_tty(stdout):
        _write_info_frame(
            stdout,
            "Download",
            [f"Ready: {dest}", "Wired into settings."],
            footer="Enter to continue",
        )
    else:
        stdout.write(f"  ready {dest}\n")
        stdout.flush()
    return dest


def _edit_models(
    working: dict[str, Any],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    paths: VoicePaths | None = None,
) -> None:
    stdout = stdout or sys.stdout
    while True:
        options = [
            f"stt_model [{working['stt_model']}]",
            f"tts_voice [{working['tts_voice'] or '(auto)'}]",
            "Back",
        ]
        picked = choose(
            "— Models (STT / TTS) —",
            options,
            stdin,
            stdout,
            subtitle="Speech-to-text and Piper voice. STT picks from a suggested local list.",
        )
        if picked is None or picked == len(options) - 1:
            return
        if picked == 0:
            entries = stt_catalog()
            labels = _catalog_labels(entries, paths) + ["Other… (local filename only)"]
            sel = choose(
                "Dictation model",
                labels,
                stdin,
                stdout,
                subtitle="Suggested local whisper.cpp files. Select to download and wire.",
            )
            if sel is None:
                continue
            if sel < len(entries):
                entry = entries[sel]
                if paths is not None:
                    try:
                        _install_with_progress(paths, entry, stdout)
                    except (OSError, ValueError) as exc:
                        stdout.write(f"  could not install {entry.filename}: {exc}\n")
                        continue
                working["stt_model"] = entry.id
                continue
            value = _prompt_text("stt_model", working["stt_model"], stdin, stdout)
            if value:
                working["stt_model"] = value
        elif picked == 1:
            value = _prompt_text("tts_voice", working["tts_voice"], stdin, stdout)
            if value is not None:
                working["tts_voice"] = value or None


def postprocess_menu_options(working: dict[str, Any]) -> list[str]:
    """Literal on/off copy for the post-process pane (TTY and numbered prompts)."""
    enabled = "on" if working["rewrite_enabled"] else "off"
    timeout = format_rewrite_timeout(working.get("rewrite_timeout_seconds"))
    model = working.get("rewrite_model") or LOCAL_REWRITE_MODEL_FILE
    auto = "on" if working["rewrite_auto_route"] else "off"
    return [
        (
            f"Clean up after dictation [{enabled}] "
            "(off = paste as spoken; on = rewrite with the local model first)"
        ),
        f"Rewrite style [{working['rewrite_preset']}] (how the cleaned-up text should read)",
        (
            f"Local model [{model}] "
            "(suggested on-device list; select downloads and wires it — never a cloud URL)"
        ),
        (f"Run with [{working['rewrite_runner']}] (llama.cpp or local ollama on this machine)"),
        (
            f"Match the front app [{auto}] "
            "(on: Mail→email, Messages→SMS; off: always use Rewrite style)"
        ),
        f"Give up after [{timeout}] (off by default; when on: 15, 30, or 60 seconds only)",
        (
            f"App → style list [{len(working['rewrite_app_routes'])} apps] "
            "(which apps pick which rewrite style)"
        ),
        "Back",
    ]


def _pick_local_rewrite_model(
    working: dict[str, Any],
    paths: VoicePaths | None,
    stdin: TextIO | None,
    stdout: TextIO | None,
) -> None:
    entries = rewrite_catalog()
    labels = _catalog_labels(entries, paths)
    sel = choose(
        "Local rewrite model",
        labels,
        stdin,
        stdout,
        subtitle="Suggested on-device GGUFs. Select to download and wire. Local only.",
    )
    if sel is None:
        return
    entry = entries[sel]
    if paths is not None:
        try:
            _install_with_progress(paths, entry, stdout)
        except (OSError, ValueError) as exc:
            out = stdout or sys.stdout
            out.write(f"  could not install local model: {exc}\n")
            return
    working["rewrite_model"] = entry.filename
    working["rewrite_runner"] = "llama.cpp"


def _edit_postprocess(
    working: dict[str, Any],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    paths: VoicePaths | None = None,
) -> None:
    stdout = stdout or sys.stdout
    while True:
        options = postprocess_menu_options(working)
        picked = choose(
            "— Post-process —",
            options,
            stdin,
            stdout,
            subtitle=(
                "After dictation, optionally rewrite the words with a local model. "
                "Off pastes them as spoken."
            ),
        )
        if picked is None or picked == len(options) - 1:
            return
        if picked == 0:
            value = choose(
                "Clean up after dictation",
                [
                    "on (rewrite the words after whisper)",
                    "off (paste them as spoken)",
                ],
                stdin,
                stdout,
            )
            if value is not None:
                working["rewrite_enabled"] = value == 0
        elif picked == 1:
            value = _prompt_literal(
                "rewrite_preset",
                working["rewrite_preset"],
                _REWRITE_PRESETS,
                stdin,
                stdout,
            )
            if value is not None:
                working["rewrite_preset"] = value
        elif picked == 2:
            _pick_local_rewrite_model(working, paths, stdin, stdout)
        elif picked == 3:
            value = _prompt_literal(
                "rewrite_runner",
                working["rewrite_runner"],
                _REWRITE_RUNNERS,
                stdin,
                stdout,
            )
            if value is not None:
                working["rewrite_runner"] = value
        elif picked == 4:
            value = choose(
                "Match style to the front app",
                [
                    "on (Mail→email, Messages→SMS, Terminal→coding)",
                    "off (always use Rewrite style)",
                ],
                stdin,
                stdout,
            )
            if value is not None:
                working["rewrite_auto_route"] = value == 0
        elif picked == 5:
            working["rewrite_timeout_seconds"] = cycle_rewrite_timeout(
                working.get("rewrite_timeout_seconds")
            )
        elif picked == 6:
            stdout.write(
                "  rewrite_app_routes is a JSON object of fragment→preset "
                f"({len(working['rewrite_app_routes'])} entries). "
                "Paste a new object or blank to keep.\n"
            )
            stdout.flush()
            stdin = stdin or sys.stdin
            try:
                raw = stdin.readline()
            except (OSError, ValueError):
                continue
            if not raw:
                continue
            raw = raw.strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    stdout.write(f"  invalid JSON — kept current ({exc})\n")
                    continue
                if isinstance(parsed, dict) and all(
                    isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
                ):
                    working["rewrite_app_routes"] = parsed
                else:
                    stdout.write("  expects a JSON object of string→string — kept current\n")


def _edit_features(
    working: dict[str, Any],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    while True:
        options = [
            f"paste_on_stop [{str(working['paste_on_stop']).lower()}]",
            f"word_detection [{str(working['word_detection']).lower()}]",
            f"spelling_detection [{str(working['spelling_detection']).lower()}]",
            f"live_banner [{str(working['live_banner']).lower()}]",
            f"banner_position [{working['banner_position']}]",
            f"banner_animations [{str(working['banner_animations']).lower()}]",
            "Back",
        ]
        picked = choose(
            "— Features —",
            options,
            stdin,
            stdout,
            subtitle="Paste, live banner, and dictation helpers. The banner is the status icon.",
        )
        if picked is None or picked == len(options) - 1:
            return
        if picked == 0:
            value = _prompt_bool("paste_on_stop", working["paste_on_stop"], stdin, stdout)
            if value is not None:
                working["paste_on_stop"] = value
        elif picked == 1:
            value = _prompt_bool("word_detection", working["word_detection"], stdin, stdout)
            if value is not None:
                working["word_detection"] = value
        elif picked == 2:
            value = _prompt_bool("spelling_detection", working["spelling_detection"], stdin, stdout)
            if value is not None:
                working["spelling_detection"] = value
        elif picked == 3:
            value = _prompt_bool("live_banner", working["live_banner"], stdin, stdout)
            if value is not None:
                working["live_banner"] = value
        elif picked == 4:
            value = _prompt_literal(
                "banner_position",
                working["banner_position"],
                _BANNER_POSITIONS,
                stdin,
                stdout,
            )
            if value is not None:
                working["banner_position"] = value
        elif picked == 5:
            value = _prompt_bool("banner_animations", working["banner_animations"], stdin, stdout)
            if value is not None:
                working["banner_animations"] = value


def _show_hotkeys(stdout: TextIO | None = None, stdin: TextIO | None = None) -> None:
    stdout = stdout or sys.stdout
    stdin = stdin or sys.stdin
    body = [
        "  dict_toggle ...... Right Option — dict --toggle",
        "  speak_selection .. Double-tap Left Option — speak --selection",
        "  cancel ........... Esc — discard take",
        "",
    ]
    for name, doc in HOTKEYS_DOCS.items():
        body.append(f"  {name}: {doc}")
    body += ["", "  See digivoice/hammerspoon/README.md for Mic + Accessibility TCC."]
    if _is_tty(stdin):
        _write_info_frame(stdout, "— Hotkeys (read-only docs) —", body)
        return
    stdout.write("\n— Hotkeys (read-only docs) —\n")
    for line in body:
        stdout.write(line + "\n")
    stdout.flush()
    _pause(stdin, stdout)


def run_interactive_setup(
    paths: VoicePaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    run_doctor=None,
) -> int:
    """TTY walks /settings. Pipes keep the numbered wizard. Returns an exit code."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if _is_tty(stdin):
        fullscreen_enter(stdout)
        try:
            browse_settings(paths, stdin, stdout, install=_install_with_progress)
        finally:
            fullscreen_leave(stdout)
        return 0
    current = load_settings(paths)
    working: dict[str, Any] = current.model_dump(mode="json")
    dirty = False
    tty = _is_tty(stdin)
    note = ""
    if tty:
        fullscreen_enter(stdout)
    try:
        if not tty:
            # Byte-stable banner for agents/pipes/tests. TTY frames redraw in place.
            stdout.write("┌─ digivoice setup ──────────────────────────────────────┐\n")
            stdout.write("│  digivoice · local speech config                       │\n")
            stdout.write("│  ↑↓ move · Enter select · Esc back · q quit            │\n")
            stdout.write("└────────────────────────────────────────────────────────┘\n")
            stdout.flush()
        while True:
            picked = choose(
                "digivoice setup",
                list(SETUP_MENU),
                stdin,
                stdout,
                subtitle="local speech config",
            )
            if picked is None or SETUP_MENU[picked] == "Quit":
                if dirty:
                    stdout.write("  Unsaved changes.\n")
                    save = choose("Save before quitting?", ["Save", "Discard"], stdin, stdout)
                    if save == 0:
                        try:
                            settings = VoiceSettings.model_validate(working)
                        except Exception as exc:
                            msg = f"  invalid settings — not saved: {exc}\n"
                            if tty:
                                note = msg
                            else:
                                stdout.write(msg)
                            return 1
                        save_settings(paths, settings)
                        msg = f"  saved {settings_path(paths)}\n"
                        if tty:
                            note = msg
                        else:
                            stdout.write(msg)
                        return 0
                    return 0
                return 0
            section = SETUP_MENU[picked]
            if section.startswith("Models"):
                before = json.dumps(working, sort_keys=True)
                _edit_models(working, stdin, stdout, paths)
                dirty = dirty or json.dumps(working, sort_keys=True) != before
            elif section.startswith("Post-process"):
                before = json.dumps(working, sort_keys=True)
                _edit_postprocess(working, stdin, stdout, paths)
                dirty = dirty or json.dumps(working, sort_keys=True) != before
            elif section.startswith("Features"):
                before = json.dumps(working, sort_keys=True)
                _edit_features(working, stdin, stdout)
                dirty = dirty or json.dumps(working, sort_keys=True) != before
            elif section.startswith("Hotkeys"):
                _show_hotkeys(stdout, stdin)
            elif section.startswith("Review"):
                try:
                    preview = VoiceSettings.model_validate(working)
                except Exception as exc:
                    stdout.write(f"  invalid settings — fix before saving: {exc}\n")
                    continue
                if tty:
                    _write_info_frame(
                        stdout,
                        "Review & save",
                        format_settings_text(preview, paths).splitlines(),
                        footer="Enter to choose",
                        wait=False,
                    )
                else:
                    stdout.write("\n" + format_settings_text(preview, paths) + "\n")
                    stdout.flush()
                save = choose("Save these settings?", ["Save", "Keep editing"], stdin, stdout)
                if save == 0:
                    save_settings(paths, preview)
                    stdout.write(f"  saved {settings_path(paths)}\n")
                    dirty = False
            elif section.startswith("Doctor"):
                if run_doctor is not None:
                    if tty:
                        _write_info_frame(
                            stdout, "Doctor", run_doctor().splitlines(), footer="Enter to go back"
                        )
                    else:
                        stdout.write("\n" + run_doctor() + "\n")
                        stdout.flush()
                else:
                    if tty:
                        _write_info_frame(
                            stdout,
                            "Doctor",
                            ["  Run `digivoice doctor` to see health checks."],
                        )
                    else:
                        stdout.write("\n  Run `digivoice doctor` to see health checks.\n")
                        stdout.flush()
    finally:
        if tty:
            fullscreen_leave(stdout)
        if note:
            stdout.write(note)
            stdout.flush()


def _silence_unused() -> None:
    # Keep literal-type imports referenced for type checkers after refactors.
    _ = (RewritePreset, RewriteRunnerKind, BannerDensity, BannerPosition)
    _ = PRESET_LABELS
