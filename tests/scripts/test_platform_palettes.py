"""Generated platform palettes stay in sync with the DigiVoice registry.

The JSON is the source of names and the four source hexes. This test
refuses a hand-edit of the CSS or TypeScript tables, and it checks the
derived tokens still clear the contrast floors.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_platform_palettes.py"


def _load() -> Any:
    name = "generate_platform_palettes_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gen = _load()


def test_generated_files_match_the_registry() -> None:
    css, ts, init = gen.render()
    assert gen.CSS_OUT.read_text(encoding="utf-8") == css
    assert gen.TS_OUT.read_text(encoding="utf-8") == ts
    assert gen.INIT_OUT.read_text(encoding="utf-8") == init


def test_init_script_parses_and_quotes_hyphenated_keys() -> None:
    _css, _ts, init = gen.render()
    start = init.index("export const themeInitScript =\n  ")
    literal = init[start:].split("\n  ", 1)[1]
    literal = literal.removesuffix(";\n")
    script = json.loads(literal)
    assert "'catppuccin-frappe'" in script
    assert "catppuccin-frappe:" not in script
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(script)
        path = handle.name
    result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_derived_tokens_clear_contrast_floors() -> None:
    derived = gen.derive_all()
    assert len(derived) == 32
    floors = {
        "ink": gen.INK_MIN,
        "soft": gen.SOFT_MIN,
        "mute": gen.MUTE_MIN,
        "hair": gen.HAIR_MIN,
        "surface": gen.SURFACE_MIN,
        "accent": gen.ACCENT_MIN,
        "on_accent": gen.ON_ACCENT_MIN,
        "danger": gen.DANGER_MIN,
    }
    for name, modes in derived:
        for theme, mode in modes.items():
            for key, floor in floors.items():
                ratio = mode["ratios"][key]
                assert ratio + 1e-9 >= floor, f"{name}/{theme} {key} {ratio} < {floor}"



@pytest.mark.parametrize(
    "surface",
    [".digichat-thread", ".dc-embed-shell", '[data-stock-product][data-thread-skin="digichat"]'],
)
def test_every_palette_block_retargets_each_token_surface(surface: str) -> None:
    css, _, _ = gen.render()
    palettes = len(json.loads(gen.REGISTRY.read_text(encoding="utf-8"))["palettes"])
    assert palettes == 32
    for theme in ("dark", "light"):
        # Exactly one block per palette in this mode lists the surface.
        assert css.count(f'"][data-theme="{theme}"] {surface}') == palettes, (surface, theme)
