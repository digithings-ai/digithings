# Review record — PR #4548, digichat non-AI-SDK backends (Phase 5c)

- **Subject:** PR #4548 (`task/4543-digichat-non-ai-sdk-backends` → `module/digichat`), issue #4543
- **Reviewed revision:** `43bd2e4af` (14 files, +1512/−1)
- **Reviewer:** independent fresh-context read-only subagent (`general`, delegation `gentle-indigo-raven`,
  2026-09-23T06:35:54Z → 06:39:03Z). The author session did not review its own work.
  The reviewer had **no shell tool**, so it reconstructed the diff from the GitHub API and read files
  on disk; it could not run test/lint/build.
- **Verdict:** REQUEST CHANGES — **1 blocker / 0 major / 3 minor / 5 nit**
- **Fixes:** `b74ad3b7f` (this commit set) on the same branch

## Findings and resolution

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| B1 | blocker | `iterateSse` split only on `"\n\n"`, so a CRLF (`\r\n\r\n`) stream matched no delimiter and yielded **zero** events — an empty answer with no error. CRLF is the SSE-spec-valid form and the default of `sse-starlette` (the Python stack A2A/AG-UI servers are built on); the dead `\r` strip showed CRLF support was intended but unreachable. | **Fixed.** `stream-utils.ts` now scans with `const SSE_DELIMITER = /\r?\n\r?\n/`. Added a CRLF fixture test (`langgraph mapper` → "reads a CRLF-delimited stream") built from the existing canned stream with `\n` → `\r\n`. |
| M1 | minor | Non-OK upstream paths returned without reading or cancelling `res.body` (langgraph, ag-ui, a2a), leaving sockets to GC; the digigraph adapter cancels explicitly. | **Fixed.** All three now `await res.body?.cancel().catch(() => {})` before returning, with a comment naming the digigraph precedent. |
| M2 | minor | A2A re-emitted cumulative artifact text: a `task` snapshot followed by `artifact-update`s (or an `append: false` resend) appended the full text each time, duplicating the answer. | **Fixed.** New `artifactDelta(artifact, emitted)` keyed by `artifactId` emits only the delta against what that artifact already contributed; used by both the `task` and `artifact-update` paths. Added a test asserting `"Part one."` appears exactly once across a cumulative resend. |
| M3 | minor | Error `data-status` rows (AG-UI `RUN_ERROR`, the three non-OK statuses) wrote raw upstream strings straight to the wire — uncapped and bypassing the disclosure gate every other span honours. | **Fixed.** New `writeFailureStatus(writer, ctx, label, activityDetail)` routes through `writeGatedSpan`, so the label is capped by `sanitizeActivitySpan` and gated by `applyActivityDetail` like every other span. All four sites use it. |
| N1 | nit | LangGraph used `tool_call_chunks` only to open a row; partial args were never accumulated, so a graph that streams chunks without settling `tool_calls` rendered tool rows with no input (asymmetric with AG-UI). | **Fixed.** `Consumer.toolArgs` accumulates chunk args; they are used as the input on `tool_calls` completion and on the `type:"tool"` result frame. The main langgraph test now asserts the accumulated `coffee` arg reaches the stream. |
| N2 | nit | `sources: true` on `langgraph`/`ag-ui` is aspirational — no mapper emits `retrieve`/`documents` spans, so sources cannot render yet. | **Accepted.** Consistent with the already-documented "declared for the matrix, not wired yet" flags on the AI-SDK entries; recorded in the plan's Phase 5c capability caveat rather than flipped, so the parity matrix keeps one meaning. |
| N3 | nit | `non-ai-sdk.ts` imports `readBackendApiKey` from the AI-SDK provider module, coupling the non-AI-SDK path to `@ai-sdk/anthropic|google-vertex|openai` (transitively `google-auth-library`). | **Accepted, deferred.** No behaviour change — the route already imports that module, so nothing new is loaded. Moving it would edit `providers.ts`, which the already-merged #4545 also changed; the churn is not worth the conflict risk for a nit. |
| N4 | nit | The credential 502 omitted the `X-Digichat-Session` / `X-Request-Id` headers the streaming responses carry. | **Fixed.** The 502 now spreads `...opts.responseHeaders` alongside `content-type`. |
| N5 | nit | The plan doc claimed "every span still flows through `sanitizeActivitySpan` + `applyActivityDetail` + `writeStandardActivity`", which M3 falsified. | **Fixed.** Reworded to "every activity span … (via `writeGatedSpan` / `writeFailureStatus`)" with the error-row guarantee stated. |

## Verified clean (reviewer's A–H)

- **A — schemas.** `LangGraphBackendSchema` (`schema.ts:364`), `AgUiBackendSchema` (`:374`), `A2aBackendSchema` (`:383`)
  are `.strict()`; each URL is `HttpsBackendUrl` (`.url()` + `startsWith("https:")`); `apiKeyEnv` is
  `OptionalBackendApiKeyEnv.optional()` with `/^DIGICHAT_BACKEND_[A-Z0-9_]+$/`. `BackendSchema` is a
  nine-member `z.discriminatedUnion("type", …)`; the three new schemas are the only additions.
- **B — embed-tenants.** The union gained exactly three arms; `validateEntry` gained ONE combined branch
  (per-type URL field `apiUrl`/`url`/`baseUrl`, `new URL()` + `protocol !== "https:"`, `assistantId`
  required for langgraph, `validateApiKeyEnv` with the identical regex); the final `else` names all nine types.
- **C — registry.** Three entries with matching `protocol` and `auth: "env"`; `a2a` capabilities all false;
  `NON_AI_SDK_PROTOCOLS` holds exactly the three; `isNonAiSdkConfig` narrows on `type` only; `BackendProtocol`
  was **not** touched (the three names pre-existed).
- **D — route.** Branch gated on `NON_AI_SDK_PROTOCOLS.has(adapter.protocol) && isNonAiSdkConfig(backend)`,
  passes raw `messages`, releases the run lock on throw. Grep for `backend.type ===` in `route.ts`: no matches.
  The branch sits after foundry and before `convertToModelMessages`; its guard is false for every other
  protocol, so the six existing backends are byte-identical.
- **E — dispatcher.** Credential resolved once; on failure a 502 `backend_unavailable` naming the env var
  **name only** with no `fetch`; the `switch` is exhaustive over the three types.
- **F — stream-utils.** `writeGatedSpan` order is `sanitizeActivitySpan` → `applyActivityDetail` →
  `writeStandardActivity`; `createTextWriter.delta` closes open reasoning before `text-start`. (The `\r`
  aspect was the B1 blocker — now fixed.)
- **G — mappers.** LangGraph uses the array-tolerant `parseSseValue` + `Array.isArray`; AG-UI accumulates
  args in `toolArgs` and parses once at `TOOL_CALL_END`/`TOOL_CALL_RESULT`; A2A handles both
  `application/json` and SSE with `result`/`error` envelope keys. All three `finally` blocks close text and
  call `finishStandardActivity`.
- **H — tests.** Fixtures exercise reasoning, tool start/args/result and text per protocol; A2A asserts
  **no** `reasoning-delta`; the 502 test asserts status/error/env-name and that `fetch` was not called.

Hunty items resolved: no path inlines a credential (`apiKeyEnv` is only read via `readBackendApiKey` and
placed in the intended host's header; never logged, never in the 502 body; the prefix guard is enforced in
both parsers); no regression to the six existing backends; upstream `fetch` receives `opts.signal` and
`iterateSse` cancels its reader in `finally` (body abandonment was M1); all spans now route through the gate
(M3 was the sole exception); B1/M2/N1 were the type-checks-but-misbehaves class; the plan doc's shapes,
headers and methods match the code (the overstatement was N5).

## Could not verify (reviewer, no shell)

- The test/lint/typecheck results in the PR body (unverified by the reviewer; re-run by the author after the
  fixes — see below).
- Whether LangGraph Platform and the specific AG-UI server in scope emit `\n\n` or `\r\n` — the CRLF risk was
  confirmed from `sse-starlette`'s documented default and the adapters' own (pre-fix) code.
- Browser behaviour on a `data-status` "failed" row with no result text.

## Post-fix verification (author, from `apps/digichat/` unless noted)

- Targeted `npx vitest run src/lib/adapters/non-ai-sdk.test.ts src/lib/backend-adapters.test.ts` → 2 files / 24 tests passed.
- `npm run test` → **132 test files / 1322 tests passed** (was 1320; +2 from the CRLF and artifact-dedupe tests).
- `npm run lint` → **30 problems, 0 errors** (all pre-existing warnings).
- `npm run build` → **0 occurrences of "Failed to type check"**; `rm -rf .next/standalone` after (that dir breaks `make doc-check`).
- `npx tsc --noEmit -p tsconfig.json` → no errors in any adapter/registry file. Five test-file errors this PR
  had introduced were fixed alongside: four `mock.calls[0] as [string, RequestInit]` casts in
  `non-ai-sdk.test.ts` (now `as unknown as …`) and one malformed `{ type: "foundry" }` narrowing fixture in
  `backend-adapters.test.ts` (now a fully-shaped foundry config).
- From the REPO ROOT: `python3 scripts/check_frontend_canon.py` → `frontend canon guard: clean`;
  `python3 scripts/check_doc_links.py` → `check_doc_links: OK (418 markdown files scanned)`.
- Non-vacuousness spot-check: reverting `stream-utils.ts` to HEAD fails the new tests (2 failed / 7 passed),
  confirming the CRLF/delimiter change is what the fixtures exercise.
