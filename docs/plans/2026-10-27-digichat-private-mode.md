# digichat private mode (`/private`)

**Status:** implemented, unreviewed · **Lane:** M · **Approver:** CTO · **Date:** 2026-10-27

> **Not a data-protection control.** Private mode changes what the assistant *says*, not what server-side stores hold. It is a demo aid. Never describe it as anonymisation, and see §4 before promising anything about it to a client.

## 1. Goal

A generic digichat capability — `/private`, off by default — that any tenant can enable so a session's visible replies contain no real personal data, letting the product be demonstrated to the client it is about without showing that client their own data back.

## 2. Why now

OCC (Online Compliance Center) is the first consumer: a client-facing tenant at `digithings.ai/chat/occ` (`apps/digichat/config/examples/occ-embed.yaml`, host `occ.digithings.ai`) with read access to real Zammad tickets via MCP. Any live demo of it, and any screenshot of one, currently shows real client names. Building it as a digichat capability rather than an OCC patch means the next such client gets it by configuration.

## 3. Scope

**Mode resolution and UI**

- `private` is a session setting: default **off**, ON via `?private=1` on an embed URL or the `/private` command.
- ON-only by construction, mirroring `wide` (`apps/digichat/src/lib/embed-ui-params.ts`, `=== "1"`). There is no `private=0`.
- Resolved **once at mount** into session state, not at send time — the transport is frozen on first render (#1339), and the mode must apply from message one.
- A visible mode badge in the composer ("Private session"). Required: unknown URL params are silently ignored throughout the embed, so a typo'd `?privte=1` would otherwise run an unmasked demo with no indication.
- Any embed can opt in: `apps/digithings-web/components/ChatEmbedShell.tsx` forwards `private=1` into the iframe URL when the parent URL carries it. It does **not** consult `acceptsInviteToken` — that is the access gate, not a property of this feature.

**Tenant opt-in**

- A tenant offers the mode only when its config says so. No tenant gains a `/private` command, and no `?private=1` is honoured, until it opts in.

**Instruction delivery**

- The client sends `x-digi-private: 1`; `/api/chat` treats it as a boolean and never accepts instruction text from the client.
- The instruction is a server-owned constant (`apps/digichat/src/lib/private-mode.ts`) appended to the **last user turn's parts on the UI messages**, once, before the route picks a backend adapter. That placement is load-bearing: the route has five paths — foundry, the non-AI-SDK branch, the AI-SDK branch, the digigraph trace stream, and the legacy `streamText` pair — and **the trace stream is the default**. Patching the converted model messages instead reaches only the legacy pair, which is how the first implementation shipped as a silent no-op.
- It cannot ride a `system` message or the AI SDK `instructions` option: digigraph flattens the request into one prompt and drops every non-`user`/`assistant` turn (`digigraph/src/digigraph/chat_prompt.py`, pinned by `tests/dg/test_chat_prompt.py::test_system_messages_are_omitted`), and its request model forbids an `instructions` field (`models.py`, `extra="forbid"`). A user turn is the only channel that reaches the model.
- Instruction content: replace real person names, organisation names, emails, phones, addresses, ticket ids and invoice/contract numbers with fictional stand-ins; assign them in first-appearance order and reuse them for the session; treat all surface forms of one party as that party; draw from a fixed roster in the module rather than inventing names; never announce the substitution.
- The mutation applies to the converted model messages only, so stored payloads and the rendered transcript of earlier turns are untouched.

**Suppressing PII-bearing surfaces**

- Tool output and reasoning do not render while the mode is on: `null` returns at the parts switch in `packages/ui/src/components/chat/gallery-thread/thread.aui.tsx` for `group-tool`, `tool-call`, `group-reasoning` and `reasoning`, plus the `group-chainOfThought` wrapper so a turn does not show a "Worked" header that expands to nothing.
- This is a hard override, not a disclosure preference: `reasoningMode` cannot express `"off"`, and it must hold while streaming.
- `/export` is refused while the mode is on — export serialises stored messages, which still hold the real text the user typed.
- Session titles read "Private session" instead of truncating the first user message, which would otherwise put a real name in the sidebar.

## 4. Non-goals

- **Not anonymisation, and not to be described as such.**
- **Does not clean the stores.** Typed text still reaches the provider, `conversation_messages.payload` (jsonb), the digigraph checkpoint DB, LangSmith spans (email/phone/key masked only) and compaction offload files.
- **No detection engine, no entity map, no tenant lexicon, no NER.** That is the deferred alternative, and the only version that would clean the stores.
- **Reasoning is hidden, not suppressed.** No request field stops generation; visibility is display-only.
- **Tools still receive and return real values**, deliberately, so lookups keep working. That is this approach's main advantage over client-side substitution.
- **The link param is not tamper-proof.** Stripping `?private=1` yields a normal chat.

## 5. Design

| File | Change |
|---|---|
| `apps/digichat/src/lib/embed-ui-params.ts` | `private` in `readEmbedUiParams()`, `=== "1"` |
| `apps/digichat/src/hooks/use-embed-ui-params.ts` | surface the flag |
| `apps/digichat/src/app/(digichat)/embed/embed-client.tsx` | session state seeded once at mount |
| `apps/digichat/src/lib/product-slash-commands.ts` | `/private` toggle; `/export` blocked while on |
| `packages/digichat-ui/src/slash-commands.ts` | registry entry, id `private` |
| `apps/digichat/src/hooks/use-embed-digi-chat.ts` | `x-digi-private: 1` on send when on |
| `apps/digichat/src/app/api/chat/route.ts` | read header; apply `withPrivateModePrompt` to converted messages |
| `apps/digichat/src/lib/private-mode.ts` **(new)** | rosters, instruction, `isPrivateMode`, `withPrivateModePrompt` |
| `packages/ui/src/components/chat/gallery-thread/thread.aui.tsx` | `privateMode` prop; part nulls; badge |
| `apps/digichat/src/components/chat-panel.tsx` | neutral session title while on |
| `apps/digithings-web/components/ChatEmbedShell.tsx` | forward `private=1` into the iframe URL |
| `apps/digichat/AGENTS.md`, `digigraph/AGENTS.md` | the no-masking rule now names this exception |

## 6. Acceptance tests

1. `?private=1` enables the mode and shows the badge; `?private=0` and unknown values leave it off.
2. `ChatEmbedShell` forwards the param only for exactly `1`, and for tokenless tenants too.
3. `/private` toggles the session; `x-digi-private: 1` is sent only while on.
4. The instruction is appended exactly once, to the last user turn, and only when the header is `1`; stored messages and earlier turns are unchanged.
5. Tool and reasoning parts render nothing while on, streaming and at rest, including no empty chain header.
6. `/export` is refused while on; the title is "Private session".
7. With the header absent, requests and rendering are unchanged.
8. Tenant without the opt-in: no command, and the param is ignored.

## 7. Risks and open questions

1. **Compliance depends on the model and cannot be tested.** A prompt is a preference; it degrades with context length and stops being enforced silently after compaction.
2. **Alias drift across compaction** (`digigraph/src/digigraph/compaction.py` evicts messages, taking the model's ledger with them). Mitigation: keep demo sessions short.
3. **The example suggestions manufacture PII.** `occ-embed.yaml` chrome is already free of names, but "Show my open support tickets" and "Summarize this week's support tickets" pull real Zammad data into context. Safe only while the tool panel is hidden. **Owner: product.**
4. **Hidden ≠ absent.** Tool JSON and reasoning remain in the stored payload and traces.
5. **The exception has a paper trail, not a test.** The rule amendment in §5 is the only thing stopping a future agent from reading "do not add a masker" and reverting this.

## 8. Vision check

Fits the direction: digichat is the client-facing surface, and a per-tenant demo-safety switch is a product capability rather than a workaround. No auth, broker, migration or live-trading surface is touched. The language is the risk: a compliance client would reasonably read "anonymous" as a regulatory claim, so the UI and docs say "private session" and the stores stay honestly described as untouched.

## 9. Decision log

- **2026-10-27 — prompt-driven, not client-side.** Chosen for semantic coverage and because it leaves tool lookups working. Accepted consequence: stores keep real text. The entity-map engine remains the deferred alternative.
- **2026-10-27 — instruction rides the user turn.** A digigraph probe showed client `system` turns are dropped (`chat_prompt.py`) and `instructions` is rejected (`models.py`), so the first implementation was inert. Replaced with `withPrivateModePrompt`.
- **2026-10-27 — PII-masking exception granted (Chris).** The twice-reaffirmed "invite link is the only gate" rule named this as forbidden on the OCC path. Chris approved a display-side exception; both component `AGENTS.md` notes were amended in the same change so the rule and the code do not contradict.
- **2026-10-27 — scope widened from OCC to any tenant.** The feature is a digichat capability enabled per tenant by configuration; nothing in the implementation is OCC-specific.
- **2026-10-27 — instruction moved to the UI messages.** A review found the model-message patch reached only the legacy `streamText` calls, because `useTraceStream` is on by default and converts the messages itself. The same review found the render flag never reached `<Thread>` (so tool output still rendered) and the per-message export menu still leaked the user's text; all three are fixed.
- **2026-10-27 — rebased onto `github/develop`.** The branch was cut from the forge mirror, which was 59 commits behind; 7 of the 28 files had already moved on develop.
- **2026-10-27 — production OCC opt-in.** Production resolves the tenant from `DIGICHAT_EMBED_TENANTS` in `infra/digichat-release/DIG-4488-occ-tenant-overlay.json`, not from the YAML example, so the flag is set there too.
