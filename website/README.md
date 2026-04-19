# website/

Static landing page for [digithings.ai](https://digithings.ai) — vanilla HTML/CSS/JS with a canvas starfield background. Deployed via GitHub Pages from this directory.

## Files

| File | Purpose |
|---|---|
| `index.html` | Landing page markup |
| `style.css` | Styles |
| `main.js` | Canvas starfield + scroll animations |
| `assets/qrw.svg` | Logo QR code — self-generated (see below) |
| `CNAME` | GitHub Pages custom domain |

## Logo QR code

`assets/qrw.svg` encodes `https://digithings.ai` with ECC level H (30% damage tolerance), circular dot modules, white fill, transparent background. It is **generated** from `scripts/generate-qr.py` and checked in so the site works without running the generator.

To regenerate:

```bash
pip install "qrcode==8.0"
make qr-logo
# → writes website/assets/qrw.svg
```

The generator script lives at `scripts/generate-qr.py` with a pinned `qrcode==8.0` dependency for reproducibility.

## Deployment

`digithings.ai` is served via GitHub Pages pointing at this directory. `CNAME` contains the custom domain. The `static.yml` workflow deploys on push to `develop`/`main`.
