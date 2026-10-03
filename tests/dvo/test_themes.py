"""Canonical theme registry: banner and terminal UI share one palette."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from digivoice.menu_tree import rows_at
from digivoice.settings import VoiceSettings, parse_setting_value, set_setting
from digivoice.themes import (
    MODES,
    PALETTE_IDS,
    ThemeChrome,
    banner_chrome,
    resolve_theme,
    tui_chrome,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "digivoice" / "hammerspoon" / "theme_registry.json"
LUA = next(
    (found for name in ("lua5.4", "lua5.3", "lua") if (found := shutil.which(name))),
    None,
)


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_lists_every_palette_and_the_three_modes() -> None:
    data = _registry()
    assert data["modes"] == ["dark", "light", "system"]
    assert MODES == ("dark", "light", "system")
    assert list(data["palettes"]) == list(PALETTE_IDS)


def test_resolve_theme_matches_registry_hex() -> None:
    palettes = _registry()["palettes"]
    for pid in PALETTE_IDS:
        for mode in ("dark", "light"):
            got = resolve_theme(pid, mode, system_dark=(mode == "dark"))
            variant = palettes[pid][mode]
            assert got == ThemeChrome(
                bg=variant["neutral"],
                text=variant["ink"],
                accent=variant["primary"],
                border=variant["accent"],
            )


def test_system_mode_follows_the_appearance_flag() -> None:
    for pid in PALETTE_IDS:
        assert resolve_theme(pid, "system", system_dark=True) == resolve_theme(
            pid, "dark", system_dark=True
        )
        assert resolve_theme(pid, "system", system_dark=False) == resolve_theme(
            pid, "light", system_dark=False
        )


def test_empty_palette_keeps_legacy_chrome() -> None:
    dark = resolve_theme("", "dark", system_dark=True)
    light = resolve_theme(None, "light", system_dark=False)
    assert dark.bg == "#000000"
    assert dark.text == "#ededed"
    assert light.bg == "#f9f8f6"
    assert light.text == "#141413"


def test_banner_and_tui_resolve_the_same_palette() -> None:
    for pid in ("dracula", "github", "tokyonight"):
        for mode in ("dark", "light"):
            banner = banner_chrome(pid, mode, system_dark=(mode == "dark"))
            tui = tui_chrome(pid, mode, system_dark=(mode == "dark"))
            assert banner == tui
            assert banner == resolve_theme(pid, mode, system_dark=(mode == "dark"))


def test_settings_palette_round_trip(tmp_path: Path) -> None:
    from digivoice.paths import resolve_paths

    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    saved = set_setting(paths, "theme_palette", "dracula")
    assert saved.theme_palette == "dracula"
    assert parse_setting_value("theme_palette", "legacy") == ""
    with pytest.raises(ValueError):
        parse_setting_value("theme_palette", "bogus")
    banner = banner_chrome(saved.theme_palette, "dark", system_dark=True)
    tui = tui_chrome(saved.theme_palette, "dark", system_dark=True)
    assert banner == tui
    assert banner.bg == "#1d1e28"


def test_terminal_settings_lists_theme_mode_and_palette() -> None:
    root = rows_at(VoiceSettings(), "/settings")
    assert "theme" in [row.name for row in root]
    theme = rows_at(VoiceSettings(theme_palette="nord", theme_mode="light"), "/settings/theme")
    assert [row.name for row in theme] == ["mode", "palette"]
    assert theme[0].value == "light"
    assert theme[1].value == "nord"
    modes = [row.choice for row in rows_at(VoiceSettings(), "/settings/theme/mode")]
    palettes = [row.choice for row in rows_at(VoiceSettings(), "/settings/theme/palette")]
    assert modes == ["dark", "light", "system"]
    assert palettes[0] == "legacy"
    assert palettes[1:] == list(PALETTE_IDS)


@pytest.mark.skipif(LUA is None, reason="no lua interpreter on PATH")
def test_lua_banner_reads_the_same_dracula_ground() -> None:
    script = f"""
    local core = dofile("{ROOT / "digivoice" / "hammerspoon" / "banner_core.lua"}")
    local colors = core.theme_colors("dark", "dracula")
    assert(math.abs(colors.bg.red - 0x1d / 255) < 0.002)
    assert(math.abs(colors.bg.green - 0x1e / 255) < 0.002)
    assert(math.abs(colors.bg.blue - 0x28 / 255) < 0.002)
    assert(core.theme_colors("dark").bg.red == 0)
    print("PASS")
    """
    result = subprocess.run([LUA, "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_named_palette_recolors_menu_rows_values_and_status() -> None:
    """Rows, values, and status follow the payload. An empty palette does not."""
    dark = json.loads(REGISTRY.read_text(encoding="utf-8"))["palettes"]["tokyonight"]["dark"]
    ink = dark["ink"]
    primary = dark["primary"]
    app = (ROOT / "digivoice" / "tui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "menuPaint(activeTheme, truecolor)" in app
    assert "menuPaint(activeTheme, truecolor).row" in app
    assert "screenPaint(activeTheme).foreground" in app
    script = f"""
import {{ menuPaint }} from "./digivoice/tui/src/menu_colors.js"
const named = menuPaint({{ active: true, text: {ink!r}, accent: {primary!r} }}, true)
const empty = menuPaint(null, true)
const channels = (hex) => {{
  const body = hex.slice(1)
  const value = Number.parseInt(body, 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}}
const same = (got, want) => got && got.join() === want.join()
if (!same(named.row, channels({ink!r}))) process.exit(1)
if (!same(named.value, channels({ink!r}))) process.exit(1)
if (same(named.value, [175, 175, 175])) process.exit(1)
if (!same(named.status, channels({primary!r}))) process.exit(1)
if (!same(named.statusText, channels({ink!r}))) process.exit(1)
if (empty.row !== null || empty.status !== null || empty.statusText !== null) process.exit(1)
if (!same(empty.value, [175, 175, 175])) process.exit(1)
console.log("PASS")
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_screen_paint_covers_the_theme_ground() -> None:
    """The screen behind the wordmark and menu follows the palette ground."""
    palettes = _registry()["palettes"]
    light = palettes["matrix"]["light"]
    dark = palettes["matrix"]["dark"]
    app = (ROOT / "digivoice" / "tui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "setBackgroundColor" in app
    assert "screenPaint(activeTheme)" in app
    script = f"""
import {{ screenPaint }} from "./digivoice/tui/src/menu_colors.js"
const channels = (hex) => {{
  const body = hex.slice(1)
  const value = Number.parseInt(body, 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}}
const same = (got, want) => got && got.join() === want.join()
const luminance = (rgb) => {{
  const linear = (channel) => {{
    const c = channel / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }}
  return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2])
}}
const empty = screenPaint(null)
const off = screenPaint({{ active: false, bg: "#000000", text: "#ffffff", accent: "#ffffff" }})
for (const paint of [empty, off]) {{
  if (paint.background !== null || paint.ink !== null || paint.foreground !== null) process.exit(1)
}}
const lightPaint = screenPaint({{ active: true, bg: {light["neutral"]!r}, text: {light["ink"]!r}, accent: {light["accent"]!r} }})
if (!same(lightPaint.background, channels({light["neutral"]!r}))) process.exit(1)
if (!same(lightPaint.ink, channels({light["ink"]!r}))) process.exit(1)
if (!(luminance(lightPaint.background) > luminance(lightPaint.ink))) process.exit(1)
if (!same(lightPaint.foreground, channels({light["ink"]!r}))) process.exit(1)
const darkPaint = screenPaint({{ active: true, bg: {dark["neutral"]!r}, text: {dark["ink"]!r}, accent: {dark["accent"]!r} }})
if (!same(darkPaint.background, channels({dark["neutral"]!r}))) process.exit(1)
if (!same(darkPaint.ink, channels({dark["ink"]!r}))) process.exit(1)
if (!(luminance(darkPaint.background) < luminance(darkPaint.ink))) process.exit(1)
const flat = screenPaint({{ active: true, bg: "#eef3ea", text: "#203022", accent: "#eef3ea" }})
if (!same(flat.foreground, channels("#203022"))) process.exit(1)
const vivid = screenPaint({{ active: true, bg: "#0a0e0a", text: "#62ff94", accent: "#c770ff" }})
if (!same(vivid.foreground, channels("#c770ff"))) process.exit(1)
if (!same(vivid.background, channels("#0a0e0a"))) process.exit(1)
console.log("PASS")
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
