# Review — PR #4536: digichat AI-SDK backends (Phase 5b)

- **Subject:** PR [#4536](https://github.com/digithings-ai/digithings/pull/4536) — branch `task/4535-digichat-ai-sdk-backends`, base `module/digichat`
- **Reviewed revision:** `e16c62597` (`feat(digichat): add openai-compatible AI-SDK backends`)
- **Fixes:** commit `fix(digichat): close the AI-SDK backend review findings` (`Refs #4535`)
- **Reviewer:** independent fresh-context read-only subagent (delegation `curious-golden-raven`, agent `general`, 2026-09-23T00:43:23Z → 00:47:49Z). The author session did not review its own work. The reviewer had **no shell tool**, so it reconstructed the diff via the GitHub API and verified statically; it did not execute test/lint/build.
- **Verdict:** APPROVE WITH NITS
- **Severity counts:** blocker 0 · major 0 · minor 2 · nit 3

## Findings and resolution

| # | Sev | Finding | Resolution |
|---|-----|---------|-----------|
| MINOR 1 | minor | `turnMutation: true` declared for both new adapters (`backend-adapters.ts`) but unreachable — `createAiSdkStreamResponse` accepts no `turnMode` and the client gate (`embed-client.tsx:580-581`) only enables regen/edit for digigraph/foundry. The capability matrix would mislead the next provider implementer. | **Fixed** — both entries now `turnMutation: false` with a comment ("not wired yet … until the mapper threads it (#4535)"), and the registry test pins `turnMutation === false`. |
| MINOR 2 | minor | The `apiKeyEnv` `DIGICHAT_BACKEND_` prefix is a naming convention, not a per-entry key binding; the schema comment overstated isolation. | **Fixed** — the schema comment now states it bounds *which* vars are nameable but does not bind an entry to its own key, and notes a per-entry `DIGICHAT_BACKEND_<SLUG>_KEY` would be needed if tenant-authored config is ever accepted. |
| NIT 1 | nit | `apps/digichat/src/app/api/chat/route.ts:19` had two import statements on one line (editing accident). | **Fixed** — newline between the imports. |
| NIT 2 | nit | Pre-existing (5a) doc comment claimed "a test asserts each adapter's canned stream normalizes to the declared parts" — no such fixture exists yet. | **Fixed** — comment now says the canned-stream normalization fixture lands in 5d and that the parity test currently asserts the boolean flags. |
| NIT 3 | nit | Redundant tail assertion `expect(BACKEND_ADAPTERS["openai-responses"].protocol).toBe("openai-responses")` already implied by the loop. | **Fixed** — removed; replaced by the `turnMutation` assertion for MINOR 1. |

## Verified clean (A–G)

- **A — schema:** `OpenAiCompatibleFields` enforces https-only `baseUrl`, non-empty `model`, and the exact `/^DIGICHAT_BACKEND_[A-Z0-9_]+$/` regex; both objects `.strict()`; both members present in the `BackendSchema` discriminated union.
- **B — registry:** `BACKEND_ADAPTERS` is `Record<BackendType, BackendAdapter>` covering all four members; both new entries `auth: "env"` with `protocol === type`; `AI_SDK_PROTOCOLS` and `isAiSdkConfig` present and correct. `anthropic-messages`/`gemini` have no adapter, so their membership in `AI_SDK_PROTOCOLS` is inert future-proofing, correctly gated by `isAiSdkConfig(backend)`.
- **C — providers/stream:** the credential is read from `process.env[apiKeyEnv]` only, never logged and never returned to the client; `.responses()` for `openai-responses`, `.chat()` for `openai-completions`; a missing credential yields a 502 JSON `backend_unavailable` naming the env var **name** only, with no upstream call. No `baseUrl`/key reaches the browser.
- **D — route:** the AI-SDK branch sits after `coreMessages` and before the BYOK guard; the condition is `AI_SDK_PROTOCOLS.has(adapter.protocol) && isAiSdkConfig(backend)`; **no** `backend.type ===` comparison in the handler (the source guard still passes); `runLock.release()` on the throw path; foundry returns earlier and digigraph falls through unchanged.
- **E — embed-tenants:** the new dispatch branch validates the same https + prefix rules; the final error enumerates all four types; `EmbedBackendConfig` carries the new shape; narrowing on `unknown` via literal `===` is sound.
- **F — widened unions:** `client-projection.ts` and `embed-client-config.ts` widened; the only consumers use the value as an opaque fact or an explicit two-way `===`; no exhaustiveness dependency, so no compile break.
- **G — tests non-vacuous:** the registry key set is now four types; the source guard still forbids `backend.type` comparisons; `backend-ai-sdk.test.ts` accepts both types and rejects http `baseUrl`, `AUTH_SECRET`, `DIGIKEY_BFF_TOKEN`, and empty `model`; `providers.test.ts` asserts `chat` vs `responses` selection (with `not.toHaveBeenCalled` on the other) and the credential error; the route test mocks the mapper and asserts the last call's `backend.type`/`model` — reverting the feature makes the mapper never called and the assertion throw.

## Type-chain verification

`@ai-sdk/openai@4.0.59`: `responses(modelId): BatchLanguageModelV4`; `Experimental_BatchLanguageModelV4 = BatchLanguageModelV4 = LanguageModelV4 & BatchModelV4<…>` (`@ai-sdk/provider`), which is assignable to `LanguageModelV4`; `ai`'s `LanguageModel = … | LanguageModelV4 | …`, so `streamText({ model })` accepts it. `.chat()` returns `LanguageModelV4` directly. Both model-id params accept arbitrary strings because each union ends `| (string & {})`, so `model: string` from config type-checks.

## Post-fix verification (executed in the author session)

- `npx vitest run src/lib/backend-adapters.test.ts` → 1 file / 11 tests passed.
- `npm run test` → **130 files / 1287 tests passed**.
- `npm run lint` → **30 problems, 0 errors** (all pre-existing warnings).
- `npm run build` → exit 0, TypeScript clean, all routes generated; `.next/standalone` removed.
- `python3 scripts/check_frontend_canon.py` → clean.
- `python3 scripts/check_doc_links.py` → OK (418 markdown files).

## Could not verify (by the reviewer)

Test/lint/build results were not executed by the reviewer (no shell tool); its type-chain and compile reasoning is static, and test non-vacuity was argued from source rather than observed red.
