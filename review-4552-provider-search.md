# Review — #4552 provider built-in web search and citations

**Reviewer:** `lively-golden-falcon` — independent, fresh-context subagent (did not write the code).
**Subject:** PR #4553, branch `task/4552-digichat-provider-search`, commit `7eba91ba0`, base `module/digichat`.
**Issue:** #4552 — digichat: surface provider built-in web search and citations (sources) in the chat.
**Verdict:** APPROVE WITH NITS
**Severity:** 0 blocker / 0 major / 2 minor / 2 nit
**Tooling disclosure:** the reviewer had no shell tool. Verification was static: on-disk reads, installed `node_modules` declarations, and the GitHub API (`get_diff`, `get_commit`, `get_check_runs`). It stated explicitly where it could not verify.

---

## Verified clean

### A — `sendSources` / `sendReasoning` names and defaults
`apps/digichat/src/lib/adapters/ai-sdk/stream.ts:69-78` passes `sendSources: true, sendReasoning: true`.
`ai@7.0.111`, `ai/dist/index.d.ts`: options type `UIMessageStreamOptions` at :2706; defaults documented at :2732-2741 —

```ts
    /**
     * Send reasoning parts to the client.
     * Default to true.
     */
    sendReasoning?: boolean;
    /**
     * Send source parts to the client.
     * Default to false.
     */
    sendSources?: boolean;
```

`toUIMessageStream` at :6327 accepts `{ stream } & UIMessageStreamOptions<UI_MESSAGE>`. Names and call shape correct; `sendSources` genuinely defaults to **false**.

### B — `resolveAiSdkSearchTools` factories
`apps/digichat/src/lib/adapters/ai-sdk/providers.ts:104-135` matches the claim arm for arm. Factory names verified against the installed declarations:

- `openai-responses` → `createOpenAI({baseURL,apiKey,name}).tools.webSearch()` — `openaiTools.webSearch` at `@ai-sdk/openai/dist/index.d.ts:1283`; `OpenAIProvider.tools: typeof openaiTools` at :1658; `createOpenAI` at :1699.
- `anthropic` → `createAnthropic({apiKey,name}).tools.webSearch_20250305()` — `anthropicTools.webSearch_20250305` at `@ai-sdk/anthropic/dist/index.d.ts:1283`; `AnthropicProvider.tools` at :1467; `createAnthropic` at :1506.
- `google-vertex` → `createVertex({project,location}).tools.googleSearch({})` — `googleVertexTools.googleSearch` at `@ai-sdk/google-vertex/dist/index.d.ts:89`; `GoogleVertexProvider.tools` at :147; `createVertex` alias at :304; settings at :187-191.
- `openai-completions` → `undefined` (providers.ts:108-109).

Assignability to `ToolSet` verified **structurally only** (`@ai-sdk/provider-utils/dist/index.d.ts:2712` `type ToolSet = Record<...>`; `ProviderExecutedTool` at :2128; `Tool` union at :2155). The factories return a `ProviderExecutedTool`, a member of the `Tool` union, and the `Pick`ed members are optional, so `{ web_search: … }` is assignable. **Not compiler-verified** — no shell.

### C — Route gate hoisted once, header written once
`route.ts:448-454` computes `clientWantsWeb` / `tenantAllowsWeb` / `webSearchEnabled` once; `:467` passes `webSearch: webSearchEnabled` to `createAiSdkStreamResponse`; `:590-594` writes `X-Digi-Enable-Web-Search` under the same variable, exactly once. `grep webSearch route.ts` returns only lines 447/452/453/454/467/592. No `backend.type ===` comparison added; branch ordering and `runLock.release()` untouched.

### D — Session-path gate: behaviour-preserving for embeds, widening only for sessions
Old: `embedConfig?.webSearch === true || (!embedConfig && env === "1")`.
New (`route.ts:451-453`): `embedConfig ? embedConfig.webSearch === true : dep?.gate.webSearch === true || env === "1"`.

- Embed tenant (truthy `embedConfig`): old reduces to `embedConfig.webSearch === true || false`; new is exactly `embedConfig.webSearch === true`. **Identical.**
- Session path (falsy): old = `env === "1"`; new = `env === "1" || dep?.gate.webSearch === true`. **Strict superset** — the env term is retained as `||`, so it cannot disable where env was the sole enabler. It can enable only when the deployment sets `gate.webSearch: true` **and** the client sends `x-digi-enable-web-search`, which is the intended opt-in widening.
- Residual, pre-existing (not a regression): `dep.gate.webSearch === false` still loses to `DIGICHAT_WEB_SEARCH=1`.

### E — Part type reaching the switch really is `"source"`
`@assistant-ui/ai-sdk` `src/converters/convertMessage.ts:334-348` maps `source-url` → `{ type: "source", sourceType: "url", id, url, title? }`; `:359-374` maps `source-document` → `{ type: "source", sourceType: "document", id, title, mediaType, filename? }`. `groupParts.ts:95` returns `lookup[part.type] ?? []` and `thread.aui.tsx:893-897` maps only `reasoning` / `tool-call` / `standalone-tool-call`, so `source` stays an individual part leaf. `thread.aui.tsx:978-979` adds `case "source": return <SourceComponent {...part} />;`; default `Source: SourceComponent = ThreadSource` at :872; slot type at :102. The raw wire names never reach the switch.

### F — Union narrowing correct; external link safe
`SourceMessagePart` (`@assistant-ui/core/src/types/message.ts:33-53`) is a discriminated union whose document member carries `readonly url?: undefined` and only it has `filename`. `source.tsx` uses the destructured `sourceType` as the discriminant. The reviewer initially suspected TS2339 on `props.filename`, then correctly refuted itself: aliased-discriminant analysis (TypeScript PR #44730, TS 4.4) narrows the original object through a destructured discriminant — its own example `f3` does `const { kind } = obj; if (kind === 'foo') obj.foo; // Ok`. `props` is an unassigned parameter and `sourceType` is `readonly`, so narrowing applies. Corroborated by the green `web / lint` job, whose `Typecheck design-reference` step pulls `@digithings/ui` sources (`test-web.yml:129-132`). Links carry `target="_blank"` + `rel="noreferrer noopener"`; documents render as a `<span>`.

### G — Tests are real and non-vacuous
1. `stream.test.ts` — removing `sendSources: true` fails test 1; removing the `...(tools ? { tools } : {})` spread fails test 2. Not vacuous as a file.
2. `providers.test.ts` — if the function returned `undefined` for every arm, only the `openai-completions` case passes; the other three assert exact factory args and `toEqual`. Non-vacuous.
3. `source.test.tsx` — genuinely mounts via `createRoot` + `act` and asserts DOM. The `as unknown as SourceMessagePartProps` cast weakens type coverage only, not assertion strength.
4. `route.test.ts:1620-1649` — asserts `webSearch: true` with the header and `false` without; would fail if `webSearch` were not passed. Proves the gate reaches the mapper.

### H — Docs table
Per-backend built-in search matches the code for the four AI-SDK arms. `ag-ui` / `langgraph` emitting `retrieve` spans is hedged and plausible given the shared `writeSource`. One attribution was wrong — see Minor 1.

### Hunt items — all clean
1. **No secret to a config-controlled host.** `resolveAiSdkSearchTools` mirrors `resolveAiSdkModel`: the credential is read from the env var the config *names* (`readBackendApiKey`, `providers.ts:32-38`), never from config; `baseURL` is config-controlled exactly as before; Anthropic uses its default base URL; Vertex uses ADC. Nothing credential-bearing reaches the browser.
2. **No digigraph / foundry / non-AI-SDK regression.** Branch order unchanged (`foundry` → non-AI-SDK → `coreMessages` → gate → AI-SDK → BYOK → upstream → digigraph); the hoisted gate is consumed only by the digigraph header, still once; `runLock.release()` in each catch is untouched.
3. **`sendSources` bypasses no `activityDetail` gate.** `activityDetail` (`route.ts:211`) is passed only to `foundry` (:387), non-AI-SDK (:416), and the digigraph trace adapter (:623); the AI-SDK mapper (:460-475) never applied it, before or after. Digigraph's own source emission *is* gated (`mapDigigraphTraceToSpans(payload, opts.activityDetail)`, `digithings/stream.ts:413`). Provider citations are answer content, not activity.
4. **Provider tool on non-tool models.** `tools` is passed only on opt-in; `openai-completions` gets none; `toolChoice` defaults `auto` and `stopWhen` to one step, which suits provider-executed search. Low risk.
5. **Nothing type-checks-but-misbehaves** beyond Minors 2/3.

**CI at review time:** `web / lint`, `digichat / test`, `dashboard / test`, `gate` all `success`.

---

## Findings and resolutions

### Minor 1 — Doc credited `sendSources` with recovering the digigraph/foundry documents (wrong cause)
The plan's new point 1 claimed `sendSources: true` recovered "provider grounding **and the digigraph/foundry `retrieve` documents that were already on the wire**".
The digigraph/foundry adapters never go through `toUIMessageStream` — they emit source chunks from their own SSE writer (`lib/ui-stream-parts.ts:239-261` `writeSource`), consumed by `digithings/stream.ts`, `foundry/stream.ts`, `ag-ui/stream.ts`, `langgraph/stream.ts`, `a2a/stream.ts`. `grep toUIMessageStream apps/digichat/src` returns only `ai-sdk/stream.ts:70` and `route.ts:643`. Those documents were dropped by the **UI** part switch, fixed by point 3.
**Resolution — FIXED.** `docs/architecture/digichat-config-program-plan.md:408` now scopes point 1 to `toUIMessageStream` on **both** call sites, and :425 states explicitly that the digigraph/foundry documents "were dropped by the message part switch's `default`, not by `sendSources`".

### Minor 2 — Second `toUIMessageStream` call site omitted `sendSources`
`route.ts:641-646` (digigraph path when the trace UI is off: `DIGICHAT_TRACE_UI=0` or `x-digichat-trace: 0`) called `toUIMessageStream({ stream: result.stream })`, so the doc's blanket claim was not true there and source parts on that path were still stripped.
**Resolution — FIXED.** Now `toUIMessageStream({ stream: result.stream, sendSources: true, sendReasoning: true })` (`route.ts:643-647`), matching `ai-sdk/stream.ts`.

### Minor 3 — `ThreadSource` linked a provider-controlled URL with no scheme allowlist
`source.tsx` put `props.url` straight into `href`; a `javascript:` / `data:` citation would render as a clickable link. The repo already had the guard pattern twice: `apps/digichat/src/lib/ui-stream-parts.ts:64` `isHttpUrl`, and `packages/ui/src/components/chat/ChatMarkdownSource.tsx:106-109` `safeHref`.
**Resolution — FIXED.** `source.tsx:26` defines a local `isHttpUrl`, `:35` computes `const href = isUrl && isHttpUrl(props.url) ? props.url : undefined;`, and the link branch is `if (href)` (`:52`) — non-http(s) renders as the text row `data-slot="aui-source-document"`, with no `<a>` and no `aui_source-url`, matching `ChatMarkdownSource`. A guard test was added via `it.each(["javascript:alert(1)", "data:text/html,<script>x</script>", ""])` asserting `host.querySelector("a")` is null, `[data-slot="aui-source-url"]` is null, and the title text still renders. First run failed with `expected undefined to be null` because the assertion used `null?.getAttribute(...)`; the assertion was corrected (the implementation was right), then 7/7 passed.

### Nit 1 — casts / mocks weaken type coverage (ACCEPTED)
`source.test.tsx` casts through `as unknown as SourceMessagePartProps`; `stream.test.ts` / `providers.test.ts` fully `vi.mock` the provider packages. Accepted: the real factory member names are pinned by `providers.test.ts` asserting the exact `.tools` member is invoked, and CI typechecks `@digithings/ui` sources.

### Nit 2 — doc pointer for the `retrieve`-span claim (FIXED)
The `ag-ui` / `langgraph` table row now says those normalizers **share** `writeSource` (`lib/ui-stream-parts.ts`) and cites the file.

---

## Commands used by the author session to re-verify the findings

```bash
rg -n "isHttpUrl|href" packages/ui/src/components/chat/gallery-thread/source.tsx
rg -n "sendSources|case \"source\"|retrieve documents" docs/architecture/digichat-config-program-plan.md
rg -n "toUIMessageStream" apps/digichat/src
```

## Post-fix verification (author session)

```
apps/digichat   npx vitest run src/lib/adapters/ai-sdk/{providers,stream}.test.ts  2 files / 14 tests passed
apps/digichat   npx vitest run src/app/api/chat/route.test.ts                      1 file / 63 tests passed
packages/ui     npx vitest run src/components/chat/gallery-thread/source.test.tsx  1 file / 7 tests passed
apps/digichat   npm run test       133 files / 1331 tests passed
apps/digichat   npm run lint       30 problems, 0 errors (all pre-existing warnings)
apps/digichat   npm run build      type-checks clean
packages/ui     npm run test       63 files / 456 tests passed
repo root       python3 scripts/check_frontend_canon.py   frontend canon guard: clean
repo root       python3 scripts/check_doc_links.py        OK (418 markdown files scanned)
```
