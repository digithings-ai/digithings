# Review — #4552 / PR #4553: provider built-in web search + citations

**Reviewer:** independent fresh-context subagent (`lively-golden-falcon`), did not write this code.
**Subject:** commit `7eba91ba` on `task/4552-digichat-provider-search`, PR **#4553** into `module/digichat`.
**Issue:** #4552.
**Verdict:** APPROVE WITH NITS — **0 blocker / 0 major / 2 minor / 2 nit**.
**Tooling caveat stated by the reviewer:** no shell tool in its environment. Static verification only — on-disk reads, installed `node_modules` `.d.ts`, GitHub API (`get_diff`, `get_commit`, `get_check_runs`), and the upstream TS PR for the one language-semantics question. It could not run `tsc`, `vitest`, or `eslint`; the author session ran those and reports them below.

---

## Verified clean (claims A–H)

| # | Claim | Result |
|---|-------|--------|
| A | `toUIMessageStream` receives `sendSources: true` / `sendReasoning: true`; option names correct; `sendSources` defaults false | ✅ `ai@7.0.111` `UIMessageStreamOptions` at `ai/dist/index.d.ts:2706`, defaults documented at `:2732-2741`; `toUIMessageStream` at `:6327`. `stream.ts:69-78` |
| B | `resolveAiSdkSearchTools` returns the right tool per arm; factories exist; `ToolSet`-assignable | ✅ factories at `openai/dist/index.d.ts:1283`, `anthropic/dist/index.d.ts:1283`, `google-vertex/dist/index.d.ts:89`; `providers.ts:104-135`. Assignability verified **structurally** (`ToolSet` at `@ai-sdk/provider-utils/dist/index.d.ts:2712`, `ProviderExecutedTool` at `:2128`) — not by compiler |
| C | Gate computed once, hoisted; `webSearch` passed; header written exactly once; no `backend.type ===` introduced | ✅ `route.ts:448-454`, `:467`, `:590-594`; `grep webSearch` returns only `447/452/453/454/467/592` |
| D | Session-path gate widening is behaviour-preserving for embeds | ✅ embed arm algebraically identical (`embedConfig.webSearch === true`); session arm a strict superset (`env === "1"` retained as `||`). Cannot disable where env was sole enabler |
| E | The UI switch really sees `type: "source"` | ✅ `@assistant-ui/ai-sdk/src/converters/convertMessage.ts:334-348` (`source-url`) and `:359-374` (`source-document`) both map to `{ type: "source", sourceType }`; `groupParts.ts:95` leaves it ungrouped; `thread.aui.tsx:978-979` |
| F | Union narrowing correct; external link safe | ✅ `SourceMessagePart` is a discriminated union (`core/src/types/message.ts:33-53`), document arm has `readonly url?: undefined`. Aliased-discriminant narrowing (TS 4.4, PR #44730) applies through the destructured `sourceType`. `target="_blank"` + `rel="noreferrer noopener"` at `source.tsx:45-49` |
| G | Tests real and non-vacuous | ✅ removing `sendSources: true` fails `stream.test.ts` test 1; removing the tools spread fails test 2; `providers.test.ts` fails on 3 of 4 if the fn returned `undefined`; `source.test.tsx` mounts and asserts DOM; `route.test.ts` fails if `webSearch` not passed. Casts weaken *type* coverage only (Nit 1), not assertion strength |
| H | Docs table matches code | ✅ for the 4 AI-SDK arms. ⚠️ Minor 1 — one attribution is wrong |

CI (`get_check_runs`): `web / lint`, `digichat / test`, `dashboard / test`, `gate` all `success`. `web / lint` includes `Typecheck design-reference`, which pulls `@digithings/ui` sources (`test-web.yml:129-132`) — so UI type errors would redden it, and it is green.

## Hunt items — clean

1. **Secret to a config-controlled host / inline credential** — none. `resolveAiSdkSearchTools` mirrors `resolveAiSdkModel`: the credential is read from the env var the config *names* (`readBackendApiKey`, `providers.ts:32-38`), never from config. Nothing credential-bearing is returned to the browser. Clean.
2. **Regressions to digigraph / foundry / non-AI-SDK** — branch order unchanged (`foundry` → non-AI-SDK → `coreMessages` → gate → AI-SDK → BYOK → upstream → digigraph); `runLock.release()` untouched; the only digigraph change is the intentional gate widening in D. Clean.
3. **`sendSources` vs `activityDetail`** — `activityDetail` (`route.ts:211`) is passed only to `foundry` (`:387`), non-AI-SDK (`:416`) and the digigraph trace adapter (`:623`); the AI-SDK mapper (`:460-475`) never applied it, before or after this PR, so nothing is bypassed. Provider citations on the AI-SDK path are answer content, not activity. Defensible; worth a conscious decision for embeds.
4. **Provider tool on non-tool models** — `tools` only passed when the client opted in and the tenant allowed it; `toolChoice` defaults to `auto`, `stopWhen` to one step. Low risk.
5. **Type-checks but misbehaves** — nothing beyond Minors 2/3.

## Findings

### Minor 1 — doc credits `sendSources` with the digigraph/foundry source recovery (wrong cause)

`docs/architecture/digichat-config-program-plan.md` says `sendSources: true` fixed "provider grounding **and the digigraph/foundry `retrieve` documents that were already on the wire**".

**Confirmed independently by the author session:** `grep toUIMessageStream apps/digichat/src` returns only `ai-sdk/stream.ts:70` and `route.ts:643`. The digigraph/foundry adapters never touch `toUIMessageStream` — they emit `source-url` / `source-document` straight from their own SSE writer (`lib/ui-stream-parts.ts:239-261` `writeSource`, consumed by `digithings/stream.ts`, `foundry/stream.ts`, `ag-ui/stream.ts`, `langgraph/stream.ts`, `a2a/stream.ts`). Those documents were dropped by the **UI** part switch, fixed by new point 3 (`case "source"`), not by `sendSources`.

**Resolution:** corrected in the docs — point 1 now credits `sendSources` with AI-SDK provider citations only; point 3 credits the UI case with the digigraph/foundry/documents path.

### Minor 2 — second `toUIMessageStream` call site omits `sendSources`

`apps/digichat/src/app/api/chat/route.ts:641-646` (digigraph path when the trace UI is off, i.e. `DIGICHAT_TRACE_UI=0` or `x-digichat-trace: 0`):
```ts
    createUIMessageStreamResponse({
      stream: toUIMessageStream({ stream: result.stream }),
      headers: responseHeaders,
    }),
```
No `sendSources: true`, so the doc's blanket "now runs with" is not true here. If the custom digigraph provider surfaces `source` parts on this path they are still stripped. The reviewer could not verify whether it can.

**Resolution:** fixed — `sendSources: true, sendReasoning: true` added for parity, matching `ai-sdk/stream.ts`.

### Minor 3 — `ThreadSource` renders a provider-controlled URL with no scheme allowlist

`packages/ui/src/components/chat/gallery-thread/source.tsx:43-54` puts `props.url` straight into `href`. That URL is model/provider-controlled (OpenAI / Anthropic / Vertex citations) — `writeSource` guards with `isHttpUrl` for digigraph docs, but AI-SDK provider annotations are not re-checked. A non-`http(s)` scheme (`javascript:`, `data:`) would render as a clickable link; React's `javascript:` handling is version-dependent. `rel="noreferrer noopener"` is correct but does not cover the scheme.

**Confirmed independently by the author session:** this repo already has the guard pattern, twice — `apps/digichat/src/lib/ui-stream-parts.ts:64` `isHttpUrl` and `packages/ui/src/components/chat/ChatMarkdownSource.tsx:106-109` `safeHref` ("Only http(s) links survive; anything else (javascript:, data:) renders as text"), with tests asserting `javascript:` never survives.

**Resolution:** fixed — a local `isHttpUrl` guard in `source.tsx`; a non-http(s) URL renders as a text row (`data-slot="aui_source-url"` retained but no `href`), matching `ChatMarkdownSource`'s established contract. Test added.

### Nit 1 — casts/mocks weaken type coverage
`source.test.tsx` uses `as unknown as SourceMessagePartProps`; `stream.test.ts` / `providers.test.ts` fully `vi.mock` the provider packages, so a wrong `.tools` method name or prop-shape drift would not be caught by them — only by the reviewer's manual `.d.ts` reading (B).
**Resolution:** accepted. The real factory names are pinned by `providers.test.ts` asserting the exact `.tools` member is invoked, and the CI typecheck would catch a renamed method; a duplicate compile-time assertion would add little.

### Nit 2 — doc "ag-ui/langgraph normalizers can emit `retrieve` spans"
Hedged with "can" and plausible given the shared `writeSource`, but not verified per adapter.
**Resolution:** fixed — the doc now says the ag-ui/langgraph normalizers *share* `writeSource`, so they emit source parts when the backend supplies documents, and cites `ui-stream-parts.ts`.

## Author-session re-verification (commands run)

```
rg -n "toUIMessageStream" apps/digichat/src          → ai-sdk/stream.ts:70, route.ts:643 only
sed -n '635,655p' apps/digichat/src/app/api/chat/route.ts → confirms Minor 2
rg -n "isHttpUrl" apps/digichat/src packages/ui/src  → ui-stream-parts.ts:64,245
rg -n "javascript:" packages/ui/src                  → ChatMarkdownSource safeHref + tests
```
