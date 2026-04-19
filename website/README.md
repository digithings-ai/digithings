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

## Design decisions

### Header/Footer: deliberate duplication, not shared partials

**Status:** accepted
**Date:** 2026-04-18

**Decision:** `website/` and `digichat/` each maintain their own nav and footer markup. There is no shared include mechanism, build-time template, or runtime fetch for these elements.

**Rationale:** `website/` is intentionally zero-build — no bundler, no preprocessor. Introducing a build step solely to share a nav partial would add tooling complexity that outweighs the benefit of DRY HTML for two small surfaces. `digichat/` is Next.js and already controls its layout via its own `app/layout.tsx`; it cannot consume a vanilla HTML partial anyway. The two surfaces align visually through shared CSS design tokens (see below), which is sufficient for brand coherence without coupling the deploy pipelines.

**CSS token alignment:** Both surfaces should use a common set of design token categories documented here as the source of truth. When `digichat/` extends or changes brand values it must update this list:

| Token category | Example properties |
|---|---|
| Brand colours | primary accent, background base, text primary/secondary |
| Typography | font family (`Inter`), weights (400/500/600), base size scale |
| Spacing scale | rem-based spacing steps used for padding/margin/gap |
| Border radius | card corners, button radius |

Agents extending either surface should check this table before introducing new values; deviations require a conscious decision, not a default.

**When to revisit:** if a third surface (e.g., `docs.digithings.ai`) emerges, evaluate a lightweight design-token package rather than more duplication.

### Analytics: Plausible, deferred to later PR

**Status:** deferred — pending Plausible account setup
**Date:** 2026-04-18

**Decision:** Plausible Analytics is the chosen analytics provider for both `digithings.ai` and `chat.digithings.ai`.

**Rationale:** Plausible is privacy-first, cookie-free, and GDPR-compliant by default. The same Plausible script works on a static site and on Next.js without custom server instrumentation. It avoids the complexity of consent banners required by cookie-based alternatives (e.g., Google Analytics).

**Implementation plan (not yet merged):**

- `website/index.html` — add the Plausible script tag in `<head>`, e.g.:
  ```html
  <script defer data-domain="digithings.ai"
          src="https://plausible.io/js/script.js"></script>
  ```
- `digichat/` — add the equivalent via the `next-plausible` package (or a `<Script>` tag in the root layout at `app/layout.tsx`), gated on the env var:
  ```
  NEXT_PUBLIC_PLAUSIBLE_DOMAIN=digithings.ai
  ```
  When the env var is absent (local dev, preview), the script is not injected.

**Prerequisite:** a Plausible account and domain must be registered before these snippets are activated. Agents must not merge the analytics PR until the Plausible account is confirmed by the maintainer; doing so would load a script for an unclaimed domain.
