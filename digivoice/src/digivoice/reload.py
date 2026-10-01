"""`digivoice reload`: refresh local control without touching the menubar.

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
from collections.abc import Callable, Mapping
from pathlib import Path

from digivoice.models import CliResult, VoicePaths
from digivoice.paths import resolve_paths
from digivoice.runner import CommandRunner, run_command
from digivoice.settings import load_settings
from digivoice.status import status_path

RELOAD_TIMEOUT_SECONDS = 8.0


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
