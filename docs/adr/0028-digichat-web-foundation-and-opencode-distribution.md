# 0028. Keep digichat web-native; assistant-ui is the chat foundation; OpenCode is distribution only

## Status

Accepted — 2026-09-05 (amended the same day: owner selected assistant-ui and
the AI SDK UI message stream; the bake-off is closed). Amended again the same
day: the assistant-ui + AI SDK v7 + standard data-parts implementation is
**digichat 2.0**, not a 1.x/1.5 ship.

Supersedes [ADR-0027](0027-opencode-digichat-cli-foundation.md).

**Release line (owner, 2026-09-05):** the published package is
`frontend/digichat` **1.4.0**. Non-UI BFF/auth/embed-policy work may still
ship as **1.5** on `develop`. Do not merge the 2.0 UI/stream migration into
`develop` until a 2.0 release is intended — release-please on `develop` would
otherwise fold it into 1.5 or force a major too early. Do not add 1.x UI
features that 2.0 will replace (composer/palette/overlays/chrome; hold
[#3565](https://github.com/digithings-ai/digithings/issues/3565)). Agents
must not ship UI nits on the 1.4/1.5 line.

## Context

ADR-0027 proposed a hybrid in which digichat kept its web surface while adding
an OpenCode-based CLI and potentially embedding OpenCode packages. Investigation
on 2026-09-05 showed that this treats OpenCode as reusable presentation when its
presentation is coupled to its own agent runtime.

OpenCode is an agent whose UI clients talk to its agent server. Running
`opencode` starts a server and TUI over an OpenAPI 3.1 HTTP API
([server documentation](https://opencode.ai/docs/server/)). The TUI uses
`@opentui/solid` and a Zig-native terminal-cell renderer; OpenTUI has no browser
renderer (`@opentui/web` is its documentation site). OpenCode's browser app is
instead a conventional SolidJS/Vite/Tailwind/Kobalte coding GUI. The published
MIT package `@opencode-ai/ui` contains primitives and theme, but the transcript,
prompt input, streaming markdown, and message parts are in the private
SolidJS package `@opencode-ai/session-ui`. None is a drop-in foundation for
digichat's React/Next.js 16 client.

More importantly, digigraph's OpenAI-compatible API can make digigraph a model
inside OpenCode, but then OpenCode owns the tool loop, prompts, and context
compaction while the LangGraph supervisor becomes one completion call. Making
digigraph's capabilities MCP tools for OpenCode instead makes OpenCode the
orchestrator. Both violate the repository requirement that orchestration use a
LangGraph supervisor and subgraphs. Because OpenCode's UI is a client of its
agent, there is no renderer-only integration that avoids this ownership choice.

A fork does not solve the coupling at a supportable cost. `opencode-ai` released
1.18.26 on 2026-09-01, 1.18.27 on 2026-09-02, and 1.18.29 on 2026-09-04, while
the repository moved from `sst/opencode` to `anomalyco/opencode`. Carrying a
branded fork across that velocity is not defensible.

The existing delivery and code split also argues against replacing the web
foundation. `frontend/digichat` plus `frontend/digichat-ui` contain 18,622
production/config lines; in the Next.js app approximately 47% is browser
presentation and 53% is API routes, adapters, auth, persistence, and embed
policy. The genuinely visual part of `digichat-ui` is approximately 2,300–2,600
lines. Its roughly 3,100-line source already contains `DigiChatSession`,
slash-command handling, streaming intro, activities, transcript markdown, and
the terminal stylesheet; markdown is already delegated to `@digithings/web`.
Replacing the chat chrome would not retire most of digichat. A convincing CLI
skin on the current React UI is estimated at 1–2 weeks, or 3–5 weeks with a
theme system, keyboard-navigation polish, and accessibility. An alternative
must beat that baseline.

Delivery is entirely web today: the `/embed` iframe, the 308-line `widget.js`
popup, the `DigichatLauncher`, and a pinned Docker image. There is no terminal
binary. A real CLI also cannot reuse the browser auth contract unchanged:
`requireDigiChatAuth()` rejects a bare `dgk_live_…` digikey key before upstream
exchange; a CLI needs a `digi_live_…` machine key or an explicit auth-contract
change. Direct MCP access is not a shortcut: digigraph's MCP server binds
`0.0.0.0:8766` without authentication, and its workflow/chat tools bypass
`DigiAuthMiddleware`, HTTP rate limiting, and CORS. Access therefore requires a
gateway or private-network decision.

The platform roadmap is not primarily a renderer choice. No bot-profile model
exists: conversations have no `bot_id`, and today's “multiple bots” are separate
hostnames, environment entries, Foundry agents, or deployments. The ingredients
already exist in tenant-scoped keys/conversations, `DIGICHAT_EMBED_TENANTS`,
digigraph's per-request `allowed_tools`, and `DIGI_TENANT_CORPUS_MAP`; digichat
does not currently forward an allowed-tools field. That control-plane gap
remains whichever UI is selected.

## Decision

1. **digichat remains web-native.** Its client-facing surface is semantic DOM,
   delivered by the existing Next.js BFF, `/embed` iframe, and `widget.js`
   popup. It may look and behave like a terminal, but it is not a streamed or
   browser-rendered terminal process.
2. **A genuine terminal client is optional and additive.** It may serve
   authenticated operators and developers. It never becomes the anonymous or
   client-facing embed surface.
3. **OpenCode is an unmodified distribution channel, not a foundation or code
   dependency.** For clients who want a coding-CLI bot, distribute upstream
   `opencode-ai` with an `opencode.json` referencing authenticated digithings
   MCP endpoints and agent markdown files. Do not fork OpenCode, import its UI
   as digichat's frontend, call the product “opencode,” or imply upstream
   endorsement.
4. **assistant-ui is the selected chat-layer foundation.** Customize and theme
   it to a CLI look matching current digichat. Do not rebuild transcript,
   composer, palette, markdown, attachments, or accessibility in-house. Keep
   BFF persistence, auth, tenant/embed policy, and digigraph orchestration.
   Assistant Cloud is the thinnest OSS surface around persistence and
   observability — those stay in the BFF. This replaces the bake-off against
   extending `digichat-ui`.
5. **Bot profiles and the control plane remain the platform roadmap.** Define
   tenant-scoped profile identity, allowed tools, corpus/vault routing, system
   instructions, branding, backend choice, and conversation ownership
   independently of the renderer.
6. **Canonical renderer contract: the Vercel AI SDK UI message stream**
   (`UIMessage` / `UIMessageChunk` SSE, `x-vercel-ai-ui-message-stream: v1`).
   We are **not** inventing a digithings-only event dialect. assistant-ui
   consumes this natively via `useChatRuntime` + `AssistantChatTransport` and
   via DataStream. Other OSS `useChat` UIs speak it. The BFF already emits it
   on `POST /api/chat`. Ranking, layer map, and `data-digichatActivity` mapping
   live in
   [digichat renderer contract](../architecture/digichat-renderer-contract.md).
   **ACP is rejected as the canonical renderer contract** (editor/workspace
   JSON-RPC, stdio-first, no citation/RAG part model) and is reserved as an
   optional coding-agent/editor gateway. **AG-UI is deferred and not needed**
   for this path: assistant-ui consumes the AI SDK UI stream natively. Do not
   add `@ag-ui/*`.
7. **2.0 wire format uses standard AI SDK UI parts only.** Today's 1.4
   `data-digichatActivity` branded part stays on the 1.x line. The 2.0
   migration maps tool/activity/status onto standard `data-*` / tool /
   `source-*` / `reasoning` parts so a generic `useChat` client needs no
   digichat vocabulary. Keep the information (retrieval, vault, progress);
   drop branding from the wire.

`assistant-ui` is selected because it is an MIT-licensed UI rather than an
orchestrator, exposes unstyled composable React primitives, and lets
digithings delegate transcript/composer/tool chrome instead of maintaining
`digichat-ui`. First-class LangGraph, Ink, and React Native runtimes are
available over the same component model, but the **browser** path talks to the
BFF, not to LangGraph Cloud. Checked 2026-09-05: `@assistant-ui/react` 0.15.x
on npm; AI SDK runtime overview targets v7 (`@assistant-ui/ai-sdk`, `ai@^7`)
with a documented v6 pin. Caveat unchanged: Assistant Cloud is commercial and
OSS support is thinnest around persistence and observability — keep those in
the BFF.

## Rejected alternatives

### OpenCode or OpenTUI as the web foundation

Rejected because OpenCode's useful session UI is private and SolidJS-based,
OpenTUI has no web renderer, and using the OpenCode client necessarily installs
OpenCode's agent runtime above or instead of digigraph's LangGraph supervisor.
Using only `@opencode-ai/ui` would reuse theme primitives, not the chat layer
ADR-0027 sought to avoid rebuilding.

### A server-side PTY as the client-facing widget

Rejected. PTY streaming through xterm.js is proven for authenticated developer
products such as VS Code Web, GitHub Codespaces, Google Cloud Shell, and
JupyterLab; the investigation found no credible production precedent for a
public, anonymous client-site chatbot backed by a live PTY. Each isolated
sandbox reserves roughly 128–512 MiB before inference and is pinned to a node,
creating idle cost, reconnect, refresh, and load-balancing problems absent from
stateless SSE turns. Coding-agent TUIs expose shell and file-edit tools by
design; permission configuration is product policy, not a security boundary
for anonymous users.

xterm.js also has weak touch selection, reported Android Gboard input
corruption, and requires extra accessibility work. Although it provides
`screenReaderMode`, VS Code built a parallel accessible buffer for terminal
history. A defensible commercial widget would therefore need a semantic DOM
representation alongside the terminal—the surface the PTY was meant to
replace.

### A client-side TUI renderer

Rejected as the primary web path. OpenTUI and Bubble Tea have no supported web
target. Textual's `textual serve` still runs a server-side subprocess connected
to xterm.js. Ratzilla is a genuine Rust/Ratatui-to-WASM option with DOM, canvas,
and WebGL2 backends, but would rewrite a React product in Rust. Ink is a custom
React renderer, not a DOM renderer; its `ink-web` and `ink-canvas` bridges are
unmaintained upstream and still render through xterm.js. asciinema is playback
only.

### Forking OpenCode

Rejected because it preserves the dual-orchestrator conflict and adds a
high-velocity fork tax. Configuring upstream OpenCode as a separate client
distribution provides the useful coding-CLI channel without either cost.

### A proprietary digithings event dialect

Rejected. An earlier draft of this ADR deferred a “renderer-neutral” protocol
and left room to formalize a house dialect. The owner wants the generally used
open-source contract so the digichat backend can be used from any UI.
On 1.4/1.5, `data-digichatActivity` remains an AI SDK `data-*` part schema on
that public stream (not a second wire format). **2.0 drops the branded type**
and maps the same information onto standard UI parts.

### OpenAI Chat Completions or Responses as the UI contract

Rejected as the **renderer** contract. digigraph’s `POST /v1/chat/completions`
is an OpenAI-compatible **model** API (and OpenAI Responses is not built). The
owner’s impression that the stack already used “standardized OpenAI contracts”
maps to that hop, plus LiteLLM. The BFF already translates those chunks into
the AI SDK UI stream the browser consumes.

### LangGraph `stream` / `useStream` as the public UI contract

Rejected. That is digigraph’s internal graph runtime. Pointing UIs at it would
bypass BFF auth, embed policy, and persistence. assistant-ui’s LangGraph
adapter talks to LangGraph SDK/Cloud, which is the wrong ownership boundary.

### ACP as the canonical renderer contract

Rejected. ACP standardizes editor ↔ coding-agent JSON-RPC (stdio today). It is
not a web chat UI stream and has no citation/RAG part model. Keep it optional
as an editor/workspace gateway only.

### AG-UI as the canonical renderer contract

Rejected for this product. AG-UI is CopilotKit’s alternate agent-to-frontend
protocol. assistant-ui’s selected path consumes the AI SDK UI stream natively,
so an AG-UI adapter is not required. Do not add `@ag-ui/*`.

### Other packaged chat foundations

- Open WebUI is disqualified for white-labelled delivery: license clause 4
  prevents replacing its branding after 50 end users in a rolling 30-day
  period without permission or an enterprise license.
- Lobe Chat is disqualified because its community license requires a paid
  commercial license to develop and distribute a derivative; a reskin is
  derivative.
- Charm Crush uses FSL-1.1-MIT. Its “Competing Use” restriction plausibly
  covers a coding-CLI-style chatbot sold to clients and requires legal review
  before reconsideration.
- Toad is AGPL-3.0 with a separately negotiated commercial license.
- aider is not selected because its default branch had no commit since
  2026-05-22 and its last tagged release was in August 2025. Elia and
  textual-web are dead; Textual has been maintained personally by Will
  McGugan since Textualize wound down in May 2025.

assistant-ui, OpenCode, OpenTUI, LibreChat, xterm.js, and terminal.css are MIT;
Chainlit, Codex CLI, Gemini CLI, Qwen Code, Goose, and Continue are Apache-2.0
with NOTICE obligations. Those licenses permit commercial rebranding but do
not grant trademark rights. Clean licensing alone does not make any option the
right architecture.

## Consequences

**Positive:**

- digigraph remains the sole orchestration brain; presentation cannot silently
  insert a second tool loop or context-compaction policy.
- The chat layer is delegated to OSS (assistant-ui) instead of growing
  `digichat-ui`; the BFF still owns auth, persistence, tenant/embed policy,
  and adapter translation.
- The renderer contract is a public stream other UIs can consume; the BFF
  already speaks it.
- OpenCode remains available to teams that want its coding CLI, without a fork
  or runtime dependency.
- Bot-profile/control-plane work can proceed independently of the UI migration.

**Negative / tradeoffs:**

- A real assistant-ui migration (theme to CLI look, standard UI parts,
  AI SDK v6 → v7) is **digichat 2.0** on a long-lived draft branch; this ADR
  does not implement it and must not be treated as permission to merge that
  work into the 1.5 train.
- Web and any future terminal client remain distinct delivery surfaces. They
  share the BFF UI-stream contract, not a PTY or ACP session.
- An OpenCode distribution needs authenticated MCP ingress; the current
  unauthenticated digigraph MCP listener must not be exposed as the answer.
- Assistant Cloud must not become the persistence/observability path.

**Follow-up:**

- Implement assistant-ui + AI SDK v7 + standard UI parts as **digichat 2.0**
  on a draft PR that must **not** merge to `develop` until the 2.0 cut:
  [#3626](https://github.com/digithings-ai/digithings/issues/3626). Use
  `feat(digichat)!:` / `BREAKING CHANGE` so release-please treats it as 2.0
  when it lands.
- 1.5 on `develop` stays **non-UI** (BFF, auth, persistence, tenant/embed
  policy, adapters). Do not land composer/palette/overlay/chrome on 1.x.
- Hold [#3565](https://github.com/digithings-ai/digithings/issues/3565)
  permanently on the 1.x chrome. Its product semantics remain useful on 2.0,
  but overlay/palette work on `digichat-ui` would be throwaway.
- Continue [#3602](https://github.com/digithings-ai/digithings/issues/3602);
  structural DOM sanitization for dashboard-to-digichat page context is
  renderer-independent.
- AG-UI is out of scope. ACP remains optional editor/workspace gateway only.

Issue #3568 was closed as Done through PR #3570 while its “follow-up spike issue
opened” criterion remained unchecked; no spike report exists. ADR-0027
therefore never advanced beyond proposed and is superseded rather than adopted.

## Links

- Decision issue: [#3623](https://github.com/digithings-ai/digithings/issues/3623)
- Implementation follow-up: [#3626](https://github.com/digithings-ai/digithings/issues/3626)
- Superseded ADR: [ADR-0027](0027-opencode-digichat-cli-foundation.md)
- Superseded research plan:
  [OpenCode as digichat CLI/TUI foundation](../architecture/opencode-digichat-adoption.md)
- Existing frontend boundary:
  [digichat modular frontend](../architecture/digichat-modular-frontend.md)
- Renderer contract (verified 2026-09-05):
  [digichat renderer contract](../architecture/digichat-renderer-contract.md)
- OpenCode server architecture: https://opencode.ai/docs/server/
- OpenCode repository: https://github.com/anomalyco/opencode
- assistant-ui repository: https://github.com/assistant-ui/assistant-ui
- AI SDK UI stream protocol: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
- assistant-ui DataStream: https://www.assistant-ui.com/docs/runtimes/custom/data-stream
- assistant-ui AI SDK v7: https://www.assistant-ui.com/docs/runtimes/ai-sdk/v7
