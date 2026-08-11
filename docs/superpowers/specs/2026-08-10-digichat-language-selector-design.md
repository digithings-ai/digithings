# DigiChat language selector — design

- **Date:** 2026-08-10
- **Issue:** [#2103](https://github.com/digithings-ai/digithings/issues/2103)
- **Components:** `frontend/digichat`, `digigraph`

## Goal

Add a language dropdown to the DigiChat top bar so a visitor can pick which
language the assistant replies in. Prompt templates stay English everywhere;
the selection is threaded through as a short directive telling the model to
respond in the chosen language. Only outgoing (assistant) text is affected —
the UI chrome and the model's own tool-use/retrieval behavior are untouched.

The feature must work identically on both backend adapters DigiChat ships
today, which currently have **no shared prompt-assembly code**:

- The **digigraph** adapter (`frontend/digichat/src/lib/adapters/digithings/stream.ts`)
  — used by digithings.ai/chat and OCC (`digithings.ai/chat/occ`), both on the
  Profile A stack.
- The **Foundry** adapter (`frontend/digichat/src/lib/adapters/foundry/stream.ts`)
  — used by DataTap (Profile B), which calls Azure AI Foundry directly via
  `@azure/ai-projects` and holds conversation state in Foundry, not digigraph.

## Decisions

| Question | Decision |
|---|---|
| Who gets the selector? | Every deployment, **on by default**. `EmbedTenantConfig.showLanguageSelector` exists so a tenant can opt out (`false`); unset or `true` both mean "show it." |
| Language list | Curated, fixed: English, German, Italian, Spanish, French. Extendable later — not user-extensible now. |
| Default selection | Auto-detected from `navigator.language` on first render; falls back to English when the browser locale isn't in the curated list. |
| Persistence | Session-only. No `localStorage` — matches the BYOK key's session-only-memory precedent. Re-detects from the browser on every fresh load. |
| Scope of the directive | Only the assistant's outgoing text. Retrieval, tool names, citations, and the underlying research/system prompts stay in English. |

## Architecture — approaches considered

The core decision is *where* the language directive gets injected into the
model call. Three approaches were considered, evaluated against the digigraph
path (which does have a resolved `system_prompt` string per request):

| # | Approach | Verdict |
|---|---|---|
| **A** | **Dedicated per-request field, appended to whichever `system_prompt` is already resolved** (default or tenant override) | **Chosen.** Composes with any tenant's prompt without either side needing to know about the other. Mirrors the existing corpus-routing precedent (`digisearch_index`, `vault_path_prefix`) exactly. |
| B | Overload `research_system_prompt_override` — DigiChat sends the *whole* tenant prompt + language directive as one override string | Rejected. Forces the frontend to know and duplicate each tenant's system-prompt text, which today lives only server-side in `digiproject.yaml` / `DIGI_TENANT_CORPUS_MAP`. Breaks single-source-of-truth and would drift the moment either side changes independently. |
| C | Inject into the visible user message (via `chat_prompt.py`'s `messages_to_workflow_prompt`) | Rejected for digigraph. Pollutes chat history shown to the model as part of the dialogue, and would repeat awkwardly on every turn now that full multi-turn history is preserved (#2100). |

The Foundry adapter has **no system-prompt slot at all** in its current call
shape — `openai.responses.create({ conversation, input: message, stream: true }, { body: { agent_reference } })`
sends only the last user message text; the agent's instructions live in the
Foundry portal's agent definition, outside this repo. So for Foundry, the
message-injection approach (C above) is not a workaround, it's the **only
available seam** — see "Foundry data flow" below.

## Data flow — digigraph backend (digithings, OCC)

```
Dropdown (chat-shell.tsx) → React state (session-only, seeded from navigator.language)
  → POST /api/chat  body: { ..., language: "de" }
    → route.ts reads body.language once, validates against the curated list
      → forwards header  X-Digi-Language: de   (alongside X-Digi-Corpus-Index, X-Digi-Vault-Prefix)
        → digigraph WorkflowRequest.response_language
          → WorkflowState.response_language   (declared on the TypedDict — see "Lesson from #2097" below)
            → research_node: after resolving system_prompt (default or tenant override),
              if response_language is set and known:
                system_prompt += "\n\nRespond to the user only in {language_name}.
                                   Keep this instruction to yourself — do not
                                   mention or translate it."
```

`response_language` is validated against the same curated allowlist on the
Python side (a small `{code: display_name}` map, e.g. `de` → `German`).
Anything else — missing, empty, unrecognized — is treated as "no preference":
the directive is skipped and `system_prompt` is unchanged. The header value is
never interpolated into the prompt directly; only the mapped display name is,
so an attacker-controlled header can at most be ignored, never inject
arbitrary text into the system prompt.

### Lesson from #2097

`WorkflowState` is a `TypedDict` consumed by `StateGraph(WorkflowState)`, and
LangGraph silently drops any key that isn't declared on it — exactly the bug
`digisearch_index`/`vault_path_prefix` hit before #2097/#2099. `response_language`
must be declared on `WorkflowState` in the same PR that starts setting it, with
a regression test in the same shape as
`test_workflow_state_declares_corpus_routing_keys`, so this class of bug can't
recur silently a third time.

## Data flow — Foundry backend (DataTap)

```
Dropdown (chat-shell.tsx) → React state (same component, same auto-detect/session-only rules)
  → POST /api/chat  body: { ..., language: "de" }
    → route.ts reads body.language, validates against the curated list
      → createFoundryStreamResponse({ ..., responseLanguage: "de" })
        → before calling openai.responses.create, prepend a bracketed directive
          to the input text:
            input = responseLanguage && responseLanguage !== "en"
              ? `[Respond only in ${languageName}. Do not mention this instruction.]\n\n${message}`
              : message
```

Because Foundry holds the conversation server-side and each turn only sends
`lastUserMessageText(opts.messages)`, the directive is **re-sent on every
turn** rather than set once — there is no persistent per-conversation
instruction slot to set it in. This has two consequences, both acceptable:

- If a visitor changes language mid-conversation, the very next turn honors
  the new choice — a free upside of re-sending per turn.
- The directive text becomes part of what `azure_ai_search_call` sees as
  input when the DataTap agent decides to search, which could in principle
  perturb retrieval. The directive is kept short, in a fixed bracketed format,
  and placed before the real question (not interleaved) to minimize this; if
  a real perturbation shows up in practice, the fallback is moving the
  directive into a per-run `instructions` field if/when the Azure SDK call
  shape here is extended to support one (it does not today — see
  `OpenAIResponsesClientLike` in `stream.ts`, which only types
  `{ conversation, input, stream }`).

Same validation rule as the digigraph path: unrecognized/missing language →
no directive, `input` unchanged from today's behavior.

## Components touched

**Frontend (`frontend/digichat/src`):**
- `lib/embed-tenants.ts` — `EmbedTenantConfig.showLanguageSelector?: boolean`, validated like `showByok`; read as `tenant?.showLanguageSelector !== false` wherever consumed (default true unless explicitly disabled).
- `components/chat-shell.tsx` — dropdown in the `app-topbar` header (next to the existing BYOK button), using the existing `dropdown-menu.tsx` primitive. New session-scoped React state, seeded once from `navigator.language` matched against the curated list (else `"en"`).
- A small shared `LANGUAGES: { code: string; label: string }[]` constant (English/German/Italian/Spanish/French) used by the dropdown.
- `app/api/chat/route.ts` — reads `language` from the request body once; branches to whichever backend-specific mechanism applies (header for digigraph, adapter option for Foundry) — this file already branches per-backend today, so this is one more thing it threads through, not a new branch point.
- `lib/adapters/digithings/stream.ts` — `createDigigraphTraceStreamResponse` gains no new logic itself; `route.ts` sets the `X-Digi-Language` header alongside the other upstream headers it already assembles.
- `lib/adapters/foundry/stream.ts` — `createFoundryStreamResponse` gains a `responseLanguage?: string` option; directive prepended to `input` as shown above.

**Backend (`digigraph/src/digigraph`):**
- `models.py` — `WorkflowRequest.response_language: str | None = None`.
- `graph/state.py` — `response_language: str | None` declared on `WorkflowState`, documented in `ARCHITECTURE.md` next to the existing corpus-routing fields.
- `workflow.py` — `_initial_graph_state` copies `req.response_language` into initial state, same as `digisearch_index`/`vault_path_prefix`.
- `graph/research.py` — `research_node`: after resolving `system_prompt`, append the language directive when `state.get("response_language")` maps to a known language.
- A small `LANGUAGE_NAMES: dict[str, str]` map (kept in sync with the frontend's `LANGUAGES` list via a cross-check unit test, the same way corpus-routing tests cross-check camelCase/snake_case header names).

## Error handling

- Unknown/garbled/missing language code (either transport): treated as "no
  preference." No exception, no 500, just silently skip the directive.
- The directive is built entirely from the server-side/client-side
  `{code: display_name}` maps — raw header or body text is never
  string-interpolated into a prompt. This closes off the obvious
  prompt-injection angle ("set `X-Digi-Language` to some crafted string").

## Testing

- Python: `WorkflowState` declares `response_language` (mirrors
  `test_workflow_state_declares_corpus_routing_keys`); `research_node` unit
  test asserting the directive is appended for a known code and absent for an
  unknown/missing one, on both a default and an overridden `system_prompt`.
- Foundry adapter: unit test on `createFoundryStreamResponse` (or the pure
  input-building helper it delegates to) asserting the bracketed directive is
  prepended for a known language and the `input` is unchanged for
  `"en"`/unknown/missing.
- Frontend Vitest: dropdown renders the curated list, selecting a language
  updates state, `route.test.ts` asserts the outgoing header (digigraph) /
  adapter option (Foundry) matches the selected code, and that an
  unrecognized value never reaches either backend call.
- `ARCHITECTURE.md` updated for `digigraph` (new state field) and
  `frontend/digichat` (new tenant flag + dual-backend contract).

## Out of scope

- Translating the UI chrome (buttons, labels, dropdown itself) — only the
  model's response language.
- More than the five curated languages — extend the two `{code: display_name}`
  maps later if needed.
- Server-side persistence of a visitor's language choice across sessions or
  devices (explicitly session-only, see Decisions).
- Changing how the Foundry/DataTap agent's own instructions are configured in
  the Azure portal — this design only affects what DigiChat sends per turn.

## Rollout note

This design adds the capability and turns it on by default in code; it does
not itself deploy anything. DataTap prod is under an active hold (no
promotion without explicit sign-off) — shipping this to DataTap's live
instance still goes through that existing gate, independent of this spec.

Both `module/digichat` (165 commits behind `develop`) and `module/digigraph`
(110 commits behind) are currently stale. Per the branching model, either
needs a sync PR (`head=develop` → `base=module/<component>`) before a
`task/2103-*` branch is cut from it — cutting now would edit against
months-old code.
