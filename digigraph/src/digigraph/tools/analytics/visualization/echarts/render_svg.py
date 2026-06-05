"""Convert ECharts option dict to SVG via Node.js ECharts SSR (optional)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

_ECHARTS_DIR = Path(__file__).resolve().parent


def echarts_option_to_svg(
    option: dict[str, Any],
    width: int = 800,
    height: int = 500,
) -> str | None:
    """
    Render ECharts option to SVG using Node.js ECharts SSR.
    Returns SVG string on success, None if Node/echarts unavailable or render fails.
    Requires: Node.js and `npm install` in the echarts package directory.
    """
    script = _ECHARTS_DIR / "render_svg.mjs"
    if not script.is_file():
        return None
    node_modules = _ECHARTS_DIR / "node_modules"
    if not node_modules.is_dir():
        return None
    try:
        proc = subprocess.run(
            ["node", str(script), str(width), str(height)],
            input=json.dumps(option, default=str).encode("utf-8"),
            capture_output=True,
            cwd=str(_ECHARTS_DIR),
            timeout=30,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        return proc.stdout.decode("utf-8")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError, ValueError):
        return None
