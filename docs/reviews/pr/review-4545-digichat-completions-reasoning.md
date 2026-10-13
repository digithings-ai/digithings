# In-session review — PR #4545 (digichat openai-compatible reasoning)

- **Subject:** PR #4545, `task/4544-digichat-completions-reasoning` → `module/digichat`
- **Issue:** #4544
- **Reviewed revision:** `37a6cc23f` (fixes in `3594ca4e0`)
- **Reviewer:** independent fresh-context read-only subagent (`general`, delegation
  `eager-coral-fox`, 2026-09-23T06:08:13Z → 06:11:04Z). The author session did not
  review its own work. The reviewer had **no shell tool**, so it could not run
  `tsc`/`vitest`/`npm run build`; its type and non-vacuity conclusions are static.
- **Verdict:** APPROVE WITH NITS
- **Severity counts:** blocker 0 · major 0 · minor 1 · nit 2

## The claim under review

The `openai-completions` backend declared `capabilities.reasoning: true`, but was
resolved through `@ai-sdk/openai`'s product client, which parses only OpenAI-native
reasoning fields and drops the `reasoning_content` field OpenAI-compatible vendors
emit — so reasoning was silently lost for xAI / DeepSeek / Groq / Mistral /
Together / Fireworks / OpenRouter / Perplexity / GLM / LiteLLM.

## Findings

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| 1 | minor | The swap silently stops requesting stream usage. `@ai-sdk/openai-compatible` only sends `stream_options: { include_usage: true }` when `includeUsage` is set (`openai-compatible-chat-language-model.ts:445-447`), whereas `@ai-sdk/openai`'s chat path always did (`openai-chat-language-model.ts:486-487`). Invisible today (nothing consumes usage) but a real change in upstream request shape. | **Fixed** — `includeUsage: true` passed to `createOpenAICompatible` in `providers.ts`, pinned in `providers.test.ts`. Confirmed `includeUsage?: boolean` is on the provider settings type (`@ai-sdk/openai-compatible/dist/index.d.ts:354`, "Include usage information in streaming responses"). |
| 2 | nit | `max_tokens` vs `max_completion_tokens`: the compatible model sends `max_tokens` (`openai-compatible-chat-language-model.ts:275`) while `@ai-sdk/openai` translates to `max_completion_tokens` for reasoning models (`openai-chat-language-model.ts:314-319`). | **Accepted, no action** — `max_tokens` is the correct wire field for a generic compatible vendor, and real OpenAI never emitted `reasoning_content` on Chat Completions anyway, so nothing is lost for the vendors this arm targets. |
| 3 | nit | Out of scope: `lib/byok-openrouter.ts:23` still builds its provider with `createOpenAI` (`name: "openrouter-byok"`), so BYOK-OpenRouter reasoning is dropped for the same reason. | **Deferred** — `createOpenRouterByokProvider` has no caller in `src/` today, so nothing is broken. Recorded as a follow-up in `docs/architecture/digichat-config-program-plan.md`. |

## Verified clean (A–H)

- **(A) The two dists really do differ on `reasoning_content` — TRUE.**
  `@ai-sdk/openai-compatible` has 7 references and actually parses them
  (`openai-compatible-chat-language-model.ts:368-375` non-stream
  `choice.message.reasoning_content ?? choice.message.reasoning` →
  `content.push({ type: "reasoning", text })`; `:671-674` stream
  `delta.reasoning_content ?? delta.reasoning` → `enqueueReasoningDelta`;
  schemas at `:856,898`). `@ai-sdk/openai` has **zero** references to
  `reasoning_content` anywhere in `src/` or `dist/` — only `reasoning_tokens`
  usage accounting and `reasoningEffort` request params.
- **(B) The new arm is correct.** `createOpenAICompatible` exists in the installed
  `3.0.53` (`dist/index.d.ts:384`) with `baseURL` / `name` / `apiKey` in its
  settings; the provider exposes `chatModel(modelId): LanguageModelV4`
  (`openai-compatible-provider.ts:35`, wired `:199`), which is assignable to
  `ai`'s `LanguageModel`. `.chatModel()` is the **right** accessor — the provider
  has no `.chat()`, so `.chat()` would be a TS2339 compile error.
- **(C) `openai-responses` unchanged** (`providers.ts:59-70`): still
  `@ai-sdk/openai` + `.responses()`, which exists (`openai-provider.ts:69`) and is
  the only provider exposing it; the Responses wire format is OpenAI-native.
- **(D) `anthropic` / `google-vertex` arms untouched** by the diff.
- **(E) The switch is still exhaustive** over `AiSdkBackendConfig`'s four members,
  one arm each, under `strict: true` — a missing arm would be TS2366.
- **(F) Credential path unchanged.** `readBackendApiKey` /
  `BackendCredentialError` untouched; key read only from
  `process.env[apiKeyEnv]?.trim()`, never logged. `toDigichatClientConfig` still
  projects only `backendType` (`client-projection.ts:239`); no `baseUrl` /
  `apiKeyEnv` / `model` reaches the browser. The 502 path names the env var,
  never its value.
- **(G) Dependency/lock clean.** `@ai-sdk/openai-compatible@^3.0.53` declared and
  installed; the lock holds exactly **one** `@ai-sdk/provider` (4.0.17) and
  **one** `ai` (7.0.111); nested `@ai-sdk` dirs under both provider packages are
  empty; all four `libc` selectors present with correct values
  (`oxide-linux-x64-gnu` glibc, `-musl` musl, `unrs/resolver-binding-linux-x64-gnu`
  glibc, `-musl` musl). The PR's lock diff is a single added root-dependency line.
- **(H) Tests real and non-vacuous.** The new test asserts
  `createOpenAICompatible` called with the right args (now including
  `includeUsage: true`), `chatModel` called with the model, and `createOpenAI`
  **not** called; the `vi.hoisted` + `vi.mock` wiring intercepts the import.
  Reverting `providers.ts` to `createOpenAI().chat()` fails it. **Caveat:** the
  tests mock the provider, so they verify wiring only — they do not exercise real
  vendor `reasoning_content` behaviour.

## Could not verify

- test/lint/build results (no shell tool) — the author session ran them:
  `npm run test` 130 files / 1300 tests, `npm run lint` 30 problems 0 errors,
  `npm run build` type-checks clean, canon guard clean, doc-check OK (418 files).
- Runtime vendor behaviour (real xAI/DeepSeek/Groq streams) — impossible from
  static files, and the tests mock the provider.
- Whether `toUIMessageStream`'s default `sendReasoning` emits reasoning to the UI
  (`stream.ts` passes no option) — read from memory, not from the installed `ai`
  source.

## Post-fix verification (at `3594ca4e0`)

- `npx vitest run src/lib/adapters/ai-sdk/providers.test.ts` → 1 file / 6 tests passed.
- `npm run test` → 130 files / 1300 tests passed.
- `npm run lint` → 30 problems, 0 errors.
- `npm run build` → type-checks clean (route table printed), then `rm -rf .next/standalone`.
- `python3 scripts/check_frontend_canon.py` → clean.
- `python3 scripts/check_doc_links.py` → OK (418 markdown files scanned).
