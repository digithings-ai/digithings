#!/usr/bin/env python3
"""Generate circular-dot QR *badge* SVGs (dark + light) for a site brand mark.

Mirrors the digithings `favicon-qr.svg` / `favicon-qr-light.svg` style exactly:
a rounded container with a white (dark badge) or ink (light badge) dot matrix,
the matrix laid out in a 1023-unit inner space and inset via
`translate(123 123) scale(0.7596)` so it carries a generous quiet zone.

Dependencies:
    pip install "qrcode==8.0"

Usage:
    python3 scripts/generate-qr-badge.py https://digiquant.io \
        frontend/digiquant-web/public/favicon-qr.svg \
        frontend/digiquant-web/public/favicon-qr-light.svg
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Layout constants lifted verbatim from the digithings badge so both sites'
# marks are visually identical in weight and quiet-zone.
SIZE = 1023
INSET = 123  # translate offset
SCALE = 0.7596  # group scale → matrix occupies the central ~777px
R_RATIO = 0.48  # dot radius as a fraction of one module step


def _matrix(url: str) -> list[list[bool]]:
    try:
        import qrcode
        import qrcode.constants
    except ModuleNotFoundError:
        sys.exit("qrcode not installed. Run: pip install 'qrcode==8.0'")
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


def _dots(matrix: list[list[bool]], fill: str) -> str:
    n = len(matrix)
    step = SIZE / n
    r = step * R_RATIO
    parts = [f'<g fill="{fill}">']
    for row_idx, row in enumerate(matrix):
        for col_idx, cell in enumerate(row):
            if cell:
                cx = (col_idx + 0.5) * step
                cy = (row_idx + 0.5) * step
                parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>')
    parts.append("</g>")
    return "\n".join(parts)


def _badge(matrix: list[list[bool]], *, container: str, dot_fill: str) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">',
            container,
            f'<g transform="translate({INSET} {INSET}) scale({SCALE})">',
            _dots(matrix, dot_fill),
            "</g>",
            "</svg>",
        ]
    )


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit("usage: generate-qr-badge.py <url> <dark-out.svg> <light-out.svg>")
    url, dark_out, light_out = sys.argv[1], sys.argv[2], sys.argv[3]
    matrix = _matrix(url)

    dark = _badge(
        matrix,
        container=f'<rect width="{SIZE}" height="{SIZE}" rx="208" fill="#0a0a0b"/>',
        dot_fill="#ffffff",
    )
    light = _badge(
        matrix,
        container='<rect x="5" y="5" width="1013" height="1013" rx="204"'
        ' fill="#ffffff" stroke="#e7e2d6" stroke-width="10"/>',
        dot_fill="#15140f",
    )

    for rel, svg in ((dark_out, dark), (light_out, light)):
        path = REPO_ROOT / rel
        path.write_text(svg + "\n", encoding="utf-8")
        try:
            shown = path.relative_to(REPO_ROOT)
        except ValueError:
            shown = path
        print(f"Written {len(svg):,} chars → {shown}")


if __name__ == "__main__":
    main()
