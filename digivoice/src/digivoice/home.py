"""Bare-`digivoice` app home: status strip plus actions over the commands.

A TTY replaces this process with the OpenTUI app (five-row DIGIVOICE
wordmark, status strip, step-rail menu). Pipes, CI, and agents get a
printed overview and exit 0 — never a hang.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from digivoice.opentui import launch_opentui
from digivoice.paths import resolve_paths
from digivoice.probe import real_probe
from digivoice.reload import LaunchReport, ensure_home_control
from digivoice.runner import CommandRunner
from digivoice.settings import load_settings
from digivoice.tui import MenuBlock, _is_tty

HOME_TITLE = "DIGIVOICE"
HOME_SUBTITLE = "DIGIVOICE · app home — local speech control"

# Four home actions. Each path is a command: `digivoice /history`, `digivoice quit`.
HOME_BLOCKS: tuple[MenuBlock, ...] = (
    MenuBlock(action="History", path="/history"),
    MenuBlock(action="Settings", path="/settings"),
    MenuBlock(action="System", path="/system"),
    MenuBlock(action="Quit", path="/quit"),
)
HOME_MENU = tuple(block.action for block in HOME_BLOCKS)

# Contiguous slices of HOME_MENU. Settings sits above System.
HOME_GROUPS: tuple[tuple[str, int, int], ...] = (
    ("Operate", 0, 1),
    ("Configure", 1, 2),
    ("Maintain", 2, 3),
    ("Leave", 3, 4),
)

MIC_HINT = (
    "mic commands run in a terminal: `digivoice dict --toggle` · `digivoice speak --selection`"
)


def home_menu_tree() -> list[str]:
    return list(HOME_MENU)


def home_context_lines(
    settings_text_model: str,
    tts_label: str,
    banner_pin: str,
    banner_position: str,
    health: str,
) -> list[str]:
    """Symbol-led status strip for the home frame (no `models:`/`health:` labels)."""
    healthy = health.strip().lower().startswith("ok")
    health_symbol = "■" if healthy else "□"
    return [
        f"▦ stt {settings_text_model} · tts {tts_label}",
        f"▥ {banner_pin} ({banner_position})",
        f"{health_symbol} {health}",
    ]


def build_context_lines(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    probe: object | None = None,
) -> list[str]:
    """Status strip: models, banner pin, doctor health. Never raises."""
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
            "pin on" if settings.banner_pinned else "pin off",
            settings.banner_position,
            summary,
        )
    except Exception:
        return ["▦ (unavailable)", "▥ (unavailable)", "□ unknown"]


def format_status_line(
    model: str,
    *,
    paste: bool,
    rewrite: bool,
    banner: bool,
    pin: bool,
    summary: str,
) -> str:
    """One line: selected model, settings that are on, doctor summary."""
    flags = [
        name
        for name, enabled in (
            ("paste", paste),
            ("rewrite", rewrite),
            ("banner", banner),
            ("pin", pin),
        )
        if enabled
    ]
    parts = [model.strip() or "model", *flags, summary.strip()]
    return " · ".join(part for part in parts if part)


def build_status_line(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    probe: object | None = None,
) -> str:
    """Status line for the pinned frame. Never raises."""
    try:
        paths = resolve_paths(platform, home, env)
        settings = load_settings(paths)
        if probe is None:
            probe = real_probe(env.get("PATH", ""))
        _ok, summary = summarize_health(platform, home, dict(env), probe)
        return format_status_line(
            settings.stt_model,
            paste=settings.paste_on_stop,
            rewrite=settings.rewrite_enabled,
            banner=settings.live_banner,
            pin=settings.banner_pinned,
            summary=summary,
        )
    except Exception:
        return "unavailable"


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
        "│  ↑↓ move · Enter select · / path · Quit stops            │",
        "└────────────────────────────────────────────────────────┘",
        "",
    ]
    if context_lines:
        lines.append("— Context —")
        for entry in context_lines:
            lines.append(f"  {entry}")
        lines.append("")
    lines.append("— Actions —")
    for index, block in enumerate(HOME_BLOCKS):
        marker = "▶" if index == 0 else " "
        lines.append(f"  {marker} {block.action}")
        lines.append(f"    {block.path}")
    lines += [
        "",
        "History, Settings, System, and Quit. Doctor lives under System.",
        "Enter opens a folder or a list. Esc goes up.",
        "Each path is a command: digivoice /history, digivoice /doctor, digivoice /quit.",
        "System is /doctor, /reload, /reset, /restart, /system/update.",
        "Closing the terminal leaves digivoice running. Quit stops it.",
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
    from digivoice.settings import format_settings_text, load_settings

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

    return launch_opentui(platform, home, env, start="/")
