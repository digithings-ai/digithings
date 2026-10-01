"""Bare-`digivoice` home shell: the full terminal UI over the existing commands.

A TTY gets the in-place TUI (pixel DIGIVOICE header, one-frame redraw per key,
same nav as setup). Pipes, CI, and agents get a printed overview and exit 0 —
never a hang. Every entry routes to the same handlers the subcommands use.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from digivoice.paths import resolve_paths
from digivoice.tui import (
    _is_tty,
    _pause,
    _write_info_frame,
    choose,
    play_intro,
)

HOME_SUBTITLE = "digivoice home · local speech control"

HOME_MENU = (
    "Doctor (health checks)",
    "Setup wizard (models, features, hotkeys)",
    "Settings (show)",
    "History (recent)",
    "Status (banner feed)",
    "Reload (local control)",
    "Update",
    "Uninstall",
    "Quit",
)

MIC_HINT = (
    "mic commands run in a terminal: `digivoice dict --toggle` · `digivoice speak --selection`"
)


def home_menu_tree() -> list[str]:
    return list(HOME_MENU)


def render_home_overview(
    settings_text: str,
    history_hint: str = "no recent entries shown here; see `digivoice history --last 5`",
) -> str:
    """Non-interactive home: menu tree plus pointers. No prompts, exit 0."""
    lines = [
        "┌─ digivoice ────────────────────────────────────────────┐",
        "│  digivoice home · local speech control                 │",
        "│  ↑↓ move · Enter select · Space select · Esc/q quit   │",
        "└────────────────────────────────────────────────────────┘",
        "",
    ]
    for index, item in enumerate(HOME_MENU):
        marker = "▶" if index == 0 else " "
        lines.append(f"  {marker} {item}")
    lines += [
        "",
        "— Settings (current) —",
        settings_text.rstrip(),
        "",
        "— History —",
        f"  {history_hint}",
        "",
        f"— Mic —\n  {MIC_HINT}",
        "",
        "Subcommands stay scriptable: doctor, setup [--print|--json], settings,",
        "history, status, reload, cancel, dict, speak. Agents: `digivoice` with",
        "no TTY prints this overview; `digivoice --help` shows argparse help.",
        "",
    ]
    return "\n".join(lines)


def run_home(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run the home shell. Returns a process exit code; never hangs a pipe."""
    from digivoice import cli as _cli
    from digivoice.settings import format_settings_text, load_settings

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    paths = resolve_paths(platform, home, env)

    if not _is_tty(stdin):
        settings_text = format_settings_text(load_settings(paths), paths)
        stdout.write(render_home_overview(settings_text) + "\n")
        stdout.flush()
        return 0

    runtime = _cli.Runtime(
        platform=platform, home=home, env=env, probe=_cli.real_probe(env.get("PATH"))
    )
    play_intro(stdout, HOME_SUBTITLE)
    while True:
        picked = choose("digivoice home", list(HOME_MENU), stdin, stdout, subtitle=HOME_SUBTITLE)
        if picked is None or HOME_MENU[picked] == "Quit":
            return 0
        entry = HOME_MENU[picked]
        if entry.startswith("Doctor"):
            result = _cli._doctor(runtime)
            _write_info_frame(
                stdout,
                "— Doctor —",
                result.stdout.splitlines() or [result.stderr],
                subtitle=HOME_SUBTITLE,
            )
            _pause(stdin, stdout)
        elif entry.startswith("Setup"):
            _cli._setup(argparse.Namespace(print_only=False, as_json=False), runtime)
        elif entry.startswith("Settings"):
            text = format_settings_text(load_settings(paths), paths)
            _write_info_frame(stdout, "— Settings —", text.splitlines(), subtitle=HOME_SUBTITLE)
            _pause(stdin, stdout)
        elif entry.startswith("History"):
            args = argparse.Namespace(last=5, grep=None, copy_last=False, as_json=False)
            result = _cli._history(args, runtime)
            _write_info_frame(
                stdout,
                "— History (last 5) —",
                result.stdout.splitlines(),
                subtitle=HOME_SUBTITLE,
            )
            _pause(stdin, stdout)
        elif entry.startswith("Status"):
            result = _cli._status(runtime)
            body = result.stdout.splitlines() or [result.stderr.strip()]
            _write_info_frame(stdout, "— Status —", body, subtitle=HOME_SUBTITLE)
            _pause(stdin, stdout)
        elif entry.startswith("Reload"):
            args = argparse.Namespace(as_json=False)
            result = _cli._reload(args, runtime)
            body = result.stdout.splitlines() or [result.stderr.strip()]
            _write_info_frame(stdout, "— Reload —", body, subtitle=HOME_SUBTITLE)
            _pause(stdin, stdout)
        elif entry.startswith("Update"):
            result = _cli._update()
            _write_info_frame(
                stdout, "— Update —", result.stdout.splitlines(), subtitle=HOME_SUBTITLE
            )
            _pause(stdin, stdout)
        elif entry.startswith("Uninstall"):
            result = _cli._uninstall()
            _write_info_frame(
                stdout, "— Uninstall —", result.stdout.splitlines(), subtitle=HOME_SUBTITLE
            )
            _pause(stdin, stdout)
