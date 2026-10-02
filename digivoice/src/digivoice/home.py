"""Bare-`digivoice` app home: status strip plus actions over the commands.

A TTY takes the whole viewport: alternate screen, a centered five-row
DIGIVOICE half-block wordmark in color-cube grays, status strip, and a
step-rail menu. Pipes, CI, and agents
get a printed overview and exit 0 — never a hang. Settings opens the
/settings path and returns to home. Every entry routes to the handlers
the subcommands use.
"""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from digivoice.doctor import doctor_checks
from digivoice.history import read_history
from digivoice.menu_tree import browse_settings
from digivoice.nav import QuitRequested, norm_path, section_of
from digivoice.panels import _UPDATE, browse_history, browse_system, present_doctor
from digivoice.paste import copy_to_clipboard
from digivoice.paths import resolve_paths
from digivoice.reload import LaunchReport, ensure_home_control, run_reload, stop_home_control
from digivoice.runner import CommandRunner, run_command
from digivoice.settings import default_settings, save_settings
from digivoice.setup import _install_with_progress
from digivoice.tui import (
    MenuBlock,
    _is_tty,
    choose,
    fullscreen_enter,
    fullscreen_leave,
    play_intro,
)

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
        "System is /doctor, /reload, /reset, /restart, /update.",
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


def _on_terminal_close(_signum: int, _frame: object) -> None:
    """The terminal went away. Leave Hammerspoon running."""
    raise SystemExit(0)


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

    runtime = _cli.Runtime(
        platform=platform, home=home, env=env, probe=_cli.real_probe(env.get("PATH"))
    )

    def _restart() -> None:
        stop_home_control(platform, home, env, runner=runner)
        fullscreen_leave(stdout)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def _doctor() -> None:
        present_doctor(
            doctor_checks(platform, home, dict(env), runtime.probe),
            stdout,
            stdin,
        )

    def _follow(raw: str) -> None:
        path = norm_path(raw)
        kind = section_of(path)
        if kind == "quit":
            raise QuitRequested()
        if kind == "settings":
            browse_settings(
                paths,
                stdin,
                stdout,
                install=_install_with_progress,
                start=path,
                on_path=_follow,
            )
            return
        if kind == "history":
            browse_history(
                paths,
                platform,
                runtime.probe,
                runner,
                stdin,
                stdout,
                on_path=_follow,
            )
            return
        if kind == "system":
            browse_system(
                paths,
                platform,
                home,
                env,
                stdin,
                stdout,
                runner=runner,
                restart=_restart,
                doctor=_doctor,
                on_path=_follow,
            )
            return
        if kind == "doctor":
            _doctor()
            return
        if kind == "reload":
            result = run_reload(platform, home, dict(env), runner=runner)
            text = result.stdout.strip() or result.stderr.strip() or "reload finished"
            stdout.write(text + "\n")
            stdout.flush()
            return
        if kind == "reset":
            save_settings(paths, default_settings())
            stdout.write("  settings reset\n")
            stdout.flush()
            return
        if kind == "restart":
            _restart()
            return
        if kind == "update":
            stdout.write(_UPDATE + "\n")
            stdout.flush()
            return
        if kind == "history-copy":
            reading = read_history(paths.history_file)
            if not reading.entries:
                stdout.write("  no takes yet\n")
                stdout.flush()
                return
            text = reading.entries[-1].text
            copied = copy_to_clipboard(platform, runtime.probe, runner or run_command, text)
            stdout.write(f"  {copied.detail}\n")
            stdout.flush()

    fullscreen_enter(stdout)
    previous_hup = signal.getsignal(signal.SIGHUP)
    signal.signal(signal.SIGHUP, _on_terminal_close)
    try:
        play_intro(stdout, "local speech control")
        while True:
            context = _context_with_control(
                build_context_lines(platform, home, env, probe=runtime.probe),
                report.summary,
            )
            picked = choose(
                "Actions",
                stdin=stdin,
                stdout=stdout,
                subtitle="local speech control",
                context=context,
                hero=True,
                pulse=True,
                groups=HOME_GROUPS,
                blocks=HOME_BLOCKS,
            )
            if isinstance(picked, str) and picked.startswith("/"):
                try:
                    _follow(picked)
                except QuitRequested:
                    stop_home_control(platform, home, env, runner=runner)
                    return 0
                continue
            if picked is None:
                # Esc leaves the screen. Hammerspoon keeps running.
                return 0
            if HOME_MENU[picked] == "Quit":
                stop_home_control(platform, home, env, runner=runner)
                return 0
            try:
                _follow(HOME_BLOCKS[picked].path)
            except QuitRequested:
                stop_home_control(platform, home, env, runner=runner)
                return 0
    finally:
        signal.signal(signal.SIGHUP, previous_hup)
        fullscreen_leave(stdout)
