# digichat single-route unification — investigation, spec & implementation plan

Status: plan only, no code changed. Owner decision: one real route with everything,
shared host component, unified configurations, theme selectable via command line
(env/CLI flag + URL override). Route/host unification scoped AFTER PR #4636.

Evidence base: 3 host-chain recon agents (product `/`, `/baseline`, `/embed`) + 4
single-route recon agents (layouts/metadata, middleware+headers+CSP, external URL
contracts, embed server mechanics). Prior work: PR #4636 (skins/registry/moves into
`packages/ui`, Option-B inversion, per-skin lazy).

## 1. What "single route" means (and doesn't)

- ONE real route: `/`, served by the Container (self-host behavior unchanged).
  Modes via `?mode=app|embed|catalog` (default `app`) alongside the existing params
  (`?skin=`, `?theme=`, `?token=`, `?host=`, `?welcome=`, `?accent=`, …).
- One shared `<DigiChatHost>` component: the converged provider stack, parameterized
  by mode (not three shells).
- One unified config loader: deploy YAML/env + tenant verify + URL overrides feed a
  single client-config projection.
- Theme CLI: `DIGICHAT_CHROME_SKIN` env (exists today) becomes the default theme,
  `?skin=` / `?theme=` override it on ALL modes (today only baseline honors them).
- NOT merged: API routes (`/api/*` incl. tenant-config, baseline-chat), the BFF/auth
  boundary, Phase-2 DB-backed tenants. Those are separate scopes.

## 2. Hard constraints the single route must absorb (from recon)

| # | Constraint (today) | Single-route preservation |
|---|---|---|
| 1 | `/embed` framing: tenant origins admitted via runtime `proxy.ts` allowlist; app routes `frame-ancestors 'none'` + `X-Frame-Options: DENY` | `proxy.ts` matcher extended to `/` with mode detection (`?mode=embed` or `?token=`/`?host=` present → embed header set; else app set). `next.config.ts` sources reworked (path-based split no longer sufficient). |
| 2 | Embed per-tenant no-store (`force-dynamic` + no-cache; one tenant's theme must not leak to another) | Single route is `force-dynamic` ALWAYS (all three routes need it today: embed, baseline, and `/` via `auth()`). Mild cost: `/` loses static-cacheability it barely had. |
| 3 | Embed server paint seed (token/host/referer triple-source verify, `paintTheme = urlTheme ?? tenant.theme`, URL UI overrides, per-skin canvas, `themePinScript`, `embedWide` script, `data-skin-canvas`) | All 12 embed mechanics move verbatim into an embed-mode branch of the single page (server-only; non-embed modes must not call the tenant resolve). |
| 4 | Gate-form early return (PaywallCard, NO providers) | Conditional early return in embed mode (unchanged logic, new location). |
| 5 | `GET /api/embed/tenant-config` no-store + live re-assert | Untouched (API route, not merged). Single route must not apply no-store globally. |
| 6 | Baseline dev-only (`production → notFound()`) + catalog honesty (no product providers/chrome) | `?mode=catalog` keeps the prod guard; honesty enforced at PROVIDER level (minimal stack) rather than CSS level (see §4). |
| 7 | `/` auth/session/memory variants + `redirect("/embed")` matrix (embed-mode deploys, anonymous session) | Matrix rewritten against modes: embed-mode deploy default → `mode=embed`; anonymous+session-auth → gate behavior, not a cross-route redirect (self-redirect would loop). |
| 8 | Robots: embed + baseline `noindex`; `/` indexable | `generateMetadata({ searchParams })` returns per-mode robots. |
| 9 | `/embed` is a LIVE external contract (tenant iframes, `widget.js` third-party snippet, INSTALL/ARCHITECTURE/ADR-0018 docs, edge `wrangler.toml` + `paths.ts` routing `/embed*` → Container, 6+ tests) | Back-compat (§5): edge REWRITE `/embed*` → `/?mode=embed` (zero client change; query preserved) + thin in-app redirect shim for non-edge contexts; `widget.js` snippet updated; docs + tests updated. |
| 10 | Edge ownership split: `/` is Pages-owned (NOT proxied), `/embed*` → Container | THE structural fork (see §5): canonical route lives in the Container; edge `paths.ts` + `wrangler.toml` change + redeploy. Self-host needs nothing (one container already serves all paths). |
| 11 | `/baseline` has NO external contract (dev docs only) | In-app redirect `/baseline` → `/?mode=catalog` (dev guard preserved); doc updates only. |

## 3. Target architecture

```
/  (single real route, force-dynamic)
├── ?mode=app (default): today's / — auth/session/memory variants, full provider
│   stack, indexable metadata, app header set
├── ?mode=embed: today's /embed — tenant verify + paint seed, persistence=none,
│   compact, gate-form branch, noindex, embed header set, tenant slots
└── ?mode=catalog (dev only): today's /baseline — ?skin=/?theme= catalog,
    minimal provider stack, noindex, app header set
+DigiChatHost (shared shell: runtime → prefs → chrome → skin-runtime → ThreadSkinView)
+unified loader (deploy YAML/env → tenant overlay → URL overrides → one projection)
+compat shims: /embed → /?mode=embed, /baseline → /?mode=catalog (thin redirects)
```

## 4. Stylesheet decision (top implementation risk)

Today `(digichat)` loads `globals.css` (bridge + product shell CSS) and `(baseline)`
loads `baseline.css` (bridge only, no product-chrome/chat-core/launcher). One route =
one layout = one entry stylesheet. Decision: single entry = today's `globals.css`
content; catalog honesty enforced at the PROVIDER level (minimal stack mounts no
product chrome), not the CSS level.

- Why acceptable: `product-chrome.css` body rules key off `data-stock-product`
  (never rendered in catalog mode); the skin grammar (`chat-aui.css` +
  `chat-digichat.css`) loads identically in both sheets today.
- Risk (bounded, must be gated): `chat-core` / `chat-widgets` / `launcher` rules
  could match catalog DOM that never saw them before. Gate: per-skin visual diff
  (`/?mode=catalog&skin=X` vs today's `/baseline?skin=X`, all 12, light+dark)
  before landing. Rollback criterion: any unexplained pixel delta → split the
  entry (mode-scoped `<link>` via a client boundary) instead of forcing one sheet.

## 5. Back-compat & deployments

- Prod edge (`digithings.ai`): `paths.ts` rewrites `/embed*` → Container
  `/?mode=embed` preserving query (tenant iframes, `widget.js`, `/chat` pages keep
  working with zero client change); `wrangler.toml` + redeploy. `/` stays
  Pages-owned — the unified route is consumed via the rewrite, not by moving `/`.
- Self-host / direct: thin in-app redirect routes `/embed` → `/?mode=embed` and
  `/baseline` → `/?mode=catalog` (~5 lines each; baseline keeps the dev guard).
- `widget.js` snippet + INSTALL/ARCHITECTURE/ADR-0018 updated to the canonical
  URLs (redirects keep old URLs working regardless).
- Tests to update: `apps/digichat-cloudflare/src/paths.test.ts`,
  `apps/digichat/src/proxy.test.ts`, `embed-popup-config.test.ts`,
  `chat-route-context.test.ts`, dashboard `digichat-popup` tests ×2,
  `ChatEmbedShell.contract.test.ts` (URL-shape assertions move to `?mode=` form).

## 6. Theme via command line (owner requirement)

- Default theme: `DIGICHAT_CHROME_SKIN` env (exists; deploy YAML `chrome.skin`,
  per-host overrides, compose examples — all keep working, now as the default
  `mode`-independent theme).
- Override: `?skin=<id>&theme=<light|dark>` honored on ALL modes (extend today's
  baseline-only params to app + embed paint seed, which already takes `?theme=`).
- Launching "a different theme" = `DIGICHAT_CHROME_SKIN=perplexity docker …` or
  appending `?skin=perplexity` — no redeploy, no code change.

## 7. Implementation steps (each verifiable, structural only, no visual change)

1. Shared `<DigiChatHost>` in the app (converged provider stack parameterized by
   mode; no route deleted yet; product + embed render through it; suites green).
2. Unified config loader (single projection fed by deploy/tenant/URL; the three
   pages call it; delete the per-route loader forks; suites green).
3. Single route `/` with `?mode=` + per-mode metadata/robots + `force-dynamic`;
   catalog mode keeps prod guard; embed mode keeps paint seed + gate branch.
   Per-skin visual diff gate (§4) before proceeding.
4. `proxy.ts` mode-aware headers + `next.config.ts` source rework; verify framing
   (tenant iframe allowlist) + DENY elsewhere + no-store scoping.
5. Compat shims (`/embed`, `/baseline` redirects) + edge `paths.ts`/`wrangler`
   rewrite + `widget.js`/docs/tests updates.
6. Delete the old route dirs; full suites + lint + build; smoke all modes +
   tenant iframe flow; commit; PR into `module/digichat`.

## 8. Risks & non-goals

- Risks: stylesheet delta on catalog skins (gated by §4 visual diff); edge
  rewrite misconfiguration breaking tenant iframes (staged rollout: ship app +
  redirects first, flip edge rewrite after smoke); query-based mode detection in
  `proxy.ts` (must fail closed to app headers).
- Non-goals: BFF/auth changes, API route changes, Phase-2 DB-backed tenants,
  unifying all apps' CSS, touching `widget.js` behavior beyond URLs.
