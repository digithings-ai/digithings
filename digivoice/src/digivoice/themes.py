"""Theme resolution for digivoice banner and TUI.

Loads the single source of truth from digivoice/hammerspoon/theme_registry.json.
Both banner (Lua) and TUI (Python) read the same file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The exact palette IDs from OpenCode, in the specified order
PALETTE_IDS: tuple[str, ...] = (
    "aura",
    "ayu",
    "catppuccin",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "cobalt2",
    "cursor",
    "dracula",
    "everforest",
    "flexoki",
    "github",
    "gruvbox",
    "kanagawa",
    "material",
    "matrix",
    "mercury",
    "monokai",
    "nightowl",
    "nord",
    "one-dark",
    "osaka-jade",
    "orng",
    "lucent-orng",
    "palenight",
    "rosepine",
    "solarized",
    "synthwave84",
    "tokyonight",
    "vesper",
    "vercel",
    "zenburn",
    "carbonfox",
)

MODES: tuple[Literal["dark", "light", "system"], ...] = ("dark", "light", "system")


@dataclass(frozen=True)
class ThemeChrome:
    """Resolved chrome colors for banner and TUI.

    Mapping from palette variant:
    - bg = neutral
    - text = ink
    - accent = primary
    - border = accent
    """

    bg: str
    text: str
    accent: str
    border: str


# Legacy digivoice chrome (when no palette is selected)
# Legacy chrome matches banner_core.lua M.CHROME (no named palette).
# vesper dark ink is stored as #FFFFFF; the OpenCode file writes the same color as #FFF.
_LEGACY_DARK = ThemeChrome(
    bg="#000000",
    text="#ededed",
    accent="#ededed",
    border="#ffffff",
)
_LEGACY_LIGHT = ThemeChrome(
    bg="#f9f8f6",
    text="#141413",
    accent="#141413",
    border="#e8e6dc",
)


def _registry_path() -> Path:
    """Path to the theme registry JSON (digivoice/hammerspoon/theme_registry.json)."""
    # This file lives at digivoice/src/digivoice/themes.py
    # parents[2] = digivoice project directory
    return Path(__file__).resolve().parents[2] / "hammerspoon" / "theme_registry.json"


def _load_registry() -> dict:
    """Load the theme registry JSON."""
    path = _registry_path()
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B) tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def sgr_fg(hex_color: str) -> str:
    """Truecolor CSI for foreground: ESC[38;2;R;G;Bm.

    Invalid hex returns empty string (no color) rather than crashing.
    """
    try:
        r, g, b = _hex_to_rgb(hex_color)
        return f"\x1b[38;2;{r};{g};{b}m"
    except Exception:
        return ""


def resolve_theme(
    palette_id: str | None,
    mode: str,
    *,
    system_dark: bool,
) -> ThemeChrome:
    """Resolve a ThemeChrome for the given palette and mode.

    Args:
        palette_id: One of PALETTE_IDS, or None/empty for legacy chrome.
        mode: "dark", "light", or "system".
        system_dark: When mode is "system", use dark variant if True.

    Returns:
        ThemeChrome with bg, text, accent, border as hex strings.
    """
    # Empty palette -> legacy chrome
    if not palette_id:
        if mode == "light":
            return _LEGACY_LIGHT
        if mode == "dark":
            return _LEGACY_DARK
        # system or unknown mode
        return _LEGACY_DARK if system_dark else _LEGACY_LIGHT

    # Known palette - only use palette for valid modes
    if mode not in MODES:
        # Unknown mode falls back to legacy dark
        return _LEGACY_DARK

    registry = _load_registry()
    palettes = registry.get("palettes", {})
    if palette_id not in palettes:
        # Unknown palette falls back to legacy
        if mode == "light":
            return _LEGACY_LIGHT
        if mode == "dark":
            return _LEGACY_DARK
        return _LEGACY_DARK if system_dark else _LEGACY_LIGHT

    palette = palettes[palette_id]
    variant = "dark" if (mode == "dark" or (mode == "system" and system_dark)) else "light"
    colors = palette[variant]

    # Mapping: bg=neutral, text=ink, accent=primary, border=accent
    return ThemeChrome(
        bg=colors["neutral"],
        text=colors["ink"],
        accent=colors["primary"],
        border=colors["accent"],
    )


def banner_chrome(
    palette_id: str | None,
    mode: str,
    *,
    system_dark: bool,
) -> ThemeChrome:
    """Chrome for the Hammerspoon banner. Delegates to resolve_theme."""
    return resolve_theme(palette_id, mode, system_dark=system_dark)


def tui_chrome(
    palette_id: str | None,
    mode: str,
    *,
    system_dark: bool,
) -> ThemeChrome:
    """Chrome for the TUI. Delegates to resolve_theme."""
    return resolve_theme(palette_id, mode, system_dark=system_dark)


def active_tui_chrome(
    palette_id: str | None,
    mode: str,
    *,
    system_dark: bool,
) -> ThemeChrome | None:
    """TUI paint chrome. Empty palette returns None so legacy SGR stays."""
    if not palette_id:
        return None
    return tui_chrome(palette_id, mode, system_dark=system_dark)


def system_is_dark(env: dict | None = None) -> bool:
    """DIGIVOICE_THEME=dark/light pins the system mode. Otherwise dark."""
    table = env or {}
    override = str(table.get("DIGIVOICE_THEME", "")).lower()
    if override == "light":
        return False
    if override == "dark":
        return True
    return True


def theme_payload(palette_id: str | None, mode: str, *, system_dark: bool) -> dict[str, str | bool]:
    """Screen payload so the terminal UI paints the same chrome as the banner."""
    chrome = resolve_theme(palette_id, mode, system_dark=system_dark)
    return {
        "palette": palette_id or "",
        "mode": mode if mode in MODES else "system",
        "active": bool(palette_id),
        "bg": chrome.bg,
        "text": chrome.text,
        "accent": chrome.accent,
        "border": chrome.border,
    }


__all__ = [
    "PALETTE_IDS",
    "MODES",
    "ThemeChrome",
    "resolve_theme",
    "banner_chrome",
    "tui_chrome",
    "active_tui_chrome",
    "system_is_dark",
    "theme_payload",
    "sgr_fg",
]
