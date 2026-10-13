"""The one place the client-facing tearsheet names its monospace face (DIG-2375).

The tearsheet is generated HTML, not a Next.js app, so it has no ``next/font``
config: it links Google Fonts and lets the browser pick the first family in the
stack that exists. Every mono surface here — the page CSS and the Plotly
layouts — reads :data:`MONO_FONT_STACK` from this module.

Swap the tearsheet mono face by editing :data:`MONO_FONT_FAMILY` on one line.
``MONO_FONT_STACK`` and ``GOOGLE_FONTS_HREF`` follow it. The web apps do the
same through ``apps/<app>/app/fonts.ts``; see "Fonts per surface" in
``packages/design/README.md``.

Geist Mono has no U+25B8 (small right triangle), U+25BE (small down triangle) or
U+2318 (command key), so the chain after the face stays a real one — it is the
same fallback list ``packages/design/tokens.css`` uses.
"""

from __future__ import annotations

#: The one line to edit when the tearsheet's mono face changes.
MONO_FONT_FAMILY = "Geist Mono"

#: CSS/Plotly font stack. First family wins when it loads; the rest cover the
#: glyphs :data:`MONO_FONT_FAMILY` lacks and machines that never fetch the web
#: font. Keep in step with ``--font-stack-mono`` in ``packages/design/tokens.css``.
MONO_FONT_STACK = (
    f"'{MONO_FONT_FAMILY}', ui-monospace, 'SF Mono', Menlo, Consolas, "
    "'DejaVu Sans Mono', 'Segoe UI Symbol', monospace"
)

#: Google Fonts request for the tearsheet. ``IBM Plex Sans`` stays: the sans
#: face did not change in DIG-2375.
GOOGLE_FONTS_HREF = (
    "https://fonts.googleapis.com/css2"
    f"?family={MONO_FONT_FAMILY.replace(' ', '+')}:wght@300;400;500;600"
    "&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap"
)
