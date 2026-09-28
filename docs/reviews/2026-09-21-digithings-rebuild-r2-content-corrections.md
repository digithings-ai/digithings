# R2 slice — content corrections on digithings.ai (2026-09-21)

Slice of the digithings.ai rebuild (plan §6, §7). Epic #4424. Branch
`task/4429-digithings-rebuild-r2`. Base `origin/develop` @ `44de2d00b`
(post-#4440 D1, post-#4446 C1).

The D1 rebuild (#4440) and the C1 content audit (#4446) are already merged, so this
slice re-verified the honesty findings against source rather than re-running the
audit. One real defect was found; four commonly-listed concerns were checked and
disproved.

## Changed

`apps/digithings-web/app/legal/privacy/page.tsx` — copy only, no structure change.

The notice claimed two things the code does not do:

1. That local storage holds "your selected provider, model, **and API key**", and
   that "If you bring your own key, **it is stored in local storage** in your
   browser."

   `lib/providerSettings.ts` never writes the key. `persistProviderPreference()`
   persists only `digichat:provider` and `digichat:model`; `readFromStorage()`
   always returns an empty `apiKey`; `purgeLegacyApiKey()` deletes the legacy
   `digichat:api_key` entry from both local and session storage and is called
   unconditionally on every page load by `components/LegacyByokPurge.tsx`
   (mounted from the root layout, #2348). The key lives in React state for the tab
   session only. The notice overstated retention of a secret — the worst direction
   to be wrong in a privacy notice.

2. That a key-test or chat request sends the key to "OpenRouter, OpenAI,
   Anthropic, or Google".

   `functions/api/byok/test.ts:4` types `ProviderId` as
   `"openrouter" | "openai" | "anthropic" | "gemini" | "xai"` and validates all
   five. xAI was missing from the notice.

Both corrected to state what the site actually stores, and to name xAI. The
"browser storage" paragraph no longer says "clear the saved key", which implied a
persisted key.

`EFFECTIVE_DATE` is deliberately unchanged: the data flows did not change, only a
wrong description of them. Flagged here rather than silently bumped.

## Checked and disproved (no change made)

1. **`/openwiki` in the nav (`app/_nav.tsx:41,67`) and sitemap
   (`app/sitemap.ts:19`).** Not a defect. `scripts/build-digithings.sh:86-112`
   exports the visualizer into `dist/openwiki/` and hard-fails unless `index.html`,
   `graph.json`, `client.js`, `client-lib.js` and `styles.css` all exist; `openwiki/`
   holds 15 generated entries; `lib/security-headers.mjs` carries the matching
   `/openwiki/*` `_headers` exception. C1 (line 77) had already ruled the plan §8
   concern stale.
2. **`lib/repo-activity.json` `generatedAt: 2026-09-15`.** Not a defect — a stated
   contract. `lib/repoActivity.ts:15-16` documents that "`generatedAt` is printed so
   a stale snapshot reads as dated rather than current", and the page prints it. C1
   (lines 35, 95) kept it.
3. **`lib/apiDocs.ts:569` "the deployed digithings.ai chat is an agentic Cloudflare
   Pages Function (no login)".** Accurate:
   `apps/digithings-web/functions/api/chat.ts` and `functions/api/byok/test.ts`
   exist and deploy with the site (`wrangler.toml`), and `/chat` renders
   `ChatEmbedShell` → digichat `/embed`.
4. **`siteCounts.ts` `COUNTED_AT` "20 September 2026" vs the repo snapshot's
   2026-09-15.** Different artifacts — repository-snapshot counts versus a commits/
   releases snapshot — each dated on its own page. Not an inconsistency.

## Note on the C1 audit

C1's `/legal/privacy` verdict ("BYOK-in-localStorage + Function-forwarding matches
`ProviderSettings` + chat route") verified the forwarding half but not the storage
half, so the local-storage claim survived a signed audit. Worth knowing that a
verdict citing a file is not the same as reading it.

## Gates (2026-09-21, all green)

- `python3 scripts/check_frontend_canon.py` → clean
- `npm run lint --workspace digithings-web` → clean
- `npm run test --workspace digithings-web` → 12 files / 72 tests pass
- `npm run build --workspace digithings-web` → green static export (all routes
  prerendered, incl. `/legal/privacy`)
- `python3 scripts/check_doc_links.py` → see PR

## Landing note (2026-09-24, #4629)

The privacy copy correction originally lived in PR #4470 against the rebuilt page.
After website revert #4489 restored `apps/digithings-web`, the same copy fix is
re-applied against the restored layout in `fix/4629-privacy-byok-copy` (issue #4629).
PR #4470 is reduced to kit-only (no privacy page). The factual claims below still hold
against `lib/providerSettings.ts` and `functions/api/byok/test.ts` on develop.
