#!/usr/bin/env python3
"""Generate the platform palette CSS and the TypeScript registry.

Source of names and the four hexes (neutral, ink, primary, accent) is
``digivoice/hammerspoon/theme_registry.json``. DigiVoice behaviour is not
changed. This script only derives web and terminal tokens (color-mix
percentages, on-accent by contrast, a readable danger) and writes:

- ``packages/design/palettes.css``
- ``packages/ui/src/theme/palette-registry.ts``
- ``packages/ui/src/components/themeInit.ts``

``default`` is not generated. With no ``data-palette``, tokens.css is the look.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "digivoice/hammerspoon/theme_registry.json"
CSS_OUT = ROOT / "packages/design/palettes.css"
TS_OUT = ROOT / "packages/ui/src/theme/palette-registry.ts"
INIT_OUT = ROOT / "packages/ui/src/components/themeInit.ts"

# Floors. Text is WCAG AA (4.5) or UI-component (3.0). Hair is a line, not
# text: visible against the canvas without becoming a second ink.
INK_MIN = 4.5
SOFT_MIN = 4.5
MUTE_MIN = 3.0
HAIR_MIN = 1.5
SURFACE_MIN = 1.08
ACCENT_MIN = 3.0
DANGER_MIN = 3.0
ON_ACCENT_MIN = 4.5

# Canon danger from tokens.css. Kept when it already clears DANGER_MIN.
CANON_DANGER = {
    "dark": (0xE9, 0x49, 0x59),
    "light": (0xC3, 0x22, 0x32),
}
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# theme-color for the default palette. Matches tokens.css --bg.
DEFAULT_BG = {"light": "#FBFBF9", "dark": "#0A0E0C"}


def parse_hex(value: str) -> tuple[int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def hex_of(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _chan(c: float) -> float:
    v = c / 255.0
    if v <= 0.04045:
        return v / 12.92
    return ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _chan(r) + 0.7152 * _chan(g) + 0.0722 * _chan(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    hi, lo = luminance(a), luminance(b)
    if hi < lo:
        hi, lo = lo, hi
    return (hi + 0.05) / (lo + 0.05)


def mix(fg: tuple[int, int, int], bg: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """``t`` is the portion of ``fg`` (0–1), matching CSS color-mix percentages."""
    return tuple(int(round(fg[i] * t + bg[i] * (1.0 - t))) for i in range(3))  # type: ignore[return-value]


def portion_for(fg, bg, target: float, start: float) -> tuple[int, tuple[int, int, int]]:
    """Smallest ink percentage at or above ``start`` that clears ``target``."""
    begin = max(0, min(100, int(round(start * 100))))
    for pct in range(begin, 101):
        color = mix(fg, bg, pct / 100.0)
        if contrast(color, bg) + 1e-9 >= target:
            return pct, color
    return 100, fg


def toward_pole(color, bg, target: float) -> tuple[tuple[int, int, int], int, tuple[int, int, int]]:
    """Mix ``color`` toward white or black until ``target`` contrast on ``bg``.

    Returns (result, percent of the original color, pole). 100 means unchanged.
    """
    if contrast(color, bg) + 1e-9 >= target:
        return color, 100, color
    pole = WHITE if contrast(WHITE, bg) >= contrast(BLACK, bg) else BLACK
    # Highest percentage of the source that still clears the floor.
    chosen = pole
    chosen_pct = 0
    for pct in range(100, -1, -1):
        mixed = mix(color, pole, pct / 100.0)
        if contrast(mixed, bg) + 1e-9 >= target:
            chosen = mixed
            chosen_pct = pct
            break
    return chosen, chosen_pct, pole


def on_accent(accent: tuple[int, int, int]) -> tuple[int, int, int]:
    """Black or white, whichever contrasts more with the accent."""
    return WHITE if contrast(WHITE, accent) >= contrast(BLACK, accent) else BLACK


def derive_mode(colors: dict[str, str], mode: str) -> dict:
    neutral = parse_hex(colors["neutral"])
    ink_src = parse_hex(colors["ink"])
    primary = parse_hex(colors["primary"])
    bg = neutral

    ink, ink_pct, ink_pole = toward_pole(ink_src, bg, INK_MIN)
    soft_pct, soft = portion_for(ink, bg, SOFT_MIN, 0.78)
    mute_pct, mute = portion_for(ink, bg, MUTE_MIN, 0.58)
    if soft_pct < mute_pct:
        soft_pct, soft = mute_pct, mute
    hair_pct, hair = portion_for(ink, bg, HAIR_MIN, 0.16)
    # Keep the line quieter than mute text when the floor allows it.
    hair_cap = max(hair_pct, min(mute_pct - 12, 70))
    if hair_cap < hair_pct:
        hair_cap = hair_pct
    if hair_pct < hair_cap and contrast(mix(ink, bg, hair_cap / 100.0), bg) >= HAIR_MIN:
        # portion_for already returned the minimum. Don't raise it.
        pass
    hair2_pct = min(100, hair_pct + 8)
    hair2 = mix(ink, bg, hair2_pct / 100.0)

    surf_pct, surface = portion_for(ink, bg, SURFACE_MIN, 0.05)
    if surf_pct >= hair_pct:
        quieter = max(3, hair_pct - 3)
        candidate = mix(ink, bg, quieter / 100.0)
        if contrast(candidate, bg) + 1e-9 >= SURFACE_MIN:
            surf_pct, surface = quieter, candidate
    surf2_pct = min(99, surf_pct + 4)
    surface2 = mix(ink, bg, surf2_pct / 100.0)

    accent, accent_pct, accent_pole = toward_pole(primary, bg, ACCENT_MIN)
    on = on_accent(accent)
    danger_src = CANON_DANGER[mode]
    danger, danger_pct, danger_pole = toward_pole(danger_src, bg, DANGER_MIN)

    adjusted: list[str] = []
    if ink_pct < 100:
        adjusted.append("ink")
    if accent_pct < 100:
        adjusted.append("accent")
    if danger_pct < 100:
        adjusted.append("danger")
    on_ratio = contrast(on, accent)
    if on_ratio + 1e-9 < ON_ACCENT_MIN:
        adjusted.append("on-accent")

    return {
        "bg": bg,
        "bg_hex": colors["neutral"],
        "ink_src": colors["ink"],
        "ink_src_rgb": ink_src,
        "ink": ink,
        "ink_pct": ink_pct,
        "ink_pole": ink_pole,
        "soft_pct": soft_pct,
        "soft": soft,
        "mute_pct": mute_pct,
        "mute": mute,
        "hair_pct": hair_pct,
        "hair": hair,
        "hair2_pct": hair2_pct,
        "hair2": hair2,
        "surf_pct": surf_pct,
        "surface": surface,
        "surf2_pct": surf2_pct,
        "surface2": surface2,
        "primary": colors["primary"],
        "primary_rgb": primary,
        "accent": accent,
        "accent_pct": accent_pct,
        "accent_pole": accent_pole,
        "on_accent": on,
        "on_accent_ratio": on_ratio,
        "danger": danger,
        "danger_pct": danger_pct,
        "danger_pole": danger_pole,
        "registry_accent": colors["accent"],
        "adjusted": adjusted,
        "ratios": {
            "ink": contrast(ink, bg),
            "soft": contrast(soft, bg),
            "mute": contrast(mute, bg),
            "hair": contrast(hair, bg),
            "surface": contrast(surface, bg),
            "accent": contrast(accent, bg),
            "on_accent": on_ratio,
            "danger": contrast(danger, bg),
        },
    }


def _mix_css(src: str, dest_hex: str, pct: int) -> str:
    if pct >= 100:
        return src
    if pct <= 0:
        return dest_hex
    return f"color-mix(in srgb, {src} {pct}%, {dest_hex})"


def _ink_css(mode: dict) -> str:
    if mode["ink_pct"] >= 100:
        return mode["ink_src"]
    pole = hex_of(mode["ink_pole"])
    return _mix_css(mode["ink_src"], pole, mode["ink_pct"])


def _accent_css(mode: dict) -> str:
    if mode["accent_pct"] >= 100:
        return mode["primary"]
    pole = hex_of(mode["accent_pole"])
    return _mix_css(mode["primary"], pole, mode["accent_pct"])


def css_block(name: str, theme: str, mode: dict) -> str:
    ink_expr = _ink_css(mode)
    accent_expr = _accent_css(mode)
    if mode["danger_pct"] >= 100:
        danger_expr = hex_of(CANON_DANGER[theme])
    else:
        danger_expr = _mix_css(
            hex_of(CANON_DANGER[theme]), hex_of(mode["danger_pole"]), mode["danger_pct"]
        )
    hair_expr = f"color-mix(in srgb, {ink_expr} {mode['hair_pct']}%, transparent)"
    hair2_expr = f"color-mix(in srgb, {ink_expr} {mode['hair2_pct']}%, transparent)"
    soft_expr = _mix_css(ink_expr, mode["bg_hex"], mode["soft_pct"])
    mute_expr = _mix_css(ink_expr, mode["bg_hex"], mode["mute_pct"])
    surf_expr = _mix_css(ink_expr, mode["bg_hex"], mode["surf_pct"])
    surf2_expr = _mix_css(ink_expr, mode["bg_hex"], mode["surf2_pct"])
    weak = f"color-mix(in srgb, {accent_expr} 16%, transparent)"
    on = hex_of(mode["on_accent"])
    # Nested color-mix (ink itself is a color-mix) is valid CSS. When ink is a
    # raw hex the expressions stay flat.
    # The product shell and the embed shell set --term-bg themselves, and the
    # app-mode body paints a literal canvas. The same block has to land on
    # those elements or a stored palette only changes unused variables.
    lines = [
        f':root[data-palette="{name}"][data-theme="{theme}"],',
        f':root[data-palette="{name}"][data-theme="{theme}"] .digichat-thread,',
        f':root[data-palette="{name}"][data-theme="{theme}"] .dc-embed-shell,',
        f':root[data-palette="{name}"][data-theme="{theme}"] [data-stock-product][data-thread-skin="digichat"] {{',
        f"  --bg: {mode['bg_hex']};",
        f"  --surface: {surf_expr};",
        f"  --surface-2: {surf2_expr};",
        f"  --hair: {hair_expr};",
        f"  --hair-2: {hair2_expr};",
        f"  --ink: {ink_expr};",
        f"  --ink-soft: {soft_expr};",
        f"  --ink-mute: {mute_expr};",
        f"  --accent: {accent_expr};",
        f"  --accent-weak: {weak};",
        f"  --on-accent: {on};",
        f"  --danger: {danger_expr};",
        f"  --term-bg: {mode['bg_hex']};",
        f"  --term-ink: {ink_expr};",
        f"  --term-mute: {mute_expr};",
        f"  --term-hair: {hex_of(mode['hair'])};",
        f"  --term-fill: {surf_expr};",
        f"  --embed-canvas: {mode['bg_hex']};",
        f"  --background: {mode['bg_hex']};",
        f"  --foreground: {ink_expr};",
        f"  --destructive: {danger_expr};",
        "}",
        (
            f':root[data-palette="{name}"][data-theme="{theme}"] '
            'body:has([data-stock-product][data-thread-skin="digichat"][data-chrome-mode="app"]) {'
        ),
        f"  background: {mode['bg_hex']};",
        "}",
    ]
    return "\n".join(lines)


def load_registry() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    palettes = data["palettes"]
    if len(palettes) != 32:
        raise SystemExit(f"expected 32 palettes, found {len(palettes)}")
    return palettes


def derive_all(palettes: dict | None = None) -> list[tuple[str, dict]]:
    palettes = palettes if palettes is not None else load_registry()
    out = []
    for name in palettes:
        modes = {}
        for theme in ("dark", "light"):
            modes[theme] = derive_mode(palettes[name][theme], theme)
        out.append((name, modes))
    return out


def render_css(derived: list[tuple[str, dict]]) -> str:
    notes = []
    for name, modes in derived:
        for theme, mode in modes.items():
            if mode["adjusted"]:
                bits = ", ".join(mode["adjusted"])
                notes.append(f"{name} {theme}: {bits}")
    header = [
        "/* Generated by scripts/generate_platform_palettes.py — do not edit.",
        "   Source: digivoice/hammerspoon/theme_registry.json (32 palettes).",
        "   default is the absence of data-palette (tokens.css).",
        "   Selectors also retarget .digichat-thread, .dc-embed-shell, and the",
        "   product shell, because those elements set their own tokens.",
        "   Dashboard never sets data-palette, so these rules do not apply there.",
    ]
    if notes:
        header.append("   Contrast adjustments (derivation, not the JSON):")
        for note in notes:
            header.append(f"   - {note}")
    else:
        header.append("   No source colour needed a contrast adjustment.")
    header.append("*/")
    header.append("")
    blocks = [
        css_block(name, theme, modes[theme])
        for name, modes in derived
        for theme in ("dark", "light")
    ]
    return "\n".join(header) + "\n" + "\n\n".join(blocks) + "\n"


def _ts_string(value: str) -> str:
    return json.dumps(value)


def render_ts(derived: list[tuple[str, dict]]) -> str:
    names = [name for name, _ in derived]
    ids = ", ".join(_ts_string(name) for name in names)
    chunks = [
        "/* Generated by scripts/generate_platform_palettes.py — do not edit.",
        "   Hexes are the resolved terminal colours (color-mix already applied).",
        "   CSS percentages live in packages/design/palettes.css. */",
        "",
        f"export const PALETTE_IDS = [{ids}] as const;",
        "",
        "export type PaletteId = (typeof PALETTE_IDS)[number];",
        "",
        "export type PaletteTokens = {",
        "  bg: string;",
        "  surface: string;",
        "  surface2: string;",
        "  hair: string;",
        "  ink: string;",
        "  inkSoft: string;",
        "  inkMute: string;",
        "  accent: string;",
        "  onAccent: string;",
        "  danger: string;",
        "};",
        "",
        "export const PALETTES: Record<PaletteId, { dark: PaletteTokens; light: PaletteTokens }> = {",
    ]
    for name, modes in derived:
        chunks.append(f"  {_ts_string(name)}: {{")
        for theme in ("dark", "light"):
            mode = modes[theme]
            chunks.append(f"    {theme}: {{")
            pairs = {
                "bg": mode["bg_hex"],
                "surface": hex_of(mode["surface"]),
                "surface2": hex_of(mode["surface2"]),
                "hair": hex_of(mode["hair"]),
                "ink": hex_of(mode["ink"]),
                "inkSoft": hex_of(mode["soft"]),
                "inkMute": hex_of(mode["mute"]),
                "accent": hex_of(mode["accent"]),
                "onAccent": hex_of(mode["on_accent"]),
                "danger": hex_of(mode["danger"]),
            }
            for key, value in pairs.items():
                chunks.append(f"      {key}: {_ts_string(value)},")
            chunks.append("    },")
        chunks.append("  },")
    chunks.append("};")
    chunks.append("")
    return "\n".join(chunks)


def render_init(derived: list[tuple[str, dict]]) -> str:
    """Pre-paint script. Palette map is bg only (theme-color + data-palette)."""
    entries = []
    for name, modes in derived:
        dark = modes["dark"]["bg_hex"]
        light = modes["light"]["bg_hex"]
        entries.append(f"'{name}':{{d:'{dark}',l:'{light}'}}")
    palette_map = "{" + ",".join(entries) + "}"
    script = (
        "try{"
        "var s=localStorage.getItem('dt-theme');"
        "var t=(s==='light'||s==='dark')?s:(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');"
        "var e=document.documentElement;"
        "e.setAttribute('data-theme',t);"
        f"var P={palette_map};"
        "var p=localStorage.getItem('dt-palette');"
        f"var c=t==='light'?'{DEFAULT_BG['light']}':'{DEFAULT_BG['dark']}';"
        "if(p&&p!=='default'&&P[p]){e.setAttribute('data-palette',p);c=t==='light'?P[p].l:P[p].d;}"
        "else{e.removeAttribute('data-palette');}"
        "var m=document.querySelector('meta[name=\"theme-color\"]');"
        "if(!m){m=document.createElement('meta');m.setAttribute('name','theme-color');document.head.appendChild(m);}"
        "m.setAttribute('content',c);"
        "}catch(err){document.documentElement.setAttribute('data-theme','dark');}"
    )
    # The script is one line on purpose: it is inlined before paint.
    return (
        "/**\n"
        " * The pre-paint theme script, as a plain string module.\n"
        " *\n"
        ' * It must NOT live in a "use client" file. Root layouts are server\n'
        " * components; importing a non-component value from a client module gives\n"
        " * them a client reference instead of the string. Generated by\n"
        " * scripts/generate_platform_palettes.py — do not edit the script body.\n"
        " *\n"
        " * `dt-theme` is light, dark, or absent (auto / follow the OS).\n"
        " * `dt-palette` is a palette id or absent (default). The palette key is\n"
        " * never written by the dashboard, and this script never writes storage.\n"
        " */\n"
        "/** Inline in <head> before paint: <script dangerouslySetInnerHTML={{__html: themeInitScript}}/> */\n"
        "export const themeInitScript =\n"
        f"  {json.dumps(script)};\n"
    )


def render() -> tuple[str, str, str]:
    derived = derive_all()
    return render_css(derived), render_ts(derived), render_init(derived)


def main() -> None:
    css, ts, init = render()
    CSS_OUT.write_text(css, encoding="utf-8")
    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.write_text(ts, encoding="utf-8")
    INIT_OUT.write_text(init, encoding="utf-8")
    derived = derive_all()
    adjusted = [
        f"{name}/{theme}: {', '.join(mode['adjusted'])}"
        for name, modes in derived
        for theme, mode in modes.items()
        if mode["adjusted"]
    ]
    print(f"wrote {CSS_OUT.relative_to(ROOT)}")
    print(f"wrote {TS_OUT.relative_to(ROOT)}")
    print(f"wrote {INIT_OUT.relative_to(ROOT)}")
    print(f"palettes: {len(derived)}")
    if adjusted:
        print("contrast adjustments:")
        for row in adjusted:
            print(f"  {row}")
    else:
        print("contrast adjustments: none")


if __name__ == "__main__":
    main()
