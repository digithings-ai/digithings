# Epic #7 — Consolidate frontends under digithings.ai

Decomposition of [Epic #7](https://github.com/digithings-ai/digithings/issues/7) (Phase 3a) into concrete child tasks.

## Recap

[ADR-0002](../adr/0002-domain-unification.md) commits to a two-domain arrangement:

- `digithings.ai` — static landing (`website/`, GitHub Pages, canvas starfield).
- `chat.digithings.ai` — production DigiChat (`digichat/`, Next.js).
- Atlas and the commercial product surface move to `digiquant.io` (tracked separately, Phase 3c).

Phase 3a is the execution pass: verify routing, add the CTA, retire duplicates, tidy nav. Phase 3b (BYOK) and 3c (`digiquant.io`) are out of scope here.

## Shipped

- [ADR-0002](../adr/0002-domain-unification.md) — two-domain decision recorded.
- [PR #58](https://github.com/digithings-ai/digithings/pull/58) — DNS + Pages routing verified and documented in `docs/DEPLOYMENT.md`; `website/CNAME` confirmed; asset-copy step audited; nav link to `chat.digithings.ai` confirmed in `website/index.html`.
- Vite DigiChat POC previously removed (per ADR-0002 context).

## Remaining sub-tasks

- [ ] **"Chat with DigiThings" CTA on `website/`** — prominent hero button linking to `https://chat.digithings.ai`. Today only a small nav link exists; ADR-0002 calls for a conversion-oriented CTA.
- [ ] **Audit `website/` copy for Atlas-specific references** — remove or redirect any mentions that belong on `digiquant.io`; keep the landing focused on the open-core ecosystem.
- [ ] **301 redirects for legacy URLs** — enumerate any previously-linked paths (old `/chat`, Vite-POC URLs, Atlas teasers) and document the redirect plan for GitHub Pages or a lightweight redirect layer.
- [ ] **Shared header/footer story** — decide between a small shared partial (build-time include for `website/` + a matching React component in `digichat/`) or deliberate duplication with a style guide. Capture the decision in `website/README.md`.
- [ ] **Canvas starfield polish** — reduce CPU on idle tabs (pause on `visibilitychange`), confirm Safari fallback (`#bg-base` solid) still renders, and verify mobile frame-rate.
- [ ] **Analytics unification** — pick one property (e.g. Plausible) used by both `digithings.ai` and `chat.digithings.ai` so prospect-to-chat funnel is measurable; document the env var / snippet locations.
- [ ] **Deployment smoke-test checklist** — one page in `docs/DEPLOYMENT.md` enumerating post-deploy curl/browser checks for both surfaces (TLS, CNAME, asset 200s, nav link health).

Each item becomes its own `agent-task` issue on [Project #1](https://github.com/orgs/digithings-ai/projects/1) and links back to Epic #7.
