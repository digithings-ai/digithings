# 0028. Keep digichat web-native; use OpenCode only as a distribution channel

## Status

Accepted — 2026-09-05

Supersedes [ADR-0027](0027-opencode-digichat-cli-foundation.md).

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
4. **`assistant-ui` is the leading chat-layer candidate, not yet the selected
   foundation.** Run a timeboxed bake-off against extending the existing
   `digichat-ui`. Compare the same representative transcript, tool activities,
   embed policy, keyboard navigation, accessibility, BFF persistence, and
   terminal styling. The result requires a separate decision before either
   implementation is adopted.
5. **Bot profiles and the control plane are the platform roadmap.** Define
   tenant-scoped profile identity, allowed tools, corpus/vault routing, system
   instructions, branding, backend choice, and conversation ownership
   independently of the renderer.
6. **A renderer-neutral event protocol is deferred.** Agent Client Protocol
   (ACP) is under separate investigation and may serve this role; this ADR makes
   no claim about its suitability, license, or maintenance status.

`assistant-ui` leads the bake-off because it is an MIT-licensed UI rather than
an orchestrator, has first-class LangGraph integration, exposes unstyled
composable React primitives, and offers `@assistant-ui/react-ink` and
`@assistant-ui/react-native` renderers over the same runtime. Version 0.15.18
was published 2026-09-03 and the repository had approximately 12,000 stars and
active pushes when checked. Its caveat is material: the YC-backed company also
sells Assistant Cloud, and open-library support is thinnest around persistence
and observability. digichat's BFF already owns those responsibilities; the
bake-off must prove that boundary rather than assume it.

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
- Existing BFF security, persistence, adapters, embeds, and distribution stay
  load-bearing while the smaller chat layer can be evaluated independently.
- OpenCode remains available to teams that want its coding CLI, without a fork
  or runtime dependency.
- The control-plane work can proceed without waiting for a renderer decision.

**Negative / tradeoffs:**

- digithings still owns a polished, accessible web shell and must fund either
  the existing-UI extension or an `assistant-ui` migration.
- Web and any future terminal client are distinct delivery surfaces. Shared
  events and sessions are deferred rather than assumed.
- An OpenCode distribution needs authenticated MCP ingress; the current
  unauthenticated digigraph MCP listener must not be exposed as the answer.
- `assistant-ui` remains a candidate. This ADR intentionally does not authorize
  a dependency migration.

**Follow-up:**

- Open a bake-off spike for `assistant-ui` versus extending `digichat-ui`.
- Define bot-profile/control-plane models and forwarding independently.
- Hold [#3565](https://github.com/digithings-ai/digithings/issues/3565)
  until the web-shell bake-off settles. Its product semantics remain useful,
  but overlay/palette implementation may be throwaway.
- Continue [#3602](https://github.com/digithings-ai/digithings/issues/3602);
  structural DOM sanitization for dashboard-to-digichat page context is
  renderer-independent.
- Investigate ACP separately before deciding on a renderer-neutral protocol.

Issue #3568 was closed as Done through PR #3570 while its “follow-up spike issue
opened” criterion remained unchecked; no spike report exists. ADR-0027
therefore never advanced beyond proposed and is superseded rather than adopted.

## Links

- Decision issue: [#3623](https://github.com/digithings-ai/digithings/issues/3623)
- Superseded ADR: [ADR-0027](0027-opencode-digichat-cli-foundation.md)
- Superseded research plan:
  [OpenCode as digichat CLI/TUI foundation](../architecture/opencode-digichat-adoption.md)
- Existing frontend boundary:
  [digichat modular frontend](../architecture/digichat-modular-frontend.md)
- OpenCode server architecture: https://opencode.ai/docs/server/
- OpenCode repository: https://github.com/anomalyco/opencode
- assistant-ui repository: https://github.com/assistant-ui/assistant-ui
