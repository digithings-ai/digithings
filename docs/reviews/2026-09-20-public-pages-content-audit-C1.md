# C1 — public-page content audit (digithings.ai + digiquant.io)

Signed: content-audit slice, 20 September 2026. Audited tip: `origin/develop` @ `080d3bd1e`
(post-#4440 D1, post-#4441 Q1). Issue: #4431. Epic: #4424. Plan §7 is the checklist.

Base note: this worktree arrived on a stale base (it still carried `frontend/`,
which `origin/develop` no longer has) and was reset to `origin/develop` before
any reading, per the slice brief.

## What changed in this slice (copy only, no structure)

| File | Change | Why |
|---|---|---|
| `packages/ui/src/data/modules.ts` (digisearch entry) | summary "Chroma or Azure AI Search" → "Cloudflare Vectorize, Azure AI Search, or Chroma"; added Cloudflare Vectorize to the stack list | Omitted the canonical first backend; contradicted the site's own "3 vector backends" figure. Source: `digisearch/src/digisearch/backend_require.py` (`require_real_search_backend`: Cloudflare → Azure → Chroma) and `core/standard_hits.py` (`vectorize`/`azure_ai_search`/`chroma`/`stub`) |
| `apps/digithings-web/lib/apiDocs.ts` (digisearch) | `/query` response `backend` enum gains `"vectorize"`; env table gains `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` | Same sweep: the enum and env table described a two-backend world |
| `apps/digithings-web/lib/siteCounts.ts` | `FRONTEND_TEST_FILES` 451 → 455 | Re-derived 2026-09-20 with the recorded command; drift is the R1/D1/Q1 kit chrome tests |
| `apps/digithings-web/lib/sharedDocs.ts` (digichat-install) | `docker pull …:v0.9.3` → `:v2.3.1`; "published through v0.9.3" → "v2.3.1" | v0.9.3 is six weeks stale; GHCR container API 2026-09-20 shows `v2.3.1` (+`latest`) as newest |
| `packages/design/releases.json` | added digichat v1.4.0, v1.5.0, v2.1.0, v2.2.0, v2.3.0, v2.3.1 | Feed stopped at v1.3.2 (2026-08-21); both `/changelog` pages render from it and were a month stale |
| `apps/digithings-web/app/quality/page.tsx` (limits row) | rewrote "Frontend is scored differently" | Two false statements: score.py excludes only `.py`-less diffs by construction (it scores `*.py`, line 362 — not "excludes apps/** and packages/**"), and test-web.yml runs the digithings-web, @digithings/ui, @digithings/digichat-ui, cron and stack-cloudflare suites. The real gaps are digiquant-web and the design reference (test scripts exist, no lane runs them) |

## Counts re-derived 2026-09-20 (all keep)

- `find tests -name 'test_*.py' | wc -l` → **809** (whole-repo `find` gives 832; the 23 extra live outside `tests/`, the recorded scope — keep 809)
- frontend tests (recorded `find apps packages …` command) → **455** (changed, see above)
- `ls .github/workflows/ | grep -c '\.yml$'` → **74**; `grep -c '^test-'` → **17**
- compose services → **23**, default (no `profiles:`) → **10** (parsed `docker-compose.yml` with PyYAML)
- modules registry → **11** total, **9** shipping (4 core + 5 support), **2** roadmap
- digikey top-level `*.py` → **18** ("eighteen Python modules" keeps)
- uv workspace members → **11**; pip-audit matrix lists the 7 Python components named on /security (digibase, digigraph, digiquant, digisearch, digismith, digikey, digiclaw) — keeps
- portfolio graph appends in `build_portfolio_phases_thesis()` → **10** (H1–H9 + coverage director); research daily list (preflight, triage, phase1–7, publish) → **10**; pipeline total **20**; `LIVE_ORDERS` **0** — all keep, portfolio side pinned by `pipeline-data.test.ts`
- research A0–A4 (preflight → triage → segments → consolidate → digest) per `research/docs/agentic/ARCHITECTURE.md` — subsystem fine print keeps
- rate limit 10/min burst 20 (`digikey/ratelimit.py` defaults), timeout envelope connect-5/read-30/write-10/pool-5 (`digibase/http_client.py`), JWKS cache 300s (`digikey/jwt_verify.py`), disclosure 72h/7d (`SECURITY.md:189`) — all keep
- SDCA default knees 25/70 (`tearsheet/dca.ts` `DEFAULT_SDCA_KNEES`) — keep
- six FastAPI services installing `install_request_id_middleware` (digigraph, digisearch, digiquant, digismith, digivault, digikey) — "all six" keeps
- repo-activity.json snapshot dated 2026-09-15 (`generatedAt` printed on-page; "stale reads as dated" contract in `repoActivity.ts`) — keep

## Per-page verdicts

Conventions: each claim lists source + date + verdict. Dimensions without findings are marked clean.

### digithings.ai `/` — keep, no copy change

- Claims: 9 shipping / 2 roadmap (modules registry), 23 services / 10 default (compose), 3 vector backends (backend_require.py), 0 keys stored (chat route forwards per-request `x-byok-key`) — all verified 2026-09-20, keep. Install tabs (docker/local/ghcr) match README paths; no `curl|sh` invented — keep.
- Links: /chat, /docs, mailto contact@digithings.ai, github.com/digithings-ai/digithings — resolve. Clean.
- Honesty: "nothing here is a projection and nothing promises live trading" (file comment) holds on the rendered copy. Clean.
- Placeholders: none. Metadata: root layout title/description/OG (`nine modules` matches the registry). Clean.

### digithings.ai `/about` — keep, no copy change

- Claims: MIT whole-repo (root LICENSE), loopback-by-default compose, per-request credentials, X-Request-ID on six services, Polars/Pydantic/LiteLLM/MCP/Nautilus composition — each has a named file behind it; verified 2026-09-20. The "live-trading adapters are stubs behind a review gate" limit matches the brokers/ source + pre-push hook. Keep.
- Links: /security, /docs, /quality, github org — resolve. Clean. Honesty/placeholders/metadata (own title+description): clean.

### digithings.ai `/docs` (guides + per-module reference) — fixed (see table)

- Vector-backend sweep: landing/principles already said 3 (siteCounts). The stale "2" lived in the module registry + apiDocs, both fixed above. `/query` mode enum (`keyword|vector|hybrid`), scopes, JWKS auth notes match server code. The digichat-install GHCR tag fixed above.
- "Never expose live-trading without explicit human approval" restates AGENTS.md verbatim. Clean.
- Links: internal `/docs/api/` link + module GitHub links resolve. Placeholders: none (input `placeholder=` attrs in ProviderSettings are HTML input hints, not copy). Metadata: own title+description. Clean.

### digithings.ai `/docs/api`, `/docs/api/[service]` — keep

- "Committed specs under docs/openapi/, not live localhost /docs" matches `lib/sync-openapi.mjs` + prebuild. Service ids/ports/roles in `openapiCatalog.ts` match the architecture service map (:8000–:8005, :3005). Clean on all five dimensions.

### digithings.ai `/changelog` — data fixed (see table)

- Copy ("versioned frontend packages only… rest ships on develop without a product tag") is accurate. The feed itself was stale; now current through v2.3.1. Link to github.com/digithings-ai/digithings/releases resolves. Note: two pre-existing rows carry dates a few days off the GitHub `publishedAt` (v1.3.2, digiskills v0.2.1) — left untouched, flagged for the feed owner.

### digithings.ai `/quality` — fixed (see table)

- Figures (809/455/74/17) re-derived above. Thresholds Security 8 / Quality 8 / Optimization 7 / Accuracy 9 match score.py + scoring README + CLAUDE.md (page names the rubric-file disagreement — keep). Lanes prose matches workflow files. Limits row rewritten (was false, see table). No placeholders; own metadata; links to github scoring dir + /security + /docs resolve.

### digithings.ai `/security` — keep, no copy change

- Spot-verified the load-bearing rows 2026-09-20: RS256+kid + bcrypt-hashed keys with cleartext prefix + fail-closed middleware + Redis jti blocklist (opt-in, no-op without URL) + 10/20 rate limit; correlation/audit/timeouts/CORS rows; gitleaks + pip-audit scope rows (7 components, 11-member workspace boundary, Python-only); the 12 limits are a declared selection from the STRIDE residual-risk column. Disclosure 72h/7d matches SECURITY.md:189. The page's two deliberate divergences from older prose (audit writer attribution, revocation blocklist) both match code. Keep.

### digithings.ai `/services`, `/team`, `/legal/privacy`, `/chat`, `/chat/occ`, 404 — keep

- Services: no prices, no SLA commitments — clean. Team: single maintainer card, vendored avatar, no biography claims beyond the repo — clean. Privacy: effective August 5 2026 (stated date, keep); BYOK-in-localStorage + Function-forwarding matches `ProviderSettings` + chat route; 5-minute handoff expiry matches `chatHandoff`; chat rate-limit/KV wording matches the Function code. /chat metadata ("grounded via digigraph and digivault, running on digillm") — digigraph backend confirmed in `ChatEmbedShell`; digillm→LiteLLM + digivault adapters are digigraph's documented profile-A wiring (sharedDocs). Keep with that chain cited. /chat/occ: OCC corpus grounding is tenant runtime config, not repo-verifiable — **could not fully verify**, stated here rather than reworded; copy is minimal and makes no performance claim. 404s: both have title+description and two honest CTAs. Sitemap lists all static routes + per-service API routes; `/openwiki` intentionally untouched per brief (deploy script exports the route; §8 concern stale).

### digiquant.io `/` — keep, no copy change

- Hero makes no performance claim; artefact footer reads "illustrative surface · not live results" + "0 live orders" (LIVE_ORDERS). Metrics band: subsystems (registry length), phases (PIPELINE_PHASES.length = 20), trades (live Supabase sum), live orders 0 — all derived, none hardcoded. "No projections" lede holds. Pricing: self=Free·MIT / managed=Coming soon (honest status, not a placeholder) / enterprise=Contact; FAQ disclaims usage caps and defers NautilusTrader licensing to upstream. Keep.

### digiquant.io `/strategies`, `/strategies/[id]` — keep

- "Nautilus backtest on Coinbase daily OHLCV" matches the tearsheet data path; honesty chips (`BacktestOnlyChip`, `OosHonestyChip`) + "Illustrative Nautilus backtest… not a live strategy" notes + print footer "Illustrative backtest · not investment advice" + tearsheet footer meta "illustrative, in-sample" all present verbatim. SDCA knees 25/70 sourced. Four published slugs match `generateStaticParams`; sitemap lists all four. Keep.

### digiquant.io `/subsystems/[id]`, `/contact`, `/changelog`, `/pipeline`, 404 — keep

- Subsystem fine print (A0–A4 / H1–H9 / paper router) sourced above; execution copy ("paper adapters ship… connecting a live venue is your own integration") matches the subsystem registry + stub adapters — no live-trading promise. Contact two-tier copy matches `_contact.ts`; managed "in development" is honest. Changelog shares the refreshed feed. /pipeline is a redirect with a real link fallback (not a silent drop). Sitemap complete (11 routes). Metadata present on every route including 404.

## Could not verify (stated, not reworded)

1. `/chat/occ` "grounded on the OCC help corpus" — tenant runtime config, no repo source.
2. Homepage "0 keys stored" for the *hosted* Function path rests on the chat route not persisting keys — verified in code, but a deploy-time DB write would not show in the repo; the privacy page's "we do not write the key to an application database" is the same class of claim. Both kept with the code citation.
3. Repo snapshot figures (2388 commits etc. from plan §7) no longer appear as prose claims — RepoActivity renders the dated snapshot file. Nothing to verify beyond the snapshot date (2026-09-15), which is printed.

## Gates (all run 2026-09-20, all green)

- `python3 scripts/check_doc_links.py` → OK (413 markdown files scanned)
- `python3 scripts/check_frontend_canon.py` → clean
- `npm run build --workspace digithings-web` → green (static export)
- `npm run build --workspace digiquant-web` → green (static export)
- `npm run test --workspace digithings-web` → 12 files / 72 tests pass
- `npm run test --workspace digiquant-web` → 11 files / 69 tests pass (incl. the portfolio-graph pin)
- `npm run test --workspace @digithings/ui` → 59 files / 429 tests pass
