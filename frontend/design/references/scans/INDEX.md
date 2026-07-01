# Deep design scans — index

**Audit date:** 2026-06-29  
**Sites:** [graphite.com](graphite-full.md) · [cursor.com](cursor-full.md) · [x.ai](xai-full.md)

This folder holds **exhaustive** frontend extractions — page maps, components, motion,
mobile nav, copy patterns, and token inference. Summary scans live one level up;
this folder is the deep layer.

| Document | Contents |
|----------|----------|
| [graphite-full.md](graphite-full.md) | Full site map, pages, scroll-pinned features, dark zinc system |
| [cursor-full.md](cursor-full.md) | Bento layout, light utilitarian, pricing/enterprise/changelog |
| [xai-full.md](xai-full.md) | Brutalist mono, API/capability cards, news/pricing |
| [components-catalog.md](components-catalog.md) | Cross-site component comparison + DigiThings primitive mapping |
| [mobile-nav-interactions.md](mobile-nav-interactions.md) | Playwright-verified mobile nav, menus, touch targets |
| [copy-patterns.md](copy-patterns.md) | Headlines, CTAs, friction reducers, section voice |

**Synthesis:** [`../EVOLUTION.md`](../EVOLUTION.md)  
**Methodology:** Live page fetch + Playwright a11y snapshots (390×844) + public CSS analyses (design-bites, getdesign.md, shadcn xAI kit). x.ai Playwright blocked by Cloudflare — x.ai sections rely on fetch + published token extractions.

**Re-audit when:** Any reference site ships a major homepage redesign.
