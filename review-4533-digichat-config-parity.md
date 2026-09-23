# In-session review — PR #4533 (digichat app/embed config parity, Phase 2c)

- **Subject:** PR [#4533](https://github.com/digithings-ai/digithings/pull/4533) — `feat(digichat): let embed tenants set the feature flags and seed language` — branch `task/4532-digichat-config-parity` → `module/digichat`
- **Tracking issue:** [#4532](https://github.com/digithings-ai/digithings/issues/4532)
- **Reviewed revision:** `701e1b6b7`
- **Fixes:** `c8132bc88`
- **Reviewer:** independent fresh-context read-only subagent (agent `general`, delegation `eager-amber-lynx`, 2026-09-23T00:07:06Z → 00:10:33Z). The author session did not review its own work. The reviewer had **no shell tool**, so it reconstructed the diff via the GitHub API and read files on disk; it did not run test/lint/build.
- **Verdict:** **REQUEST CHANGES** — severity counts **1 blocker / 1 major / 2 minor / 3 nit**

## Summary

The two headline capabilities — the four feature flags (`features.dictation`, `speech`, `sources`, `branchPicker`) and `chrome.defaultLanguage` — did **not** take effect on the live `/embed` surface. The new parity test exercised a projection path the runtime does not use, so it passed green over a no-op. Both were fixed in `c8132bc88`.

## Findings

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | **blocker** | The four flags (and `defaultLanguage`) were dropped by the loader bridge the live `/embed` path actually uses. `/embed` first paint resolves through `resolveEmbedClientConfigForPaint` (`app/(digichat)/embed/page.tsx:81`) → `embed-chat-tenant.ts:153` → `matchHostDeployment` + `deploymentToEmbedTenant`, and `GET /api/embed/tenant-config` uses `resolveVerifiedEmbedTenant` → the same function. `deploymentToEmbedTenant` (`deploy-config/loader.ts:145-182`) mapped only `attachments`/`pageContext`/`view`/`thinking`/`webSearch`; `embedTenantToDeployment` (`loader.ts:66-142`) additionally **hard-coded** `defaultLanguage: DEFAULT_LANGUAGE_CODE`, `dictation: false`, `speech: false`, `sources: true`, `branchPicker: true`. Net: a tenant setting `sources: false` silently kept it ON; `dictation`/`speech: true` stayed OFF; `defaultLanguage` stayed `en`. The parity test missed it by calling `parseEmbedTenants → toEmbedClientConfig → clientConfigFromEmbedTenant` directly. | **Fixed.** `embedTenantToDeployment` now carries the tenant's values (`defaultLanguage: cfg.defaultLanguage ?? DEFAULT_LANGUAGE_CODE`, `dictation: cfg.dictation === true`, `speech: cfg.speech === true`, `sources: cfg.sources !== false`, `branchPicker: cfg.branchPicker !== false`); `deploymentToEmbedTenant` carries them back, projecting only non-default values so the existing client contract is unchanged. New tests: a deployment-bridge round trip, and a route-level test through `GET /api/embed/tenant-config`. |
| 2 | **major** | `chrome.defaultLanguage` had no consumer on the embed surface. Its only reader is `stock-chat-prefs-host.tsx:44` (`language: clientConfig.chrome.defaultLanguage || detectBrowserLanguageCode()`), and `useStockChatPrefs` is used only by `home-stock-client.tsx` and `baseline-client.tsx` — not the embed. `embed-client.tsx`'s `chatPrefs` initializer never seeded `language`, and `reset`/`newThread`/`compactThread` reset to a hard-coded `DEFAULT_LANGUAGE_CODE`. The plan doc's "Embed honours it" row was therefore false. | **Fixed.** `embed-client.tsx` derives `const tenantLanguage = stockClient.chrome.defaultLanguage \|\| DEFAULT_LANGUAGE_CODE;`, seeds `language: tenantLanguage` in the `chatPrefs` initializer, and all three reset paths now use `tenantLanguage`. |
| 3 | minor (pre-existing) | `DIGICHAT_EMBED_TENANTS` silently drops `tools`/`models`: `validateEntry`'s return object (`embed-tenants.ts:526-578`) never emits them though the type declares both and downstream bridges read them. JSON tenants therefore cannot set `models.allowPicker` / `tools.catalog`; only the YAML path can. | **Out of scope** — not introduced by this PR. Recorded here; candidate for a follow-up issue. |
| 4 | minor | Plan doc line 174 cited `client-projection.ts:178-180`; the actual fold is at `176-178`. | **Fixed** in the plan doc. |
| 5 | nit | Three duplicate language-code sets exist: `embed-tenants.ts:32` (new), `schema.ts:23`, and a module-private `KNOWN_CODES` in `languages.ts:64`. Suggest exporting an `isKnownLanguageCode()` from `languages.ts` and reusing it. | **Accepted, not actioned** — kept the local set to avoid extra churn in this PR; noted for the ownership-consolidation phase. |
| 6 | nit | Plan doc line 171's `userAlign` rationale overstated: only the first-party `digichat` skin forces left alignment (`product-shell.tsx:349-350`); other skins would honour it. The "not configurable" decision still stands because the embed cannot set it. | **Fixed** in the plan doc. |
| 7 | nit | `DEFAULT_EMBED_TENANT_CONFIG` (`embed-client-config.ts:97-118`) omits the new fields. | **Correct as-is** — unlike the `mcp` keys (projected with `=== true`, so they must be present), the new flags use `?? base.features`, so absence yields the base defaults. No change. |

## Verified clean by the reviewer

- **A** `LANGUAGES` is `{code,label,native}[]` (`languages.ts:10-57`); the new `LANGUAGE_CODES` is built from `.code` (`embed-tenants.ts:32`), no in-file collision (only `PAGE_CONTEXT_MODES`); validator + builder correct.
- **B** The projection asymmetry is intentional and correct: `FeaturesSchema` defaults `dictation`/`speech` false (`schema.ts:196-197`) and `sources`/`branchPicker` true (`:202,:210`), so `true` turns the first pair ON and `false` turns the second pair OFF.
- **C** At the bridge level the fixed keys (`persistence`, `auth`, `chrome.mode`, `tools.allowUserToggle`) are unchanged (`embed-bridge.ts:40,52,53,74`).
- **D** `parseEmbedTenants` returns a `Map` (`embed-tenants.ts:581`) so `.get(...)` is right; `entry()` produces a schema-valid tenant; no cross-test leak; tests non-vacuous against the projection.
- **E** The `schema.ts` diff was comments only.
- **F** Once in `tenantCfg` the flags DO reach the runtime adapters and CSS (`embed-client.tsx:369,578,1245` → `product-shell.tsx:132-137` dictation/speech, `:164-178` sources/branchPicker) — the filter was upstream (finding 1).
- **Security:** `toEmbedClientConfig` has no `token`/backend branch; `embed-client-config.test.ts:154-165` asserts no token/endpoint; no new URL/token/credential is projected. No BFF/secret-boundary regression.
- Diff touched no `route.ts` auth path, no new dependency, no lockfile change.

## Could not verify (reviewer)

test/lint/build results (no shell tool). Findings 1 and 2 are static data-flow conclusions; finding 1's repro was supplied and has since been run by the author (see below).

## Post-fix verification (author)

- Non-vacuousness proved: with only `loader.ts` reverted to `HEAD`, `GET /api/embed/tenant-config` route test fails (`expected undefined to be true` at `route.test.ts:190`); with the fix it passes.
- Targeted: `npx vitest run src/lib/embed-tenants.parity.test.ts src/app/api/embed/tenant-config/route.test.ts src/lib/deploy-config/loader.test.ts` → **3 files / 49 tests passed**.
- `apps/digichat` `npm run test` → **128 test files / 1273 tests passed**.
- `apps/digichat` `npm run lint` → **30 problems, 0 errors** (all pre-existing warnings).
- `apps/digichat` `npm run build` → TypeScript clean, all routes generated (then `rm -rf apps/digichat/.next/standalone`).
- `python3 scripts/check_frontend_canon.py` → **clean**.
- `python3 scripts/check_doc_links.py` → **OK (418 markdown files scanned)**.
