# Phase 4 — Full rename of the public `/embed` surface to `/chat` (Cloudflare v2 refactor)

- **Status:** spec only — no code changes made by this plan. Implementer executes tasks in order.
- **Scope:** repo `/Users/chrisstefan/Code/digithings` ONLY. Never touch sibling repos (`zeus`, `apollo`, DataTapStream third-party code).
- **Decision (user):** full rename of the public surface (route, API path, iframe URLs, tokens, file prefixes) over internals-only rename.
- **Predecessor phases:** Phase 3 produced `frontend/digichat-cloudflare/` (`src/paths.ts`, `src/index.ts`, `wrangler.toml`). No merged Worker router was found in-repo (`frontend/digithings-stack-cloudflare/src/` contains zero `embed` references — verified by rg); all Worker specs below target the `digichat-cloudflare` router. If Phase 3 merged the routers elsewhere, the implementer must re-point T6 at the merged file and keep the same route set.
- **Compat policy:** 308 `/embed` → `/chat` (path-preserving) + dual postMessage-listen readiness for one release. Cached `widget.js` copies and third-party iframes (incl. DataTapStream) break silently otherwise.
- **Ship order (mandatory):** (1) land new `/chat` routes dual-serving alongside `/embed`; (2) repoint dashboard + marketing shells FIRST; (3) compat window (one release, 308s active); (4) remove old paths.

## Global Constraints

1. **TDD:** every task adds/updates the failing test first (`npm run test` in `frontend/digichat/`, dashboard, digithings-web as touched), then the change. `npm run lint` zero errors before and after.
2. **Shells-first ship order:** dashboard (`frontend/dashboard/lib/digichat-popup.ts`, `components/digichat-popup.tsx`) + marketing shells (`frontend/digithings-web/components/ChatEmbedShell.tsx`, `app/chat/page.tsx`, `app/chat/occ/page.tsx`) repoint to the new URLs before any old path is removed.
3. **Compat window mandatory:** one full release with 308 redirects + dual-accept tokens/paths (spec in §Compat shims). No flag-gated early removal.
4. **FROZEN — do not rename:** all `X-Embed-*` request headers (`X-Embed-Host`, `X-Embed-Token`, `X-Embed-Accent`, `X-Embed-Trial-Unlock`, `X-Embed-Chat-Token`, `X-Embed-Plan-Proof`, and the never-trusted `X-Embed-Plan-Tier` negative path); all `digichat:*` postMessage type strings (`digichat:ready`, `digichat:seed`, `digichat:theme`, `digichat:page-context`, `digichat:plan-tier`, `digichat:parent-error`); `data-digichat-private`, `data-host` / `data-token` (+ existing `data-embed-host` / `data-embed-token` aliases) snippet attributes — renaming any of these is a silent break for copy-pasted third-party snippets.
5. **Stay in-repo;** never edit `zeus/`, `apollo/`, or any DataTapStream code.
6. **Never touch `sleepAfter` / scaling:** `sleepAfter = "15m"` in `frontend/digichat-cloudflare/src/index.ts:19` and `max_instances = 5` in `frontend/digichat-cloudflare/wrangler.toml:39` are out of scope. Cost/scale tuning is a separate decision.
7. **BFF + auth rules (digichat AGENTS.md):** browser never holds digigraph JWT / `DIGIKEY_BFF_TOKEN`; every new API route calls `requireDigiChatAuth()` unless explicitly public; no `AUTH_SECRET` in client bundles.

## Canonical token mapping (normative for all tasks)

| Domain | Old | New | Compat read (one release) |
|---|---|---|---|
| Public route dir | `frontend/digichat/src/app/(digichat)/embed/` | `frontend/digichat/src/app/(digichat)/chat/` | 308 `/embed` → `/chat`, `/embed/:path*` → `/chat/:path*` |
| Tenant-config API | `/api/embed/tenant-config` | `/api/chat/tenant-config` | 308 `/api/embed/:path*` → `/api/chat/:path*` |
| `?layout=` value | `embed` | `compact` | accept `embed` → normalize to `compact` |
| `?layout=` value | `page` | `full` | accept `page` → normalize to `full` |
| Tenant registry `layout` | `"page" \| "embed"` | `"full" \| "compact"` | accept `"page"` → `full`, `"embed"` → `compact` |
| `chrome.mode` | `"app"` | `"full"` | accept `"app"` → `full` |
| `chrome.mode` | `"embed"` | `"compact"` | accept `"embed"` → `compact` |
| `chrome.mode` | `"modal"`, `"sidebar"` | unchanged | — |
| Anonymous tenant slug | `"embed"` / `"embed:anonymous"` | `"chat"` / `"chat:anonymous"` | internal only; rate-bucket reset acceptable |
| localStorage keys | `digichat_embed_turns:` / `digichat_embed_trial_unlocked:` / `digichat_embed_chat_token:` / `digichat_embed_conversation:` | `digichat_chat_turns:` / `digichat_chat_trial_unlocked:` / `digichat_chat_token:` / `digichat_chat_conversation:` | same-browser reset acceptable; NO dual-read (fresh start) |
| `data-chrome-mode` DOM value | `"embed"` | `"compact"` | — |
| FROZEN (see constraint 4) | `X-Embed-*`, `digichat:*`, `data-digichat-private`, `data-host`, `data-token` | unchanged | — |
| Codemod trap (NOT a rename) | `"embed"` tag entry in `DROP_TAGS` (`frontend/digichat/src/lib/page-context-sanitize.ts:109`, `frontend/digichat/public/widget.js:119`) | unchanged — that is the HTML `<embed>` element | exclude from every sed/codemod; assert in review |

## T0 — New `/chat` route dir (dual-serve) + root redirect

Files: `frontend/digichat/src/app/(digichat)/embed/{page.tsx,layout.tsx,embed-client.tsx,embed-slash.test.tsx}` → `frontend/digichat/src/app/(digichat)/chat/{page.tsx,layout.tsx,chat-client.tsx,chat-slash.test.tsx}`; `frontend/digichat/src/app/(digichat)/page.tsx`; `frontend/digichat/src/app/(digichat)/globals.css`.

Interfaces: `GET /chat?host=&token=&theme=&layout=&accent=&welcome=&placeholder=&suggestions=&wide=1`; default export `ChatPage` (was `EmbedPage`); `ChatLayout` (was `EmbedLayout`); default export `ChatClient` (was `EmbedClient`, prop `initialTenantCfg` unchanged).

- [ ] `git mv frontend/digichat/src/app/\(digichat\)/embed frontend/digichat/src/app/\(digichat\)/chat`, then `git mv` inside: `embed-client.tsx` → `chat-client.tsx`, `embed-slash.test.tsx` → `chat-slash.test.tsx` (keep `page.tsx`, `layout.tsx` names).
- [ ] `chat/page.tsx`: `import ChatClient from "./chat-client"` (was `import EmbedClient from "./embed-client"`); `export default async function ChatPage(` (was `EmbedPage`); update the doc comment `* /embed — server shell.` → `* /chat — server shell.`, `fetching /api/embed/tenant-config after mount` → `fetching /api/chat/tenant-config after mount`. Server logic (`resolveEmbedHostParamOrReferer`, `resolveEmbedClientConfigForPaint`, `parseEmbedThemeParam`, `themePinScript`, `force-dynamic`) unchanged.
- [ ] `chat/layout.tsx`: `export default function ChatLayout(` (was `EmbedLayout`); comment `/embed surface is unauthenticated` → `/chat surface is unauthenticated`; metadata `description: "Embedded digichat preview."` → `description: "digichat chat."`. Keep `dc-embed-shell` class name (CSS hook; renaming it is out of scope — record as follow-up, not this phase).
- [ ] `chat/chat-client.tsx`: default export rename `EmbedClient` → `ChatClient`, inner `EmbedPageInner` → `ChatPageInner`; `data-chrome-mode="embed"` (line ~1156) → `data-chrome-mode="compact"`; comments `via digichat:theme postMessage` unchanged (frozen names), `(embed/layout.tsx)` → `(chat/layout.tsx)`.
- [ ] `chat/chat-slash.test.tsx`: `join(__dirname, "embed-client.tsx")` → `join(__dirname, "chat-client.tsx")`; variable `embedClientSrc` → `chatClientSrc` (all 6 uses); describe `"embed stock chrome wiring"` → `"chat stock chrome wiring"`; inner `expect(...).toMatch` targets unchanged.
- [ ] Compat route (new file `frontend/digichat/src/app/(digichat)/embed/page.tsx`, replaces moved dir): `import { redirect } from "next/navigation"; export default function EmbedCompatPage() { redirect("/chat", "replace" as never); }` — implement as 308: preferred is `src/proxy.ts` rewrite (see T2) so query params are preserved (`redirect()` drops search params; iframe URLs always carry `?host=`). If proxy rewrite is used, do NOT keep an `/embed` route file (it would shadow the proxy). Decide in T2, do exactly one.
- [ ] `(digichat)/page.tsx` lines 29–31, 39, 52: `redirect("/embed")` → `redirect("/chat")` (3 sites); comment `redirect to /embed (anonymous iframe surface)` → `redirect to /chat (anonymous iframe surface)`.
- [ ] `globals.css` line 48: `@source "../../app/(digichat)/embed";` → `@source "../../app/(digichat)/chat";` (Tailwind v4 content detection — without this the renamed dir's classes go unstyled in production).
- [ ] Tests first: duplicate `proxy.test.ts` CSP cases for `/chat` URLs before changing matcher (T2); update `embed-slash` → `chat-slash` file assertions.

## T1 — `?layout=` values + tenant `layout` + `chrome.mode` token migration (dual-read)

Files: `frontend/digichat/src/lib/embed-tenants.ts` (lines ~104, ~335–336, ~383), `embed-client-config.ts` (lines ~46, ~75, ~87, ~112), `embed-ui-flags.ts` (lines ~43, ~49), `deploy-config/schema.ts` (line ~19, `ChromeSchema` default line ~125, `DeploymentSchema` default line ~275), `deploy-config/loader.ts` (lines ~72–73, ~165, ~315), `deploy-config/embed-bridge.ts` (line ~37), `deploy-config/client-projection.ts` (lines ~106–108), `deploy-config/*.test.ts`, `embed-ui-flags.test.ts`, `embed-tenants.test.ts`.

Interfaces: `layout?: "full" | "compact"` (tenant + client config + UI flags); `ChromeModeSchema = z.enum(["full", "compact", "modal", "sidebar"])`; loader/bridge map `full↔app-side`, `compact↔embed-side` exactly as today.

- [ ] `embed-tenants.ts`: type `layout?: "page" | "embed";` → `layout?: "full" | "compact";`; validation `if (v.layout !== undefined && v.layout !== "page" && v.layout !== "embed") { throw new Error(`${ctx}: layout must be "page" or "embed"`); }` → accept old with normalization: `"page"` → `"full"`, `"embed"` → `"compact"` (normalize at parse, store canonical); error string → `` `${ctx}: layout must be "full" or "compact"` ``; projection line `layout: v.layout === "page" || v.layout === "embed" ? v.layout : undefined,` → emit canonical (`"full"`/`"compact"`) after normalization.
- [ ] `embed-client-config.ts`: `layout?: "page" | "embed";` → `layout?: "full" | "compact";`; `layout: "embed",` (DEFAULT, line ~87) → `layout: "compact",`; `layout: cfg.layout ?? "embed",` (line ~112) → `layout: cfg.layout ?? "compact",`.
- [ ] `embed-ui-flags.ts`: `layout: "page" | "embed";` → `layout: "full" | "compact";`; `layout: cfg.layout === "page" ? "page" : "embed",` → `layout: cfg.layout === "full" ? "full" : "compact",`.
- [ ] `schema.ts`: `ChromeModeSchema = z.enum(["app", "embed", "modal", "sidebar"])` → `z.enum(["full", "compact", "modal", "sidebar"])` with `z.preprocess` (or `.catch` + normalize) mapping `"app"` → `"full"`, `"embed"` → `"compact"` during compat; `mode: ChromeModeSchema.default("embed")` → `.default("compact")`; `DeploymentSchema` chrome default `mode: "embed"` → `mode: "compact"`.
- [ ] `loader.ts` line ~72–73: `cfg.layout === "page" ? ("app" as const) : ("embed" as const)` → `cfg.layout === "full" ? ("full" as const) : ("compact" as const)`; line ~165: `layout: dep.chrome.mode === "app" || dep.chrome.mode === "sidebar" ? "page" : "embed",` → `layout: dep.chrome.mode === "full" || dep.chrome.mode === "sidebar" ? "full" : "compact",`; dev-default `mode: "embed"` (line ~315) → `mode: "compact"`.
- [ ] `embed-bridge.ts` line ~37: `mode: embed.layout === "page" ? "app" : "embed",` → `mode: embed.layout === "full" ? "full" : "compact",`.
- [ ] `client-projection.ts` lines ~106–108: `slug: "embed",` → `slug: "chat",`; `mode: "embed",` → `mode: "compact",`.
- [ ] `(digichat)/page.tsx` line 29: `(mode === "embed" || mode === "modal" || mode === "sidebar")` → `(mode === "compact" || mode === "modal" || mode === "sidebar")`; `skin-chrome.tsx:30` `mode: "embed",` → `mode: "compact",`.
- [ ] Iframe builders' `layout` param: `url.searchParams.set("layout", "embed")` → `url.searchParams.set("layout", "compact")` in `embed-popup-config.ts:114`, `public/widget.js:94`, `dashboard/lib/digichat-popup.ts:304`; `url.searchParams.set("layout", "page")` → `url.searchParams.set("layout", "full")` in `digithings-web/components/ChatEmbedShell.tsx:72` (see T4 for full builder edits).
- [ ] Tests: `embed-ui-flags.test.ts` (`layout: "page"`/`"embed"` → `"full"`/`"compact"`), `embed-tenants.test.ts:458` (`layout: "page"` → `layout: "full"`), `use-embed-tenant-config.test.ts:65` (`layout: "embed"` → `"compact"`), `api/embed/tenant-config/route.test.ts:54,118`, `deploy-config/*` mode assertions (`toBe("embed")` → `toBe("compact")`), `product-shell.test.tsx:64` (`toBe("embed")` → `toBe("compact")`). Add dual-read cases: old `"page"`/`"embed"`/`"app"` inputs normalize to new canonical.

## T2 — CSP + proxy matcher + next.config headers (dual-path during compat)

Files: `frontend/digichat/src/proxy.ts`, `frontend/digichat/next.config.ts`, `frontend/digichat/src/lib/security-headers-bake.ts` (constants only if renamed — recommend: keep `DIGICHAT_EMBED_BAKED_SECURITY_HEADERS` / `DIGICHAT_EMBED_FAIL_CLOSED_CSP` identifier names; they are build-internal, renaming adds churn with zero public effect), `frontend/digichat/src/proxy.test.ts`.

- [ ] `proxy.ts` matcher: `matcher: ["/embed", "/embed/:path*"],` → `matcher: ["/chat", "/chat/:path*", "/embed", "/embed/:path*"],` and inside `proxy()`: if `request.nextUrl.pathname === "/embed" || startsWith("/embed/")`, return `NextResponse.redirect(new URL(request.nextUrl.pathname.replace(/^\/embed/, "/chat") + request.nextUrl.search, request.url), 308)` BEFORE setting CSP headers. Doc comment: `/embed` CSP ownership → `/chat` + `/embed` (compat) ownership.
- [ ] `next.config.ts` headers: duplicate the two embed entries for the new path — `source: "/chat/:path*"` and `source: "/chat"` with `[...DIGICHAT_EMBED_BAKED_SECURITY_HEADERS]`; keep `/embed` + `/embed/:path*` entries through compat; negative-lookahead entry `source: "/((?!embed$|embed/).*)"` → `source: "/((?!embed$|embed/|chat$|chat/).*)"` (during compat), collapsing to `"/((?!chat$|chat/).*)"` at old-path removal.
- [ ] `proxy.test.ts`: existing two cases keep passing with `/embed` URLs; add mirrors with `/chat?host=client.example.com` and bare `/chat`; add 308 test: `new NextRequest("http://127.0.0.1:3000/embed?host=x")` → `res.status === 308` and `Location` ends `/chat?host=x`.
- [ ] Removal task (post-compat, separate PR): drop `/embed` matcher entries, the 308 branch, `/embed` header sources; collapse lookahead.

## T3 — Worker router + zone routes (spec against `frontend/digichat-cloudflare/`)

Files: `frontend/digichat-cloudflare/src/paths.ts`, `src/index.ts` (doc comment only — no logic/scale touch), `wrangler.toml`, `src/paths.test.ts`, `frontend/digichat-cloudflare/README.md`.

- [ ] `paths.ts`: `pathname === "/embed" ||` → `pathname === "/chat" ||`; `pathname.startsWith("/embed/") ||` → `pathname.startsWith("/chat/") ||`; `pathname.startsWith("/api/embed/") ||` → `pathname.startsWith("/api/chat/tenant-config") || pathname.startsWith("/api/chat/tenant-config/") ||` — note `/api/chat` + `/api/chat/` arms already cover the new tenant-config path, so the explicit arm is documentation-grade; keep it explicit for grep-ability. During compat ALSO keep the three old arms (`/embed`, `/embed/`, `/api/embed/`) so the 308s issued by Next (T2) are reachable through the Worker. Comment lines 1–5: `via /embed?host=` → `via /chat?host=`.
- [ ] `wrangler.toml`: add `pattern = "digithings.ai/chat*"` + `pattern = "digithings.ai/api/chat/tenant-config*"`? — **BLOCKED by P0 open question** (§Risks Q1: apex `/chat` collides with the Pages `/chat` shell on the same hostname). Recommended: do NOT add an apex `chat*` Worker route. Serve canonical `/chat` on `digichat.digithings.ai` (new `[[routes]]` with `zone_name`, host already in every CSP allowlist) + keep apex `/embed*` → 308 (T2) → absolute canonical URL. If owner instead chooses apex shadowing, Pages shells must relocate first — separate decision, separate plan.
- [ ] `index.ts`: doc comment `Proxies /embed, digichat APIs` → `Proxies /chat (/embed compat 308), digichat APIs`; `digithings.ai/chat → Pages iframe → /embed?host=` → `→ /chat?host=` (2 lines); 404 string `"digichat Worker: path not routed. Marketing /chat shells are on Pages."` unchanged.
- [ ] `paths.test.ts`: `/embed` cases → `/chat` equivalents (`shouldProxyToDigiChat("/chat") === true`, `("/chat/")`, `("/api/chat/tenant-config")`); keep old-path assertions `true` during compat with `// COMPAT one release` marker; **update the Pages-guard block**: `expect(shouldProxyToDigiChat("/chat")).toBe(false)` and `("/chat/occ") → false` MUST be revisited per Q1 decision — if apex Worker claims `/chat*`, these invert; if canonical moves to `digichat.digithings.ai`, they stay `false` and new assertions pin `shouldProxyToDigiChat` never matching bare Pages shells.
- [ ] `README.md`: table rows `digithings.ai/embed*` → canonical-host `/chat*` (+ compat row `/embed*` → 308); `curl …/embed?host=digithings.ai` → canonical `/chat?host=…`; `Worker **path** routes stay unchanged: /embed*` → list new set.

## T4 — Shells repoint FIRST (dashboard + marketing + widget.js)

Order within T4: land T0–T3 dual-serve first, then these edits, then release. Shells must never point at a path that 404s.

`frontend/dashboard/lib/digichat-popup.ts`:
- [ ] `buildDigichatEmbedSrc` (line ~302): `` new URL(`${cfg.origin.replace(/\/$/, '')}/embed`) `` → `` …/chat`) ``; `url.searchParams.set('layout', 'embed')` → `('layout', 'compact')`. Header comment (lines 1–13): `` iframes digichat `/embed?layout=embed` `` → `` iframes digichat `/chat?layout=compact` ``; `widget.js` (#3421) ref unchanged.
- [ ] Message constants `DIGICHAT_READY / PAGE_CONTEXT / THEME / PLAN_TIER` values unchanged (frozen). No dual-listen needed (names kept — record rationale in PR body).
- [ ] `frontend/dashboard/lib/digichat-popup.test.ts:219`: `expect(url.pathname).toBe('/embed')` → `.toBe('/chat')`; line ~221 `get('layout')).toBe('embed')` → `.toBe('compact')`; line ~85 origin fixture `'https://digichat.digithings.ai/embed'` → `'https://digichat.digithings.ai/chat'`.
- [ ] `frontend/dashboard/components/digichat-popup.test.tsx:137,139`: `toContain('https://digithings.ai/embed')` → `toContain('https://digithings.ai/chat')`; `toContain('layout=embed')` → `toContain('layout=compact')`.
- [ ] `frontend/dashboard/README.md:245`: `` iframes digichat `/embed?layout=embed` `` → `` `/chat?layout=compact` ``; line ~282 `X-Embed-Plan-Tier` text unchanged (frozen header name).

`frontend/digithings-web/components/ChatEmbedShell.tsx`:
- [ ] `embedSrc()` (lines ~68–78): `` new URL(`${base}/embed`) `` → `` new URL(`${base}/chat`) ``; `url.searchParams.set("layout", "page")` → `("layout", "full")`; `wide=1` unchanged. Doc comment line ~87 `iframes digichat /embed` → `iframes digichat /chat`.
- [ ] `READY`/`SEED`/`THEME`/`PARENT_ERROR` constants + `onMessage` single-type check (lines ~162–165) unchanged — names frozen, no dual-listen.
- [ ] `app/chat/page.tsx:16` comment `iframe to digichat /embed` → `iframe to digichat /chat`; `app/chat/occ/page.tsx` if mirrored (verify by read); `lib/security-headers.mjs:9` comment `(Worker routes /embed*)` → `(Worker routes /chat*, /embed* compat)`; lines ~101–102 `# /chat iframes digichat Node` — expand to name the guest path `/chat?host=…` explicitly.

`frontend/digichat/public/widget.js` (ships to third parties; cached copies persist — see acceptance C3):
- [ ] `buildSrc()` (lines ~91–99): `new URL(origin + "/embed")` → `new URL(origin + "/chat")`; `url.searchParams.set("layout", "embed")` → `("layout", "compact")`. Header usage comment line ~16 `iframes /embed?layout=embed` → `iframes /chat?layout=compact`.
- [ ] FROZEN inside widget.js: `READY`/`PAGE_CONTEXT` strings, `PRIVATE_ATTR = "data-digichat-private"`, `data-host`/`data-token` (+ `data-embed-host`/`data-embed-token`, `data-origin`/`data-digichat-origin`, `data-mode`/`data-launcher`) attribute reads, `DROP_TAGS` `embed: 1` (HTML tag), `fetchChrome` `/api/deploy/chrome` URL. `message` listener single `READY` check unchanged.
- [ ] `src/lib/embed-popup-config.ts` (server mirror of widget.js): line ~6 comment `` iframes `/embed?layout=embed` `` → `` `/chat?layout=compact` ``; `buildPopupEmbedSrc` line ~112 `` `${cfg.origin.replace(/\/$/, "")}/embed` `` → `` …/chat`) ``; line ~114 `set("layout", "embed")` → `set("layout", "compact")`; `embed-popup-config.test.ts:69,84` (`"/embed URL with layout=embed"`, `toBe("embed")`) → `/chat`, `"compact"`.

## T5 — Internal codemod: `lib/embed-*.ts` + `hooks/use-embed-*` + `components/stock/embed-*` → `chat-*`

Mechanical, one codemod commit + review. Exclusions: frozen header strings, frozen `digichat:*` strings, `DROP_TAGS`/`ALLOWED_TAGS` HTML-tag entries, `page-context-sanitize.ts` allowlist, `dc-embed-shell` CSS class (out of scope, see T0).

- [ ] `git mv` renames (30 lib files, keep `.test.*` beside each): `embed-accent-style.ts` → `chat-accent-style.ts`, `embed-chat-error.ts` → `chat-error.ts` (drop the redundant `chat-` stutter: `embed-chat-tenant` → `chat-tenant.ts`, `embed-chat-tenant.test.ts` likewise), `embed-client-config.ts` → `chat-client-config.ts`, `embed-first-party.ts` → `chat-first-party.ts`, `embed-gate-provider.ts` → `chat-gate-provider.ts`, `embed-gate.ts` → `chat-gate.ts`, `embed-ip-rate-limit.ts` → `chat-ip-rate-limit.ts`, `embed-legacy-gate.ts` → `chat-legacy-gate.ts`, `embed-page-context-messages.ts` → `chat-page-context-messages.ts`, `embed-parent-error-messages.ts` → `chat-parent-error-messages.ts`, `embed-popup-config.ts` → `chat-popup-config.ts`, `embed-seed-apply.ts` → `chat-seed-apply.ts`, `embed-seed-messages.ts` → `chat-seed-messages.ts`, `embed-send-gate.ts` → `chat-send-gate.ts`, `embed-suggestion-pools.ts` → `chat-suggestion-pools.ts`, `embed-tenants.ts` → `chat-tenants.ts`, `embed-theme-messages.ts` → `chat-theme-messages.ts`, `embed-trial-messages.ts` → `chat-trial-messages.ts`, `embed-turn-limits.ts` → `chat-turn-limits.ts`, `embed-turn-quota.ts` → `chat-turn-quota.ts`, `embed-ui-flags.ts` → `chat-ui-flags.ts`, `embed-ui-params.ts` → `chat-ui-params.ts`; hooks `use-embed-digi-chat.ts` → `use-chat-digi-chat.ts`, `use-embed-suggestions.ts` → `use-chat-suggestions.ts`, `use-embed-tenant-config.ts` → `use-chat-tenant-config.ts` (+ tests); stock components `embed-chat-prefs.tsx` → `chat-prefs.tsx`, `embed-composer-menu.tsx` → `chat-composer-menu.tsx`, `embed-mcp-catalog.ts` → `chat-mcp-catalog.ts`, `embed-mcp-flow.ts` → `chat-mcp-flow.ts`, `embed-mcp-oauth.ts` → `chat-mcp-oauth.ts`, `embed-mcp-pane.tsx` → `chat-mcp-pane.tsx`, `embed-models-pane.tsx` → `chat-models-pane.tsx`, `embed-provider-flow.ts` → `chat-provider-flow.ts`, `embed-settings-pane.tsx` → `chat-settings-pane.tsx` (+ tests).
- [ ] Import rewrite: `@/lib/embed-` → `@/lib/chat-`, `@/hooks/use-embed-` → `@/hooks/use-chat-`, `@/components/stock/embed-` → `@/components/stock/chat-` (rg-verify zero remaining; dashboard's `../../digichat/src/lib/page-context-sanitize` import is unaffected).
- [ ] Symbol renames (exported identifiers; update imports at call sites): `EmbedTenantConfig` → `ChatTenantConfig`, `EmbedTenantClientConfig` → `ChatTenantClientConfig`, `EmbedUiParams`/`readEmbedUiParams` → `ChatUiParams`/`readChatUiParams`, `resolveEmbedUiFlags` → `resolveChatUiFlags`, `resolveEmbedTenantByHost`/`parseEmbedTenants`/`getEmbedTenantRegistry`/`normalizeEmbedHost` → `resolveChatTenantByHost`/`parseChatTenants`/`getChatTenantRegistry`/`normalizeChatHost`, `resolveEmbedChatTenant`/`resolveVerifiedEmbedTenant`/`isEmbedChatRequest`/`isEmbedReferer`/`embedHostOf`/`embedConfigOf` → `resolveChatTenant`/`resolveVerifiedChatTenant`/`isChatRequest`/`isChatReferer`/`chatHostOf`/`chatConfigOf`, `isLegacyEmbedEnabled`/`LEGACY_EMBED_DISABLED_MESSAGE` → `isLegacyChatEnabled`/`LEGACY_CHAT_DISABLED_MESSAGE`, hooks `useEmbedTenantConfig`/`useEmbedDigiChat`/`useEmbedUiParams` → `useChatTenantConfig`/`useChatDigiChat`/`useChatUiParams`, `DEFAULT_EMBED_TENANT_CONFIG`/`toEmbedClientConfig` → `DEFAULT_CHAT_TENANT_CONFIG`/`toChatClientConfig`, `PopupWidgetConfig`/`readPopupWidgetConfigFromScript`/`buildPopupEmbedSrc` → `ChatPopupWidgetConfig`/`readChatPopupWidgetConfigFromScript`/`buildChatPopupSrc` (keep `PopupLauncherMode` name or rename to `ChatLauncherMode` — implementer picks, one name everywhere).
- [ ] String-literal discipline inside renamed files: header values `"X-Embed-Host"` etc. byte-identical; `"digichat:…"` type constants byte-identical; `isChatReferer` matches BOTH `/embed` and `/chat` path shapes during compat (see T7); comments mentioning `/embed` paths updated to `/chat` (or dual during compat).
- [ ] Storage keys (fresh start, no dual-read): `embed-gate.ts:10-11,124` → `"digichat_chat_turns:"`, `"digichat_chat_trial_unlocked:"`, `"digichat_chat_token:"` (name `CHAT_ACCESS_TOKEN_PREFIX` value change only); `use-embed-digi-chat.ts:76` → `"digichat_chat_conversation:"`; tests (`embed-gate.test.ts:64`, `use-embed-digi-chat.test.ts:561`) to new keys.
- [ ] Anonymous slug: `embed-chat-tenant.ts:159` `{ tenantSlug: "embed", ownerUserSub: "embed:anonymous", embedConfig: null }` → `{ tenantSlug: "chat", ownerUserSub: "chat:anonymous", embedConfig: null }` — field name `embedConfig` keeps its name in this phase (rename to `chatConfig` only with the T5 symbol pass if zero external readers; dashboard never sees this server-side shape — verify by rg before renaming the field). `chat-route-context.test.ts:88` `toEqual({ tenantSlug: "embed", … })` → `"chat"`.
- [ ] `components/chat-shell.tsx:600`: `signOut({ callbackUrl: p("/embed") })` → `signOut({ callbackUrl: p("/chat") })`.
- [ ] `app/api/baseline-chat/route.ts:38`: `headers.set("referer", "https://digithings.ai/embed?host=digithings.ai")` → `"https://digithings.ai/chat?host=digithings.ai"`.
- [ ] Codemod verification commands (must print zero): `rg "@/lib/embed-|@/hooks/use-embed-|components/stock/embed-" frontend/digichat/src`; `rg '"embed"' frontend/digichat/src --glob '!*DROP*'` triaged line-by-line; `rg 'embed' frontend/digichat/src/lib/page-context-sanitize.ts` must still show the tag allowlist intact.

## T6 — Env vars: one-release aliases (follow `DIGICHAT_EMBED_ENABLED` precedent)

Precedent (`embed-legacy-gate.ts:8-14`): canonical `DIGICHAT_LEGACY_EMBED_ENABLED`, deprecated alias `DIGICHAT_EMBED_ENABLED` honored for one release. Apply the same shape — new canonical read first, old fallback:

| Canonical (new) | Deprecated alias (one release) | Files |
|---|---|---|
| `DIGICHAT_CHAT_HOSTS` | `DIGICHAT_EMBED_HOSTS` | `security-headers.ts` (`embedHostsFromEnv`), `index.ts` envVars + `Env`, `wrangler.toml` `[vars]`, `proxy.test.ts`, `security-headers.test.ts` |
| `DIGICHAT_CHAT_TENANTS` | `DIGICHAT_EMBED_TENANTS` | `embed-tenants.ts:425` + all error strings `DIGICHAT_EMBED_TENANTS[…]` → `DIGICHAT_CHAT_TENANTS[…]` (lines ~177, ~402, ~405, ~413–414), `instrumentation.ts:3` comment, tests |
| `DIGICHAT_CHAT_TOKEN` | `DIGICHAT_EMBED_TOKEN` | `embed-chat-tenant.ts:48`, `chat-route-context.test.ts`, `embed-chat-tenant.test.ts` |
| `DIGICHAT_LEGACY_CHAT_ENABLED` | `DIGICHAT_LEGACY_EMBED_ENABLED` + `DIGICHAT_EMBED_ENABLED` (chain: new → middle → legacy) | `embed-legacy-gate.ts` |
| `DIGICHAT_CHAT_IP_RATE_LIMIT_MAX` / `…_WINDOW_MS` | `DIGICHAT_EMBED_IP_RATE_LIMIT_*` | `embed-ip-rate-limit.ts:21-22` (+ comment about import-time read) |
| `DIGICHAT_ALLOW_LOCAL_CHAT_PARENTS` | `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS` | `security-headers.ts:60-64` |
| `NEXT_PUBLIC_DIGICHAT_CHAT_ORIGIN/HOST/TOKEN/POPUP/POPUP_MODE/PAGE_CONTEXT` | `NEXT_PUBLIC_DIGICHAT_EMBED_*` | `dashboard/lib/digichat-popup.ts:128-137`, `digithings-web/lib/security-headers.mjs`, `app/chat/*` env reads |

- [ ] Helper per reader: `const v = process.env.NEW ?? process.env.OLD` (new wins). No warnings logged (client bundles must not leak which vars exist; server may `console.warn` once at boot for deprecated use — implementer picks server-only warn in `instrumentation.ts`).
- [ ] `wrangler.toml` `[vars]` + secrets comment block: list canonical names, note aliases honored one release. `index.ts` `envVars` + `Env` interface: same.
- [ ] Removal task (post-compat): delete alias arms + deprecated tests (`"allows when deprecated DIGICHAT_EMBED_ENABLED=1"` pattern replaced by canonical-only cases).

## T7 — Compat shims (all active during the one-release window)

1. **Path 308s (T2 proxy branch):** `/embed` → `/chat`, `/embed/:path*` → `/chat/:path*`, query string preserved, status 308 (method-preserving; iframe GETs unaffected, POSTs to old API paths — none exist publicly — also safe). `/api/embed/:path*` → `/api/chat/:path*` 308: implement as new route file `frontend/digichat/src/app/api/embed/[...path]/route.ts` returning `NextResponse.redirect(new URL(req.url.replace("/api/embed/", "/api/chat/")), 308)` (proxy matcher covers only page paths today; API compat needs its own route — do NOT widen proxy matcher to `/api/*` or the global CSP gets overwritten on every API response).
2. **New API route:** `git mv src/app/api/embed/tenant-config src/app/api/chat/tenant-config`; body unchanged except imports + doc comment (`/api/embed/tenant-config` → `/api/chat/tenant-config`).
3. **Referer dual-match** (`embed-chat-tenant.ts:36-43`): `return new URL(ref).pathname.includes("/embed")` → match either shape: `const p = new URL(ref).pathname; return p === "/chat" || p.startsWith("/chat/") || p === "/embed" || p.startsWith("/embed/");` (substring `includes("/chat")` is banned — it matches Pages marketing paths like `/chat/occ`… which ARE valid embed parents, but also any future `/chateau`; exact-prefix is precise. Note: Pages `/chat` shell as referer now returns true — intended during compat since the shell IS an embed parent).
4. **postMessage:** NO dual-listen (names frozen, §T4 rationale). Fallback spec if owner overrides: parents check `data.type === "digichat:ready" || data.type === "chat:ready"` — do not implement unless asked.
5. **`?layout=` + registry + mode dual-read** (T1 normalize-at-parse) — no separate shim code beyond the normalizers.
6. **Env aliases** (T6 table) — removal PR deletes alias arms.

## T8 — Docs

Each file: rg `/embed` after edit must show only intentional remains (frozen names, historical ADR note, compat notes).

- [ ] `frontend/digichat/README.md`: install/snippet `/embed?host=` → `/chat?host=`; env table to canonical names with alias footnote.
- [ ] `frontend/digichat/ARCHITECTURE.md`: route table + `/embed` mentions → `/chat` (+ one compat paragraph).
- [ ] Root `ARCHITECTURE.md` + `README.md`: `/embed` refs → `/chat` (verify by rg; keep historical ADR links intact).
- [ ] `docs/digichat/INSTALL.md`: line ~132 `Enable /embed as needed` → `Enable /chat as needed`; ~133 `/` redirects to `/embed` → `/chat`; ~154 token paragraph unchanged (header frozen); ~179 `Embed URL /embed?host=` → `/chat?host=`; ~181–199 `sets /embed frame-ancestors`, `frontend/digichat/embed-hosts.txt`, `http://127.0.0.1:3005/embed?host=` → `/chat` equivalents; `git mv frontend/digichat/embed-hosts.txt frontend/digichat/chat-hosts.txt` + ref update.
- [ ] `docs/digichat/STOCK-SMOKE.md`: line ~19 `DIGICHAT_CONFIG_PATH=…digithings-ai-embed.yaml` — rename example config? File `config/examples/digithings-ai-embed.yaml` exists? Verify by ls; if renamed, update ref. Line ~35 `/embed?host=https://digithings.ai` → `/chat?host=…`; line ~42 `embed-send-gate` → `chat-send-gate` (post-T5).
- [ ] `docs/DEPLOYMENT.md`: lines ~140, ~148, ~165, ~170–176, ~221–236 (`/embed` guest paths, `chat.digithings.ai` note, `/chat` shell smoke, iframe CSP check) → guest `/chat` (+ compat note); redirects table `249-253` (`/chat` must never appear as redirect target) MUST be amended — `/chat` becomes a Worker-served path per Q1 decision; rewrite that rule explicitly rather than leaving a contradiction.
- [ ] `docs/adr/0018-digichat-path-routing.md`: append amendment entry (never edit historical notes 1–7): decision table `digithings.ai/embed*` → canonical `/chat*` (+ compat), `iframe → /embed?host=` → `/chat?host=` (2 rows). Historical note 1 (`DIGICHAT_BASE_PATH=/chat`) stays verbatim.
- [ ] `frontend/digichat-cloudflare/README.md`: per T3. `frontend/digichat/src/lib/base-path.ts:6` comment `NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat` → `=/digichat` (with route dir now `/chat`, a `/chat` basePath would nest to `/chat/chat` — call out in comment).
- [ ] `docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md`: only if it pins `/embed` health-check curls — update curls, do not rewrite history sections.

## T9 — Old-path removal (separate PR, after one release)

- [ ] Delete `/api/embed/[...path]` compat route; delete `/embed` proxy branch + matcher entries; collapse next.config lookahead to `"/((?!chat$|chat/).*)"`; remove `/embed` header sources.
- [ ] `isChatReferer`: drop `/embed` arms. Registry/mode normalizers: drop old-token arms (keep canonical + error strings). Env: drop alias arms. Worker `paths.ts`: drop old arms; wrangler: drop apex `/embed*` route (per Q1 outcome).
- [ ] Re-run full suites + T10 checklist against a deploy with zero `/embed` references outside frozen names/history.

## T10 — Acceptance criteria

- [ ] C1 Routes: `GET /chat?host=digithings.ai` 200 first-paint tenant theme (no dark→light flash — same assertion class as #1379); `GET /embed?host=…` → 308 to `/chat?host=…` preserving full query; `GET /api/chat/tenant-config` 200 `no-store`; `GET /api/embed/tenant-config` → 308.
- [ ] C2 Tokens: `?layout=compact|full` honored end-to-end (popup narrow vs full-page wide); legacy `?layout=embed|page` normalized (compat); tenant YAML `layout: full|compact` validates, old values normalize; `chrome.mode: full|compact|modal|sidebar` validates, old `app|embed` normalize; `/` redirect honors `compact|modal|sidebar` → `/chat`.
- [ ] C3 Cached-widget.js scenario (mandatory): pin `widget.js` to the PRE-rename bytes in a fixture page (frozen attrs + `buildSrc` → `/embed?layout=embed`, listening only for `digichat:ready`); load against the NEW server; assert panel opens, iframe 308-lands on `/chat`, `digichat:ready` handshake completes, `digichat:page-context` delivered, `/api/deploy/chrome?host=` labels apply. Fails if any frozen name changed or the 308 drops query params.
- [ ] C4 Third-party iframe (DataTapStream-shaped): hand-built iframe `src="<origin>/embed?host=<registered customer host>&token=<token>"` loads and chats; no `X-Embed-*` value changed; CSP `frame-ancestors` admits the customer host on BOTH `/chat` and compat `/embed` responses.
- [ ] C5 Shells: dashboard popup (Desk+ entitled) opens `/chat?layout=compact` iframe with theme/accent/welcome passthrough; baseline tier still sees upgrade CTA, never an iframe; digithings.ai `/chat` + `/chat/occ` shells sync theme without reload (`digichat:theme`).
- [ ] C6 Codemod hygiene: zero `rg` hits for `@/lib/embed-`, `@/hooks/use-embed-`, `components/stock/embed-`, `"layout", "embed"`, `layout: "page"` outside frozen-name lines, compat arms (marked `COMPAT`), `DROP_TAGS` HTML-tag entries, and historical docs; `npm run test` + `npm run lint` green in `frontend/digichat`, `frontend/dashboard`, `frontend/digithings-web`, `frontend/digichat-cloudflare`.
- [ ] C7 `DIGICHAT_BASE_PATH=/digichat` smoke: build with basePath set, assert no `/chat/chat` nesting and tenant-config fetch prefixed via `p()`.

## Rollback

- Each task is its own PR (T0+T1+T2 together allowed — dual-serve is the atomic unit; T4 shells PR only after that deploys; T9 removal last). Revert order is reverse ship order.
- Fast rollback (compat window): revert the shells PR (T4) — old `/embed` paths serve fully until T9, so shells pointing back is a complete rollback of user-visible behavior. No data migration exists (localStorage keys are client-side, fresh-start acceptable).
- If the T0–T3 deploy itself is bad: revert the dual-serve PR; `/embed` serving is untouched by definition (new paths are additive until T9).
- Worker route rollback: `wrangler.toml` route changes deploy independently of code — keep the route-add and path-rename deploys as separate releases so each reverts alone.

## Risks / open questions

- **Q1 (P0, blocks T3 wrangler edit): `digithings.ai/chat` collision.** The apex `/chat` + `/chat/occ` paths are Pages-owned marketing shells (`paths.test.ts` pins `shouldProxyToDigiChat("/chat") === false`, `("/chat/occ") === false`; `docs/DEPLOYMENT.md:249-253` forbids `/chat` as a redirect target). A Worker `digithings.ai/chat*` zone route shadows those shells (Worker routes take precedence over Pages). Recommended: canonical container path `/chat` served ONLY on `digichat.digithings.ai` (already in dashboard `DIGICHAT_POPUP_FRAME_ORIGINS`, digithings-web `frame-src`, and `security-headers.ts` first-party thinking) + loopback; apex keeps `/embed*` → 308 to the absolute canonical URL; Pages shells + dashboard env `NEXT_PUBLIC_DIGICHAT_*_ORIGIN` repoint to `https://digichat.digithings.ai`. Owner decision required before T3; the alternative (apex shadowing + Pages shell relocation) needs its own plan.
- **Q2: `/widget.js` serving path unverified.** `public/widget.js` is container-static, but `shouldProxyToDigiChat` has no `/widget.js` arm — yet the header comment prescribes `src="https://digithings.ai/widget.js"`. Verify how third parties actually fetch it (Pages copy? Worker passthrough?) before T4; whatever serves it must serve the NEW bytes at the SAME URL (frozen URL — cached copies reference old bytes by design, covered by C3) and the Q1 host decision changes its `originFromSrc` default.
- **Q3: `slug: "embed"` → `"chat"` side effects.** `client-projection.ts:106` default slug and `embed-chat-tenant.ts:159` anonymous slug feed rate-limit buckets (`byok-models:embed:`, `mcp-oauth:embed:`), `ownerUserSub`, and observability group-bys. Rename resets buckets (acceptable, note in release notes) but dashboards alerting on `tenantSlug="embed"` need updating — grep observability saved views before T5.
- **Q4: `dc-embed-shell` CSS class kept.** Deliberately out of scope (pure internal hook, `chat-client.tsx:1156` + `layout.tsx:35` + `globals.css` readable-measure rule). Rename is a trivial follow-up; doing it here only widens the diff.
- **Q5: `modal`/`sidebar` chrome.modes** keep names (no collision with `chat`), but both funnel to the `compact` presentation side in `loader.ts:165` and the `/` redirect — confirm with owner that `modal`/`sidebar` shells should keep iframing `?layout=compact` (yes, recommended) rather than gaining distinct values.
- **Q6: DataTapStream (`datatapstream.com`) references** in suggestion pools / seed fixtures are tenant content, not paths — do not touch; C4 covers their iframe shape generically without naming customer hosts in tests (use `customer.example` fixtures).
- **Q7: Phase-3 "merged worker" location.** If the merged router lives outside `frontend/digichat-cloudflare/` (not found in-repo), T3's file list is wrong — implementer must locate it first and confirm `digithings-stack-cloudflare` stays route-free.
