# frontend/digithings/

Static landing page for [digithings.ai](https://digithings.ai) — vanilla
HTML, CSS, and ES modules, with a canvas starfield background. Deployed
via **Cloudflare Pages** (see repo `scripts/build-digithings.sh` and
`.github/workflows/static.yml` — retired; dispatch-only guard).

## Files

| File                  | Purpose                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `index.html`          | Landing page markup                                              |
| `style.css`           | Page-local overrides (tokens/components come from design) |
| `main.js`             | Loader — wires starfield, scroll-trigger, typewriter             |
| `assets/qrw.svg`      | Full digithings logo — self-generated QR code (see below)        |
| `CNAME`               | Custom domain hint for Cloudflare Pages                          |

Shared design tokens, component primitives, starfield / scroll-trigger /
typewriter modules, favicons, and the OG preview image all live in the
[`@digithings/design`](../design/README.md) workspace package
and are referenced via `../design/…` relative paths.

## Design system

See [`../design/README.md`](../design/README.md) for the full
reference: base palette, per-module accent colors, type / spacing / radius
tokens, the component primitive list with HTML usage examples, and the
starfield and scroll-trigger APIs.

The tokens in `design/tokens.css` mirror the dark-mode values in
`frontend/digichat/src/app/globals.css`, keeping the two surfaces visually
coherent.

## Logo QR code

`assets/qrw.svg` encodes `https://digithings.ai` with ECC level H (30%
damage tolerance), circular dot modules, white fill, transparent
background. It is **generated** from `scripts/generate-qr.py` and checked
in so the site works without running the generator.

To regenerate:

```bash
pip install "qrcode==8.0"
make qr-logo
# → writes frontend/digithings/assets/qrw.svg
```

The generator script lives at `scripts/generate-qr.py` with a pinned
`qrcode==8.0` dependency for reproducibility.

## Local preview

Because the site references the sibling `../design/` folder, serve
from `frontend/` (not `frontend/digithings/`):

```bash
cd frontend
python3 -m http.server 8765
# open http://localhost:8765/digithings/
```

## Deployment

`digithings.ai` is served via **Cloudflare Pages** (not GitHub Pages).
Build with `scripts/build-digithings.sh`; the legacy `static.yml` workflow is
retired (workflow_dispatch guard only). See [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md).
