# In-session review — backend adapter registry (Phase 5a)

| | |
|---|---|
| **Subject** | PR #4527 — `refactor(digichat): resolve the chat backend through an adapter registry` |
| **Branch** | `task/4522-digichat-backend-registry` → `module/digichat` |
| **Tracking issue** | #4522 |
| **Reviewed revision** | `3289a11c5` (fixes in `c9e063728`) |
| **Reviewer** | independent fresh-context read-only subagent (`general`, delegation `calm-indigo-badger`, 2026-09-22T23:32:06Z → 23:34:18Z). The author session did not review its own work. |
| **Verdict** | **APPROVE WITH NITS** — 0 blocker / 0 major / 1 minor / 3 nit |

## Correction to the review brief

The brief asserted that the corpus header condition previously read
`embedConfig?.backend.type`. That is **wrong**: the PR base (`19ffbb5a3`)
already had `if (backend?.type === "digigraph")` with the hoist
`const backend = embedConfig?.backend ?? dep?.backend;` in place (Phase 2b,
#4512). The new `if (adapter.capabilities.corpus && isDigigraphConfig(backend))`
is therefore **behaviour-identical — there is no widening**. Corroborated by the
pre-existing test `route.test.ts:1503` ("forwards the digigraph corpus index and
vault prefix on a session request"), which already asserted the session path
carries `X-Digi-Corpus-Index`.

## Findings and resolutions

| # | Sev | Finding | Resolution |
|---|---|---|---|
| MINOR-1 | minor | `backend-adapters.test.ts:82` guarded only `/backend\??\.type\s*===/`. A re-introduced dispatch as `backend.type == "digigraph"`, `backend?.type !== "digigraph"` or `switch (backend.type)` would pass while still hard-coding the backend in the handler. It also scanned comments, so a future comment containing the literal `backend.type ===` would fail the guard spuriously. | **Fixed.** The route source is read with `.replace(/\/\/.*$/gm, "")` (comments stripped) and the guard broadened to `/backend\??\.type\s*(===|!==|==|!=)|switch\s*\(\s*backend\??\.type/`. |
| NIT-1 | nit | "Pins exhaustiveness" was enforced by the `Record<BackendType, BackendAdapter>` **type**, not the test; the test only pins the key set. | **Fixed.** Comment above the test states the split; the plan doc wording corrected the same way. |
| NIT-2 | nit | Most capability flags are documentation-only in 5a. Only `protocol` (`route.ts:367`) and `capabilities.corpus` (`route.ts:455`) are read; the foundry path's immunity to the MCP/web-search blocks comes from the early return at `route.ts:391`, not from those flags. | **Fixed.** The `backend-adapters.ts` module docstring now says only `protocol`/`corpus` are load-bearing in 5a and the rest are declared for 5b/5c and asserted by the parity test. |
| NIT-3 | nit | `isDigigraphConfig`/`isFoundryConfig` narrow on `type` only while promising the full shape (`route.ts:372` then reads `foundryBackend.projectEndpoint`). | **Fixed (documented).** Both guards now carry a comment that the rest of the shape is guaranteed by the Zod schema (`BackendSchema`) and the tenant validator, which run before the handler sees a config. Not a regression — the pre-change inline `if (backend?.type === "foundry")` had the identical shape. |
| FOLLOW-UP | — | A second `backend.type` dispatch site remains in the `DIGICHAT_EMBED_TENANTS` validator: `apps/digichat/src/lib/embed-tenants.ts:231,251,269` (`if (backend?.type === "digigraph") … else if (backend?.type === "foundry") … throw`). Correctly out of 5a's chat-route scope. | **Recorded** in the program plan as a 5b/5c follow-up. |

## Verified clean (with evidence)

- **A. Registry covers the whole union; the union has exactly two members.** `BackendSchema` is `z.discriminatedUnion("type", [DigigraphBackendSchema, FoundryBackendSchema])` (`schema.ts:247-250`); `BackendType = BackendConfig["type"]`; `BACKEND_ADAPTERS` is a `Record<BackendType, BackendAdapter>` with both keys.
- **B. Every capability flag matches today's code.** digigraph `corpus:true` → `route.ts:455-463`; `mcp:true` → `X-Digi-Mcp-Servers`; `webSearch:true` → the web-search gate; `conversationContinuity:false` (continuity keys off `X-Session-Id`; `externalConversation` feeds only the run-lock key and the foundry call). foundry `conversationContinuity:true` → `conversationId: externalConversation`; `webSearch/mcp/corpus:false` because the foundry branch returns at `route.ts:391` before all three blocks; `reasoningSummary:false` matching `foundry/stream.ts`.
- **C. The foundry condition is behaviour-identical.** `adapter` derives solely from `backend?.type`, and `foundry-responses` maps only to the foundry entry, so `protocol === "foundry-responses"` ⇔ `backend.type === "foundry"` ⇔ `isFoundryConfig(backend)`. No fall-through introduced.
- **E. `backendAdapterFor(undefined)` preserves the no-backend path.** `DEFAULT_BACKEND_TYPE = "digigraph"`; the corpus block is skipped because `isDigigraphConfig(undefined)` is false; the foundry branch is skipped.
- **F. No `backend.type === …` comparison remains in `route.ts`.** Only the comment at `:199` and the lookup argument at `:200`.
- **G. The tests are non-vacuous.** The guard matches the pre-change `if (backend?.type === "foundry") {`; the registry assertions fail if any asserted flag flips; the parity invariant loops all types asserting `reasoning`/`toolCalls`/`sources`; guard tests cover both directions plus `undefined`.
- **H. Guards are sound-enough; `Extract` resolves.** `Extract<BackendConfig, {type:"foundry"}>` yields the foundry member, not `never`.
- **Server-safety / BFF.** `backend-adapters.ts` has no `"use client"`, no `window`/`document`/`process.env`, its only import is a type-only `DigichatDeployment` (erased at compile time). The registry carries no URL/token/credential, only enum flags; the client projection exposes only the `backendType` discriminator, never `projectEndpoint`.
- **Docs accuracy.** The plan doc's Phase 5a "Done (issue #4522)" text matches the code apart from the NIT-1 wording, now corrected.

## Could not verify (stated plainly by the reviewer)

- Test / lint / build results — the reviewer had no shell tool.
- `noUncheckedIndexedAccess` by compilation (the flag is absent from `apps/digichat/tsconfig.json`, so `BACKEND_ADAPTERS[...]` types non-optional — read from the config, not by running `tsc`).
- Regex behaviour by execution (hand-reasoned).
- The "no new dependency" claim beyond the diff (no `package.json`/lockfile change in it, which is consistent, but the lockfile was not audited).

## Post-fix verification (author session)

- `apps/digichat` `npx vitest run src/lib/backend-adapters.test.ts` → 1 file / 8 tests passed.
- `apps/digichat` `npm run test` → **127 files / 1264 tests passed**.
- `apps/digichat` `npm run lint` → **30 problems, 0 errors** (all pre-existing warnings).
- `apps/digichat` `npm run build` → TypeScript clean, all routes generated (`.next/standalone` removed afterwards).
- `python3 scripts/check_frontend_canon.py` → **clean**.
- `python3 scripts/check_doc_links.py` → **OK (418 markdown files scanned)**.
