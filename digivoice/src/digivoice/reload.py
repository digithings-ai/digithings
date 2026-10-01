"""`digivoice reload` and the bare-`digivoice` Hammerspoon launch.

Reload refreshes local control without touching the menubar. Home launch
(`ensure_home_control`) opens Hammerspoon when it is down and asks the
adapter to show the banner. Both are bounded.

Reload re-resolves the CLI path (same lookup order the Hammerspoon adapter
uses), re-validates settings, checks the installed Lua adapter (following the
symlink into the checkout counts as picking up the installed tip), then asks a
running Hammerspoon to reload — with a hard timeout so a stuck `hs` can never
hang the CLI. When the Hammerspoon reload fails or times out, the stale
`status.json` is cleared so the banner cannot stick on old state.

Speech stays local: no cloud, no downloads, no secrets.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import BaseModel

from digivoice.models import CliResult, VoicePaths
from digivoice.paths import resolve_paths
from digivoice.runner import CommandRunner, run_command
from digivoice.settings import load_settings
from digivoice.status import TERMINAL_STATES, read_status, status_path

RELOAD_TIMEOUT_SECONDS = 8.0
# Home launch may open Hammerspoon and paint the banner, but it must return.
LAUNCH_BUDGET_SECONDS = 4.0
_PROBE_EXPR = "return 'ok'"
_BANNER_EXPR = (
    'local ok, m = pcall(require, "digivoice"); '
    'if not ok or type(m) ~= "table" or type(m.ensure_banner) ~= "function" then '
    'return "missing" end; '
    "return m.ensure_banner()"
)


def resolve_cli_path(
    env: Mapping[str, str],
    home: Path,
    package_file: str = __file__,
) -> str:
    """Mirror the adapter's lookup: env, PATH, checkout venv, ~/.local, ~/.venv."""
    override = env.get("DIGIVOICE_BIN", "")
    if override:
        return override
    found = shutil.which("digivoice", path=env.get("PATH", os.defpath))
    if found:
        return found
    candidates = [
        str(
            Path(package_file).resolve().parent.parent.parent.parent / ".venv" / "bin" / "digivoice"
        ),
        str(home / ".local" / "bin" / "digivoice"),
        str(home / ".venv" / "bin" / "digivoice"),
    ]
    for candidate in candidates:
        if os.access(candidate, os.X_OK) and Path(candidate).is_file():
            return candidate
    return "digivoice"


def adapter_locations(home: Path, paths: VoicePaths) -> tuple[str, str]:
    """Where the Lua adapter lives: user config first, data dir second."""
    return (
        str(home / ".hammerspoon" / "digivoice"),
        str(Path(paths.data_dir) / "hammerspoon"),
    )


def find_adapter(home: Path, paths: VoicePaths) -> dict[str, str | None]:
    """Locate init.lua + banner_core.lua; resolve symlinks to prove the tip is live."""
    for directory in adapter_locations(home, paths):
        init = Path(directory) / "init.lua"
        if init.is_file():
            core = Path(directory) / "banner_core.lua"
            real = os.path.realpath(directory)
            return {
                "dir": directory,
                "init": str(init),
                "banner_core": str(core) if core.is_file() else None,
                "realpath": real if real != directory else None,
            }
    return {"dir": None, "init": None, "banner_core": None, "realpath": None}


def reload_hammerspoon(
    runner: CommandRunner,
    hs_path: str | None,
    timeout: float = RELOAD_TIMEOUT_SECONDS,
) -> tuple[str, bool]:
    """Ask Hammerspoon to reload. Returns (message, ok). Never hangs."""
    if not hs_path:
        return "hammerspoon .. skipped (hs not on PATH; hotkeys need Hammerspoon running)", True
    result = runner(["hs", "-c", "hs.reload()"], timeout=timeout)
    if result.code == 0:
        return "hammerspoon .. reloaded", True
    if result.code == 124:
        return f"hammerspoon .. reload timed out after {timeout:g}s (config left running)", False
    detail = (result.stderr or result.stdout or f"exit {result.code}").strip().splitlines()
    return f"hammerspoon .. reload failed ({detail[0] if detail else 'unknown'})", False


def clear_stale_status(paths: VoicePaths) -> bool:
    """Remove status.json so the banner cannot stick. Fails soft; reports removal."""
    try:
        existed = status_path(paths).exists()
        status_path(paths).unlink(missing_ok=True)
        return existed
    except OSError:
        return False


def run_reload(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    runner: CommandRunner | None = None,
    which_hs: Callable[[], str | None] | None = None,
    timeout: float = RELOAD_TIMEOUT_SECONDS,
    as_json: bool = False,
) -> CliResult:
    """Refresh local control and report every step. Exit 1 only on real failure."""
    paths = resolve_paths(platform, home, env)
    active = runner or run_command
    lines: list[str] = []
    payload: dict[str, object] = {}

    cli = resolve_cli_path(env, home)
    lines.append(f"cli .......... {cli}")
    payload["cli"] = cli

    try:
        settings = load_settings(paths)
    except Exception as exc:
        message = f"settings ..... invalid ({exc})"
        if as_json:
            return CliResult(
                code=1,
                stdout=json.dumps({"ok": False, "error": message}, indent=2) + "\n",
                stderr="",
            )
        return CliResult(code=1, stdout=message + "\n", stderr="")
    settings_line = (
        f"settings ..... ok (banner_density={settings.banner_density}, "
        f"live_banner={str(settings.live_banner).lower()})"
    )
    lines.append(settings_line)
    payload["settings"] = "ok"

    adapter = find_adapter(home, paths)
    if adapter["init"] is not None:
        assert isinstance(adapter["dir"], str)
        adapter_line = f"adapter ...... {adapter['dir']}"
        if adapter["realpath"]:
            adapter_line += f" (live tip: {adapter['realpath']})"
        if adapter["banner_core"] is None:
            adapter_line += " [banner_core.lua missing]"
        lines.append(adapter_line)
        payload["adapter"] = adapter
    else:
        user_dir, data_dir = adapter_locations(home, paths)
        lines.append(f"adapter ...... missing (checked {user_dir} and {data_dir})")
        payload["adapter"] = adapter

    # Strictly the caller's PATH (never the process default): tests and agents
    # without a PATH must skip Hammerspoon instead of finding a stray `hs`.
    hs_path = which_hs() if which_hs is not None else shutil.which("hs", path=env.get("PATH", ""))
    message, ok = reload_hammerspoon(active, hs_path, timeout)
    lines.append(message)
    payload["hammerspoon"] = {"path": hs_path, "ok": ok, "message": message}
    if not ok:
        cleared = clear_stale_status(paths)
        status_line = (
            "status ....... cleared stale status.json"
            if cleared
            else ("status ....... no stale status.json to clear")
        )
        lines.append(status_line)
        payload["status_cleared"] = cleared
        if as_json:
            payload["ok"] = False
            return CliResult(code=1, stdout=json.dumps(payload, indent=2) + "\n", stderr="")
        return CliResult(code=1, stdout="\n".join(lines) + "\n", stderr="")

    payload["ok"] = True
    if as_json:
        return CliResult(code=0, stdout=json.dumps(payload, indent=2) + "\n", stderr="")
    return CliResult(code=0, stdout="\n".join(lines) + "\n", stderr="")


class LaunchReport(BaseModel):
    """What bare `digivoice` did to Hammerspoon and the banner. Never a failure exit."""

    summary: str
    lines: list[str]


def _hs_ok(runner: CommandRunner, expr: str, timeout: float) -> tuple[bool, str]:
    if timeout <= 0:
        return False, ""
    result = runner(["hs", "-c", expr], timeout=timeout)
    text = (result.stdout or "").strip().strip('"')
    return result.code == 0, text


def ensure_digivoice_require(home: Path, paths: VoicePaths) -> tuple[str, bool]:
    """Make sure Hammerspoon's init loads digivoice. No-op when the adapter is absent."""
    adapter = find_adapter(home, paths)
    if adapter["init"] is None:
        return "config ...... adapter missing", False
    init = home / ".hammerspoon" / "init.lua"
    needle_a = 'require("digivoice")'
    needle_b = "require('digivoice')"
    try:
        if init.is_file():
            text = init.read_text(encoding="utf-8")
            if needle_a in text or needle_b in text:
                return "config ...... digivoice already required", False
            if text and not text.endswith("\n"):
                text += "\n"
            init.write_text(text + f"\n{needle_a}\n", encoding="utf-8")
            return 'config ...... added require("digivoice")', True
        init.parent.mkdir(parents=True, exist_ok=True)
        init.write_text(f"{needle_a}\n", encoding="utf-8")
        return 'config ...... wrote init.lua require("digivoice")', True
    except OSError as exc:
        return f"config ...... not written ({exc})", False


def _take_in_progress(paths: VoicePaths) -> bool:
    snapshot = read_status(status_path(paths))
    return snapshot is not None and snapshot.state not in TERMINAL_STATES


def ensure_home_control(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    runner: CommandRunner | None = None,
    which_hs: Callable[[], str | None] | None = None,
    which_open: Callable[[], str | None] | None = None,
    budget: float = LAUNCH_BUDGET_SECONDS,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> LaunchReport:
    """Start Hammerspoon if needed and show the banner. Bounded; never raises.

    macOS only. Reuses `reload_hammerspoon` and the status file. A missing
    `hs` binary, a refused open, or a dead IPC socket is a skipped line, not
    an exception and not a hang.
    """
    try:
        return _ensure_home_control(
            platform,
            home,
            env,
            runner,
            which_hs,
            which_open,
            budget,
            monotonic,
            sleep,
        )
    except Exception as exc:
        return LaunchReport(
            summary="hammerspoon unknown · banner hidden",
            lines=[f"hammerspoon .. skipped ({exc})"],
        )


def _ensure_home_control(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    runner: CommandRunner | None,
    which_hs: Callable[[], str | None] | None,
    which_open: Callable[[], str | None] | None,
    budget: float,
    monotonic: Callable[[], float] | None,
    sleep: Callable[[float], None] | None,
) -> LaunchReport:
    if platform != "darwin":
        return LaunchReport(
            summary="hammerspoon skipped · banner skipped",
            lines=["hammerspoon .. skipped (not macOS)", "banner ....... skipped"],
        )

    now = monotonic or time.monotonic
    pause = sleep or time.sleep
    deadline = now() + max(0.0, budget)
    active = runner or run_command
    lines: list[str] = []

    def left() -> float:
        return deadline - now()

    paths = resolve_paths(platform, home, env)
    config_line, config_changed = ensure_digivoice_require(home, paths)
    lines.append(config_line)

    live_banner = True
    try:
        live_banner = load_settings(paths).live_banner
    except Exception:
        live_banner = True

    hs_path = which_hs() if which_hs is not None else shutil.which("hs", path=env.get("PATH", ""))
    running = False
    if hs_path and left() > 0:
        running, _ = _hs_ok(active, _PROBE_EXPR, min(1.0, left()))
    was_running = running

    if not running and left() > 0:
        if which_open is not None:
            open_bin = which_open()
        else:
            open_bin = shutil.which("open", path=env.get("PATH", ""))
        if not open_bin:
            lines.append("hammerspoon .. not opened (open not on PATH)")
        else:
            opened = active([open_bin, "-a", "Hammerspoon"], timeout=min(2.0, max(0.2, left())))
            if opened.code == 0:
                lines.append("hammerspoon .. opened")
            else:
                detail = (opened.stderr or opened.stdout or f"exit {opened.code}").strip()
                first = detail.splitlines()[0] if detail else "unknown"
                lines.append(f"hammerspoon .. open failed ({first})")
        while not running and hs_path and left() > 0.25:
            pause(min(0.2, max(0.0, left())))
            running, _ = _hs_ok(active, _PROBE_EXPR, min(0.8, max(0.0, left())))

    if config_changed and was_running and running and left() > 0.3:
        message, _ok = reload_hammerspoon(active, hs_path, min(1.5, left()))
        lines.append(message)
        running = False
        while not running and hs_path and left() > 0.25:
            pause(min(0.2, max(0.0, left())))
            running, _ = _hs_ok(active, _PROBE_EXPR, min(0.8, max(0.0, left())))
    elif was_running:
        lines.append("hammerspoon .. already running")
    elif running:
        lines.append("hammerspoon .. up")
    else:
        lines.append("hammerspoon .. not running")

    if not live_banner:
        lines.append("banner ....... off (live_banner false)")
        summary = "hammerspoon up · banner off" if running else "hammerspoon down · banner off"
        return LaunchReport(summary=summary, lines=lines)
    if _take_in_progress(paths):
        lines.append("banner ....... left up (take in progress)")
        summary = "hammerspoon up · banner busy" if running else "hammerspoon down · banner busy"
        return LaunchReport(summary=summary, lines=lines)
    if not running or not hs_path or left() <= 0:
        lines.append("banner ....... not shown")
        summary = "hammerspoon down · banner hidden"
        return LaunchReport(summary=summary, lines=lines)

    ok, token = _hs_ok(active, _BANNER_EXPR, min(1.5, left()))
    if ok and token in {"shown", "visible"}:
        lines.append(f"banner ....... {token}")
        state = "shown" if token == "shown" else "visible"
        return LaunchReport(summary=f"hammerspoon up · banner {state}", lines=lines)
    if ok and token == "disabled":
        lines.append("banner ....... off (live_banner false)")
        return LaunchReport(summary="hammerspoon up · banner off", lines=lines)
    detail = token or ("no reply" if ok else "ipc failed")
    lines.append(f"banner ....... not shown ({detail})")
    return LaunchReport(summary="hammerspoon up · banner hidden", lines=lines)
