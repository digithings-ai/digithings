# frontend/digiquant/

Static scaffold for [digiquant.io](https://digiquant.io) — the financial-AI
product hub of the DigiThings stack. Shares the design system with the
sibling [`frontend/digithings/`](../digithings/README.md) via the
[`@digithings/design`](../design/README.md) workspace package:
`tokens.css`, `components.css`, `quant-native/`, and `scroll-trigger.js`
are loaded from `../design/` so there is a single source of truth.

## Files

| File          | Purpose                                                        |
| ------------- | -------------------------------------------------------------- |
| `index.html`  | DigiQuant landing — hero, acts, deployment tabs, get-started   |
| `atlas.html`  | Atlas marketing page — cycles, ten-phase pipeline, data sources |
| `atlas-main.js` | Atlas page module — counters + draw-ins                      |
| `main.js`     | Landing module — diagram, counters, Act V tabs                 |
| `style.css`   | Page styles on top of the shared design tokens                 |
| `_headers`    | Cloudflare Pages security headers (root-level, see #674)       |
| `CNAME`       | Legacy GitHub Pages domain marker (`digiquant.io`)             |

All charts and figures on these pages are illustrative and labeled as such
in the markup; the live data surface is the Olympus dashboard at
[`/olympus/`](https://digiquant.io/olympus/).

## Design system

Page CSS lives in `style.css`; shared styles come from
`../design/tokens.css` and `../design/components.css`; the
full reference is [`../design/README.md`](../design/README.md).

Accent scoping follows the documented pattern:

- Page-level surfaces use `.accent-digiquant` for the DigiQuant emerald.
- Product cards scope to their own child accent: `.accent-atlas`,
  `.accent-hermes`, `.accent-kairos`.

## Local preview

```bash
cd frontend
python3 -m http.server 8765
# open http://localhost:8765/digiquant/
```

The dev server must run from `frontend/` (not `frontend/digiquant/`)
so the `../design/` imports resolve.

## Deployment

Build locally with [`scripts/build-digiquant.sh`](../../scripts/build-digiquant.sh)
(mirrors the Cloudflare Pages build). Production deploy is **Cloudflare Pages**
(project `digiquant-io`), not a monorepo GitHub Actions workflow — see
[ADR-0012](../../docs/adr/0012-digiquant-io-split-repo.md).

GitHub Pages supports one custom domain per repo and the monorepo's slot
is taken by `digithings.ai`. `digiquant.io` may also be published via
[`digithings-ai/digiquant.io`](https://github.com/digithings-ai/digiquant.io)
when using the split-repo sync pattern described in ADR-0012.

**Rule:** treat the publish repo as deploy-only when used. Never edit
files in `digithings-ai/digiquant.io` directly — automated deploys rewrite
its `main` branch.

### Required monorepo secret

`DIGIQUANT_IO_DEPLOY_TOKEN` — fine-grained GitHub PAT scoped to the
publish repo only, with **Contents: Read and write**. Generate it at
[github.com/settings/tokens?type=beta](https://github.com/settings/personal-access-tokens/new),
then set it here:

```bash
gh secret set DIGIQUANT_IO_DEPLOY_TOKEN  # paste the PAT
```

### DNS (at registrar)

Apex `digiquant.io` → GitHub Pages A/AAAA records:

| Type  | Host | Value                  |
| ----- | ---- | ---------------------- |
| A     | @    | 185.199.108.153        |
| A     | @    | 185.199.109.153        |
| A     | @    | 185.199.110.153        |
| A     | @    | 185.199.111.153        |
| AAAA  | @    | 2606:50c0:8000::153    |
| AAAA  | @    | 2606:50c0:8001::153    |
| AAAA  | @    | 2606:50c0:8002::153    |
| AAAA  | @    | 2606:50c0:8003::153    |
| CNAME | www  | digithings-ai.github.io |

Propagation + GitHub cert issuance typically takes 10–30 minutes combined.
Enable HTTPS in the publish repo's Pages settings once the cert issues.

### Publish-repo Pages config (one-time)

In `digithings-ai/digiquant.io` → Settings → Pages:

- Source: **Deploy from a branch**
- Branch: `main` / `/ (root)`
- Custom domain: `digiquant.io`
- Enforce HTTPS: enabled (toggle after cert issues)

### Related

- Epic [#9](https://github.com/digithings-ai/digithings/issues/9) — stand up digiquant.io.
- Epic [#235](https://github.com/digithings-ai/digithings/issues/235) — shared design system.
- Epic [#254](https://github.com/digithings-ai/digithings/issues/254) — frontend umbrella reorg.
- Issue [#183](https://github.com/digithings-ai/digithings/issues/183) — wiring the investment profiling entry flow into the embedded DigiChat slot.
- ADR: [`../../docs/adr/0002-domain-unification.md`](../../docs/adr/0002-domain-unification.md) — two-domain plan.
- ADR: [`../../docs/adr/0009-frontend-umbrella.md`](../../docs/adr/0009-frontend-umbrella.md) — umbrella layout.
