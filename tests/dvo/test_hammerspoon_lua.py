"""Hammerspoon adapter + banner core, driven by a fake `hs` under plain Lua 5.3+.

Skipped when no `lua` is installed; the Python side of cancel/empty/status is covered
in test_cancel_empty.py either way.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
LUA_DIR = REPO / "tests" / "dvo" / "lua"
ADAPTER = REPO / "digivoice" / "hammerspoon"
LUA = next((found for name in ("lua5.4", "lua5.3", "lua") if (found := shutil.which(name))), None)

needs_lua = pytest.mark.skipif(LUA is None, reason="no lua interpreter on PATH")

SCENARIOS = re.findall(
    r"^function scenarios\.(\w+)\(\)", (LUA_DIR / "hs_flows.lua").read_text(), re.MULTILINE
)


def _lua(script: str, *args: str, env_extra: dict[str, str] | None = None) -> str:
    assert LUA is not None
    env = {**os.environ, **(env_extra or {})}
    proc = subprocess.run(
        [LUA, script, *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return proc.stdout


def test_scenarios_were_discovered() -> None:
    assert len(SCENARIOS) >= 10


@needs_lua
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_adapter_flow(scenario: str, tmp_path: Path) -> None:
    out = _lua(
        str(LUA_DIR / "hs_flows.lua"),
        scenario,
        env_extra={
            "DIGIVOICE_DATA_DIR": str(tmp_path),
            "DIGIVOICE_BIN": "/opt/test/bin/digivoice",
            "DIGIVOICE_THEME": "dark",
            "DIGIVOICE_PBCOPY_FILE": str(tmp_path / "clip.txt"),
        },
    )
    assert f"PASS {scenario}" in out


@needs_lua
def test_banner_core_checks() -> None:
    out = _lua(str(LUA_DIR / "banner_core_check.lua"), env_extra={"ADAPTER_DIR": str(ADAPTER)})
    assert "PASS banner_core" in out


@needs_lua
def test_hotkey_binding_checks() -> None:
    out = _lua(str(LUA_DIR / "hotkeys_check.lua"), env_extra={"ADAPTER_DIR": str(ADAPTER)})
    assert "PASS hotkeys" in out


@needs_lua
@pytest.mark.parametrize("name", ["init.lua", "banner_core.lua", "hotkeys.lua"])
def test_adapter_sources_compile(name: str) -> None:
    assert LUA is not None
    proc = subprocess.run(
        [LUA, "-e", f'assert(loadfile("{ADAPTER / name}"))'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
