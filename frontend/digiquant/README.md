# frontend/digiquant/

Static scaffold for [digiquant.io](https://digiquant.io) — the financial-AI
product hub of the DigiThings stack. Shares the design system with the
sibling [`frontend/digithings/`](../digithings/README.md) via the
[`@digithings/design`](../design/README.md) workspace package:
`tokens.css`, `components.css`, `starfield.js`, and `scroll-trigger.js`
are loaded from `../design/` so there is a single source of truth.

## Files

| File          | Purpose                                                |
| ------------- | ------------------------------------------------------ |
| `index.html`  | DigiQuant landing — hero, product family, chat embed   |
| `atlas.html`  | Stub reserving `/atlas` for Phase 4                    |
| `main.js`     | Composes `initStarfield` + `initScrollTrigger`         |
| `CNAME`       | GitHub Pages custom domain (`digiquant.io`)            |

## Design system

No CSS or JS lives in this directory beyond `main.js`. Styles come from
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

Deployed via [`.github/workflows/deploy-digiquant.yml`](../../.github/workflows/deploy-digiquant.yml).

GitHub Pages supports one custom domain per repo and the monorepo's slot
is taken by `digithings.ai`. `digiquant.io` is therefore served from a
separate **publish repo**, [`digithings-ai/digiquant.io`](https://github.com/digithings-ai/digiquant.io).
The workflow above runs on every push to `develop`/`main` that touches
`frontend/digiquant/**` or `frontend/design/**`, builds a `dist/` mirroring
the Pages artifact shape, and force-pushes it to the publish repo's
`main` branch.

**Rule:** the publish repo is write-only from this workflow. Never edit
files in `digithings-ai/digiquant.io` directly — every deploy rewrites
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
