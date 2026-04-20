# website/

Static landing page for [digithings.ai](https://digithings.ai) — vanilla
HTML, CSS, and ES modules, with a canvas starfield background. Deployed
via GitHub Pages from this directory.

## Files

| File                  | Purpose                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `index.html`          | Landing page markup                                              |
| `tokens.css`          | Design-system tokens (colors, type, spacing, per-module accents) |
| `components.css`      | Component primitives (`.nav`, `.hero`, `.module-card`, …)        |
| `style.css`           | Thin shim that `@import`s tokens + components                    |
| `main.js`             | Loader — wires the three modules below                           |
| `starfield.js`        | `initStarfield({ canvasId, density })`                           |
| `scroll-trigger.js`   | `initScrollTrigger({ selector, ... })` — writes `--scroll`       |
| `typewriter.js`       | `typeWriter(elId, text, { speed, onDone })`                      |
| `DESIGN_SYSTEM.md`    | **Authoritative** design-system reference                        |
| `assets/qrw.svg`      | Full digithings logo — self-generated QR code (see below)        |
| `assets/favicon.svg`  | SVG favicon (primary)                                            |
| `assets/favicon.ico`  | 16×16 + 32×32 ICO fallback                                       |
| `assets/og.png`       | 1200×630 Open Graph preview image                                |
| `CNAME`               | GitHub Pages custom domain                                       |
| `digiquant/`          | Sibling subdomain scaffold for `digiquant.io` (see its README)   |

## Design system

See [`DESIGN_SYSTEM.md`](./DESIGN_SYSTEM.md) for the full reference: base
palette, per-module accent colors, type / spacing / radius tokens, the
component primitive list with HTML usage examples, the starfield and
scroll-trigger APIs, and an adoption guide for `digichat/` and the
forthcoming `digiquant.io` surface.

The tokens in `tokens.css` mirror the dark-mode values in
`digichat/src/app/globals.css`, keeping the two surfaces visually coherent.

## Logo QR code

`assets/qrw.svg` encodes `https://digithings.ai` with ECC level H (30%
damage tolerance), circular dot modules, white fill, transparent
background. It is **generated** from `scripts/generate-qr.py` and checked
in so the site works without running the generator.

To regenerate:

```bash
pip install "qrcode==8.0"
make qr-logo
# → writes website/assets/qrw.svg
```

The generator script lives at `scripts/generate-qr.py` with a pinned
`qrcode==8.0` dependency for reproducibility.

## Local preview

```bash
cd website
python3 -m http.server 8765
# open http://localhost:8765
```

## Deployment

`digithings.ai` is served via GitHub Pages pointing at this directory.
`CNAME` contains the custom domain. The `static.yml` workflow deploys on
push to `develop` / `main`.
