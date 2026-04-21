#!/usr/bin/env python3
"""Generate frontend/website/assets/qrw.svg — a circular-dot QR code for digithings.ai.

Dependencies:
    pip install "qrcode==8.0"

Usage:
    python3 scripts/generate-qr.py
    make qr-logo

Spec:
    URL:             https://digithings.ai
    ECC level:       H (highest — tolerates ~30% damage)
    Module style:    filled circles (#ffffff, transparent background)
    Output:          frontend/website/assets/qrw.svg (1023×1023 px viewBox)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "frontend" / "website" / "assets" / "qrw.svg"
URL = "https://digithings.ai"

try:
    import qrcode
    import qrcode.constants
except ModuleNotFoundError:
    sys.exit("qrcode not installed. Run: pip install 'qrcode==8.0'")

# ── Generate matrix ─────────────────────────────────────────────────────────
qr = qrcode.QRCode(
    version=None,
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=1,
    border=4,
)
qr.add_data(URL)
qr.make(fit=True)
matrix = qr.get_matrix()

# ── Render SVG with circular modules ────────────────────────────────────────
SIZE = 1023
n = len(matrix)
step = SIZE / n
r = step * 0.48  # radius fills ~96% of each cell

parts: list[str] = [
    f'<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve"'
    f' width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}"'
    f' style="max-width:100%;height:auto;">',
    '<g fill="#ffffff">',
]

for row_idx, row in enumerate(matrix):
    for col_idx, cell in enumerate(row):
        if cell:
            cx = (col_idx + 0.5) * step
            cy = (row_idx + 0.5) * step
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>')

parts += ["</g>", "</svg>"]
svg = "\n".join(parts)

OUT.write_text(svg, encoding="utf-8")
print(f"Written {len(svg):,} chars → {OUT.relative_to(REPO_ROOT)}")
