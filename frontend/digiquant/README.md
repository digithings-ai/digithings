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

## Deployment — follow-up (out of scope for this PR)

This scaffold does **not** yet ship its own deploy. The existing
`static.yml` workflow deploys `frontend/digithings/` to `digithings.ai`.
`digiquant.io` needs a parallel Pages project (or a sibling workflow)
pointing at `frontend/digiquant/`. Tracked under epic #9.

### DNS

GitHub Pages custom domain setup:

1. In the repo settings, create a second Pages site that serves
   `frontend/digiquant/` (separate from the one serving
   `frontend/digithings/`).
2. Set the custom domain to `digiquant.io`. `CNAME` in this directory
   carries that value.
3. At the registrar, add a DNS `CNAME` record for `digiquant.io` pointing
   at `digithings-ai.github.io`. For apex-domain setups, use four `A`
   records per the [GitHub Pages docs](https://docs.github.com/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).
4. Enable HTTPS in Pages settings once DNS has propagated.

### Related

- Epic [#9](https://github.com/digithings-ai/digithings/issues/9) — stand up digiquant.io.
- Epic [#235](https://github.com/digithings-ai/digithings/issues/235) — shared design system.
- Epic [#254](https://github.com/digithings-ai/digithings/issues/254) — frontend umbrella reorg.
- Issue [#183](https://github.com/digithings-ai/digithings/issues/183) — wiring the investment profiling entry flow into the embedded DigiChat slot.
- ADR: [`../../docs/adr/0002-domain-unification.md`](../../docs/adr/0002-domain-unification.md) — two-domain plan.
- ADR: [`../../docs/adr/0009-frontend-umbrella.md`](../../docs/adr/0009-frontend-umbrella.md) — umbrella layout.
