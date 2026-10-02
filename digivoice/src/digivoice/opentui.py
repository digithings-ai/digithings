"""Launch the OpenTUI process. The Python CLI stays for non-TTY commands."""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from digivoice.banner_launch import mark_tui_closed, mark_tui_open
from digivoice.paths import resolve_paths

NAV_FOOTER = "↑↓ move · enter select · esc back · click"


def tui_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tui"


def _tui_runtime(env: Mapping[str, str]) -> str:
    """Bun, as the OpenTUI quickstart runs it. ``DIGIVOICE_NODE`` overrides the binary."""
    chosen = env.get("DIGIVOICE_NODE", "").strip()
    if chosen:
        return chosen
    bun = shutil.which("bun")
    if bun:
        return bun
    home_bun = Path.home() / ".bun" / "bin" / "bun"
    if home_bun.is_file():
        return str(home_bun)
    local_bun = Path.home() / ".local" / "bin" / "bun"
    if local_bun.is_file():
        return str(local_bun)
    return shutil.which("node") or "node"


def opentui_argv(env: Mapping[str, str] | None = None) -> list[str]:
    """The OpenTUI app. ``main.js`` calls ``createCliRenderer``."""
    table = env or os.environ
    runtime = _tui_runtime(table)
    script = tui_root() / "src" / "main.js"
    return [runtime, str(script)]


def launch_opentui(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    *,
    start: str = "/",
) -> int:
    """Replace this process with the OpenTUI app. Returns only when it cannot start."""
    argv = opentui_argv(env)
    script = Path(argv[1])
    node = argv[0]
    if not script.is_file() or (not Path(node).is_file() and shutil.which(node) is None):
        sys.stderr.write("digivoice: OpenTUI is not available (node or digivoice/tui missing)\n")
        return 1
    paths = resolve_paths(platform, home, env)
    mark_tui_open(paths.data_dir)
    child = dict(env)
    src = str(Path(__file__).resolve().parents[1])
    prior = child.get("PYTHONPATH", "")
    child["PYTHONPATH"] = src if not prior else src + os.pathsep + prior
    child["DIGIVOICE_DATA_DIR"] = paths.data_dir
    child["DIGIVOICE_TUI_START"] = start
    child["DIGIVOICE_PYTHON"] = sys.executable
    child["DIGIVOICE_ARGV"] = json.dumps(list(sys.argv))
    child["DIGIVOICE_NODE"] = node
    child["PATH"] = str(Path(node).parent) + os.pathsep + child.get("PATH", "")
    try:
        os.execve(node, argv, child)
    except OSError as exc:
        mark_tui_closed(paths.data_dir)
        sys.stderr.write(f"digivoice: could not start the OpenTUI process: {exc}\n")
        return 1
    return 0


__all__ = ["NAV_FOOTER", "launch_opentui", "opentui_argv", "tui_root"]
