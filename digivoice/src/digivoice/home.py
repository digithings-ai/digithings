"""Bare-`digivoice` app home: status strip plus actions over the commands.

A TTY takes the whole viewport: alternate screen, content centered, DIGIVOICE
half-block wordmark (build-in, then a quiet glint), status strip, and a
step-rail menu. Pipes, CI, and agents get a printed overview and exit 0 —
never a hang. Setup is a submenu entry that returns to home; it is not the
home screen. Every entry routes to the handlers the subcommands use.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from digivoice.paths import resolve_paths
from digivoice.reload import LaunchReport, ensure_home_control, stop_home_control
from digivoice.runner import CommandRunner
from digivoice.tui import (
    _is_tty,
    _pause,
    _write_info_frame,
    choose,
    fullscreen_enter,
    fullscreen_leave,
    play_intro,
)

HOME_TITLE = "DIGIVOICE"
HOME_SUBTITLE = "DIGIVOICE · app home — local speech control"

# App-home actions. Setup sits second-last as a "wizard…" submenu — it opens
# the setup wizard and returns to home, it is never the home screen itself.
# Status is not an action: the live status.json feed surfaces in the context
# strip and via `digivoice status`. Update/Uninstall stay CLI-only
# (`digivoice install` / `update` / `uninstall`).
HOME_MENU = (
    "Doctor (health checks)",
    "Settings (show)",
    "History (recent)",
    "Reload (local control)",
    "Setup (wizard…)",
    "Quit",
)

# Contiguous slices of HOME_MENU. Status is the context strip, not a row.
HOME_GROUPS: tuple[tuple[str, int, int], ...] = (
    ("Operate", 0, 3),
    ("Maintain", 3, 4),
    ("Configure", 4, 5),
    ("Leave", 5, 6),
)

MIC_HINT = (
    "mic commands run in a terminal: `digivoice dict --toggle` · `digivoice speak --selection`"
)


def home_menu_tree() -> list[str]:
    return list(HOME_MENU)


def home_context_lines(
    settings_text_model: str,
    tts_label: str,
    banner_density: str,
    banner_position: str,
    health: str,
) -> list[str]:
    """Symbol-led status strip for the home frame (no `models:`/`health:` labels)."""
    healthy = health.strip().lower().startswith("ok")
    health_symbol = "■" if healthy else "□"
    return [
        f"▦ stt {settings_text_model} · tts {tts_label}",
        f"▥ {banner_density} ({banner_position})",
        f"{health_symbol} {health}",
    ]


def build_context_lines(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    probe: object | None = None,
) -> list[str]:
    """Status strip: models, banner density, doctor health. Never raises."""
    from digivoice.settings import load_settings

    try:
        paths = resolve_paths(platform, home, env)
        settings = load_settings(paths)
        tts_label = settings.tts_voice or "(auto)"
        if probe is None:
            from digivoice.probe import real_probe

            probe = real_probe(env.get("PATH", ""))
        ok, summary = summarize_health(platform, home, dict(env), probe)
        _ = ok
        return home_context_lines(
            settings.stt_model,
            tts_label,
            settings.banner_density,
            settings.banner_position,
            summary,
        )
    except Exception:
        return ["▦ (unavailable)", "▥ (unavailable)", "□ unknown"]


def summarize_health(
    platform: str,
    home: Path,
    env: dict[str, str],
    probe: object,
) -> tuple[bool, str]:
    """One-line doctor summary for the strip. Never raises."""
    try:
        from digivoice.doctor import doctor_checks, render_doctor

        checks = doctor_checks(platform, home, env, probe)  # type: ignore[arg-type]
        report = render_doctor(checks)
        required = [c for c in checks if c.id in {"whisper-cli", "piper", "capture", "models"}]
        missing = [c.id for c in required if c.status != "ok"]
        if report.ok:
            return True, f"ok ({len(required)}/{len(required)} ready)"
        if missing:
            return False, f"not ready — missing: {', '.join(missing)}"
        return False, "not ready — see Doctor"
    except Exception:
        return False, "unknown"


def render_home_overview(
    settings_text: str,
    history_hint: str = "no recent entries shown here; see `digivoice history --last 5`",
    context_lines: list[str] | None = None,
) -> str:
    """Non-interactive home: context strip plus menu tree. No prompts, exit 0."""
    lines = [
        "┌─ DIGIVOICE ────────────────────────────────────────────┐",
        "│  DIGIVOICE · app home — local speech control           │",
        "│  ↑↓ move · Enter select · Esc/q quit                   │",
        "└────────────────────────────────────────────────────────┘",
        "",
    ]
    if context_lines:
        lines.append("— Context —")
        for entry in context_lines:
            lines.append(f"  {entry}")
        lines.append("")
    lines.append("— Actions —")
    for index, item in enumerate(HOME_MENU):
        marker = "▶" if index == 0 else " "
        lines.append(f"  {marker} {item}")
    lines += [
        "",
        "Setup lives under “Setup (wizard…)” and returns here; it is not the home screen.",
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


def _context_with_control(context: list[str], summary: str) -> list[str]:
    return [*context, f"▤ {summary}"]


def run_home(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    runner: CommandRunner | None = None,
    launch: LaunchReport | None = None,
) -> int:
    """Run the home shell. Returns a process exit code; never hangs a pipe."""
    from digivoice import cli as _cli
    from digivoice.settings import (
        format_settings_compact,
        format_settings_text,
        load_settings,
    )

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    paths = resolve_paths(platform, home, env)
    report = (
        launch if launch is not None else ensure_home_control(platform, home, env, runner=runner)
    )

    if not _is_tty(stdin):
        settings_text = format_settings_text(load_settings(paths), paths)
        context = _context_with_control(
            build_context_lines(platform, home, env, probe=_cli.real_probe(env.get("PATH"))),
            report.summary,
        )
        stdout.write(render_home_overview(settings_text, context_lines=context) + "\n")
        stdout.flush()
        return 0

    runtime = _cli.Runtime(
        platform=platform, home=home, env=env, probe=_cli.real_probe(env.get("PATH"))
    )
    fullscreen_enter(stdout)
    try:
        play_intro(stdout, "local speech control")
        while True:
            context = _context_with_control(
                build_context_lines(platform, home, env, probe=runtime.probe),
                report.summary,
            )
            picked = choose(
                "Actions",
                list(HOME_MENU),
                stdin,
                stdout,
                subtitle="local speech control",
                context=context,
                hero=True,
                pulse=True,
                groups=HOME_GROUPS,
            )
            if picked is None or HOME_MENU[picked] == "Quit":
                # Explicit TUI exit tears Hammerspoon down. Closing the Terminal
                # alone (SIGHUP/SIGTERM) never reaches here — HS stays running.
                stop_home_control(platform, home, env, runner=runner)
                return 0
            entry = HOME_MENU[picked]
            if entry.startswith("Doctor"):
                result = _cli._doctor(runtime)
                _write_info_frame(
                    stdout,
                    "Doctor",
                    result.stdout.splitlines() or [result.stderr],
                    subtitle=HOME_SUBTITLE,
                )
                _pause(stdin, stdout)
            elif entry.startswith("Settings"):
                text = format_settings_compact(load_settings(paths), paths)
                _write_info_frame(stdout, "Settings", text.splitlines(), subtitle=HOME_SUBTITLE)
                _pause(stdin, stdout)
            elif entry.startswith("History"):
                args = argparse.Namespace(last=5, grep=None, copy_last=False, as_json=False)
                result = _cli._history(args, runtime)
                _write_info_frame(
                    stdout,
                    "History",
                    result.stdout.splitlines(),
                    subtitle=HOME_SUBTITLE,
                )
                _pause(stdin, stdout)
            elif entry.startswith("Reload"):
                args = argparse.Namespace(as_json=False)
                result = _cli._reload(args, runtime)
                body = result.stdout.splitlines() or [result.stderr.strip()]
                _write_info_frame(stdout, "Reload", body, subtitle=HOME_SUBTITLE)
                _pause(stdin, stdout)
            elif entry.startswith("Setup"):
                # Submenu: run the wizard, then return to home (never exit).
                _cli._setup(argparse.Namespace(print_only=False, as_json=False), runtime)
    finally:
        fullscreen_leave(stdout)
