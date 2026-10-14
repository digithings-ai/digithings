"""The generated design token module stays in step with tokens.css."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENS = REPO_ROOT / "packages" / "design" / "tokens.ts"


def test_generated_tokens_match_tokens_css() -> None:
    proc = subprocess.run(
        ["node", "scripts/gen-design-tokens.mjs", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_generated_tokens_pin_the_live_theme_colours() -> None:
    text = TOKENS.read_text(encoding="utf-8")
    assert 'bg: { hex: "#0A0E0C", rgb: 0x0a0e0c }' in text
    assert 'ink: { hex: "#ECEEF0", rgb: 0xeceef0 }' in text
    assert 'accent: { hex: "#3DD6C4", rgb: 0x3dd6c4 }' in text
    assert 'up: { hex: "#3DD6C4", rgb: 0x3dd6c4 }' in text
    assert 'accentDigiquant: { hex: "#3DD6C4", rgb: 0x3dd6c4 }' in text
    assert 'accentDigiquant: { hex: "#0E8C7F", rgb: 0x0e8c7f }' in text
    assert 'danger: { hex: "#E94959", rgb: 0xe94959 }' in text
    assert 'bg: { hex: "#FBFBF9", rgb: 0xfbfbf9 }' in text
    assert 'accent: { hex: "#0C7C71", rgb: 0x0c7c71 }' in text
