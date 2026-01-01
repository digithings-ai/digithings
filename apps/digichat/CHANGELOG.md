## [2.7.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.9...digichat-v2.7.0) (2026-10-24)

The de-slop release: one canonical token set across the chat, the desk and the
terminal; the product chat moves to `/chat` with the menu on `?mode=menu`; a
scroll setting that can leave the stream alone; the gate budget as a cube bar;
and the keyboard retracts on every way a turn starts.

### Features

* **digichat:** the product chat is served at `/chat`, the chooser stays on `?mode=menu` (an internal change)
* **digichat:** the gate's turn budget is a cube bar in the composer toolbar, sharing one fill scale with the context meter (an internal change)
* **digichat:** a scroll setting that follows the stream or leaves it alone (an internal change)
* **ui:** canonical surface/ink/hair/accent/danger roles replace the shadcn semantic utilities across the chat (an internal change)

### Bug Fixes

* **digichat:** the keyboard retracts on every way a turn starts, and after send on a phone (an internal change, an internal change)
* **digichat:** the work chain no longer pushes the loading row down at handoff (an internal change)

## [2.6.9](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.8...digichat-v2.6.9) (2026-10-23)

One density token set across the thread, and raw backend ids everywhere: the
trace, `/tools`, the model toolbar, exports and mobile all name the tool the
backend actually calls. The model picker is a provider path tree, the evaluation
`/tools` page lists every tool its agent is bound to, and house chats stay on
the 1017 checkpoint. Limits move into YAML per deployment.

### Bug Fixes

* **digichat:** raw backend tool ids everywhere — the streaming trace, `/tools`, the model toolbar, exports and mobile show the id the backend calls (`<service>_<tool>`), not a humanised label. The humanising layer is deleted, not bypassed (an internal change, an internal change)
* **digichat:** one density token set across the thread. The phone keeps its airy default after a prefs reset, the floating action bar no longer paints over the next turn's first line, and the reference composer resolves `--composer-padding` instead of falling back to 0 (an internal change)
* **digichat:** the evaluation deployment's tool list had lost eight of the agent's 42 tools in a merge. All 42 are back, in the agent's groups, with raw ids (an internal change)
* **digichat:** the model chip and the lock agree. No open-models button over a locked, one-model list (an internal change)
* **digichat:** house chats run the 1017 checkpoint on the CheaperInference API — it reasons only when asked, and the chain asks (an internal change)
* **digichat:** the signed evaluation proof is removed from the evaluation deployment, as ordered (an internal ticket, an internal change)
* **ui:** the overlay scrollbars come from one copy of the rule blocks, and the composer picker closes through its own scope on the back key (an internal change, an internal change)
* **digichat:** the invite-only embed with no key answers the site 404 at the Worker, and the in-image helpdesk MCP sees its own loopback Host (an internal change, an internal change)

### Features

* **digichat:** `/models` is a provider path tree — models grouped by id segments, bare modes as their own rows, and a typed filter that searches collapsed providers (an internal change)
* **digichat:** the evaluation `/tools` page lists all 42 tools the Foundry agent is bound to, in the agent's own groups, each reading On with a checked, non-toggling switch; the house page lists DigiSearch and DigiVault (an internal change, an internal change)
* **digichat:** YAML limits for every deployment gate — per-deployment token, cost and rate limits live in config, not code (an internal change)
* **digichat:** house is the checked-in default: one `defaults.yaml` that hosts extend, with evaluation and client clearing what they do not want (an internal change)
* **digichat:** the session starts on Auto when the deployment's default is the auto model (an internal change)
* **ui:** the theme toggle is shared with `/chatbot` and the embed instead of three separate controls (an internal change)

## [2.6.8](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.7...digichat-v2.6.8) (2026-10-22)

Reasoning is on for every chat, and `/effort` sets how hard the model thinks.
The model name and picker are back on by default on digithings.ai and the client
embed. Exports save on phones and inside embeds. A stopped or failed turn stops
animating. `/tools` lists each service with its tools again. The `/chat` page
has proper loading, 404 and failure states. Every export path is redacted.

### Bug Fixes

* **digichat:** the model name and picker are on by default for the house chat and the client embed. The house chat keeps its per-visitor Premium window. client carries no Premium meter and no tokens-per-minute guardrail. A tenant can still opt out with `allowPicker: false` or `clientPicker: false`. 2.6.6 had made the picker opt-in (an internal change)
* **digichat:** Markdown and HTML exports save on phones and inside embedded chats. The file link now stays valid long enough for the browser's save confirm. Phones use the share sheet where the page allows it. When the tap that started the export has expired, a Save button asks for one more tap (an internal change)
* **digichat:** a stopped or failed turn stops its animations (an internal change)
* **digichat:** `/tools` lists each service as a tree with its tools under it, as before the 2.6.6 palette change (an internal change)
* **web:** the `/chat` page shows loading, not-found and failure states instead of a blank frame (an internal change)
* **digichat:** every export path is redacted. The clipboard copy, the `mailto:` body, the `.txt` export and the minimal HTML export now go through the shared redactor, as the Markdown download already did. A `)` or a backtick inside a secret no longer leaks the rest of the value (an internal change, an internal change)
* **digichat:** a evaluation starter asks a full question instead of a fragment (an internal change)

### Features

* **chat:** reasoning is on for every chat, and `/effort` (low/medium/high) sets the model's reasoning level where the model has one. The house model (DeepSeek V4.1 Flash 1017) only reasons when a level is sent, so with no `/effort` it gets `medium`. Foundry backends get `/effort` as `reasoning.effort` and drop it for the turn if it's refused. Which models take a level is configured in `config/model-policy.json` (an internal change)

### Known limits

* An embedding page must allow `web-share` on the iframe for the phone share sheet. Without it, the export falls back to a download (with the extra tap when needed).
* In the command palette, typing `/export html` and pressing Enter runs the highlighted row, which may be the Markdown export. Tapping the row works.
* Premium spend counters are per instance, as in 2.6.7.

## [2.6.7](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.6...digichat-v2.6.7) (2026-10-22)

The invite-only client embed loads again, a visitor who leaves or presses stop
ends the model call, the house chat can carry a context meter, and one answer
exports as HTML from the message menu.

2.6.6 was rolled back from the digithings.ai / client deployment: every
invite-token request to `/embed` answered 500.
2.6.7 carries the fix and everything 2.6.6 shipped.

### Bug Fixes

* **digichat:** an embed request that carries `?token=` loads again behind the trusted-proxy entrypoint. Next now listens on `localhost`, so the token-strip rewrite stays internal and no longer becomes a 500 with no content type (an internal change)
* **digichat:** when a visitor leaves or presses stop, the entrypoint closes the upstream request, so the model call and the session's run lock end with it (an internal change)
* **digichat:** a Foundry tool-call wrapper left unclosed at the end of an answer no longer reaches the visitor (an internal change)

### Features

* **digichat:** the composer context meter can be switched on for the house chat slugs only (`showContextMeter`, on for them unless set false, refused on any other host) (an internal change)
* **digichat:** export one answer as HTML from the message menu (an internal change)

### Known limits

* Premium spend counters are per instance. With `DIGICHAT_TRUSTED_PROXIES` unset, anonymous visitors behind a shared ingress share one premium allowance and one guardrail bucket on that instance.
* In the redacted `/export html`, a `)` or a backtick inside a secret leaks the rest of that value.
* The clipboard, mailto, `.txt` and minimal-HTML exports are not redacted.
* The live house chat publishes no models yet, so it shows no context-meter bar. Digigraph reporting the served model is a follow-up.

## [2.6.6](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.5...digichat-v2.6.6) (2026-10-21)

Take the chat with you and choose the model: `/export html` saves the rendered
conversation as one self-contained HTML file, a config-driven model picker
offers presets and a metered Premium group, one shared guardrail covers tokens
and tool calls, one command palette, and `/theme` on
every embedded chat.

### Features

* **digichat:** a config-driven model picker on digithings.ai and the client embed: presets first, then the newest tool-capable model of each family under the standard output-price cap, and a Premium group for manual picks metered per user per rolling day (an internal change)
* **digichat:** a shared guardrail, off unless a deployment sets it: `tokensPerMinute` on every backend and `maxToolCallsPerTurn` enforced per backend as documented; rate-limit identities come from the server-derived client IP, and `DIGICHAT_TRUSTED_PROXIES` names the ingress allowed to stamp it (an internal change, shipped via an internal change)
* **digichat:** `/export html` saves the open conversation as a single self-contained HTML file, built in the browser from the rendered thread, with scripts, frames and non-http links stripped and redaction applied to the page text (an internal change)
* **digichat:** `/theme` works on every embed tenant and starts from the tenant's own theme (an internal change)
* **digichat:** worked-chain density, palette defaults and a braces tool mark (an internal change)
* **digichat:** the evaluation tenant's welcome and placeholder describe the sample email archive (an internal change)

### Bug Fixes

* **digichat:** one command palette: typing `/` inside a submenu filters that pane, and tools are switched on and off only in `/tools` (an internal change)
* **ui:** the worked chain has one spacing rhythm (an internal change)
* **digichat:** MCP call arguments streamed on `mcp_call_arguments` events are shown (an internal change)

### Behaviour changes

* **digichat:** on Container deploys the trusted-proxy entrypoint now always sits in front of Next, even with `DIGICHAT_TRUSTED_PROXIES` unset, so it can stamp the peer socket for rate-limit identity (an internal change, shipped via an internal change)

### Known limits

* Premium spend counters are per instance. With `DIGICHAT_TRUSTED_PROXIES` unset, anonymous visitors behind a shared ingress share one premium allowance and one guardrail bucket on that instance.
* In the redacted `/export html`, a `)` or a backtick inside a secret leaks the rest of that value.
* The clipboard, mailto, `.txt` and minimal-HTML exports are not redacted.
* On Container deploys, a visitor who leaves or presses stop does not abort the in-flight model call: the proxy does not yet destroy the upstream request on client disconnect. The fix is in an internal change for the next release.
* The house chat's composer context meter (an internal change) comes in the next release.
* Exporting one answer as HTML from the message menu (an internal change) comes in the next release.

## [2.6.5](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.4...digichat-v2.6.5) (2026-10-21)

One caret and your own colours: every collapsible row in a turn opens with
the same pixel chevron, and `/theme` paints the chat in any shared palette,
light or dark.

### Features

* **digichat:** `/theme` picks a palette from the shared registry and a mode (`/theme aura light`); the choice paints before the first frame and persists, and pinned embeds keep their own theme (an internal change)

### Bug Fixes

* **digichat:** the work chain, reasoning, tool group and every tool row share one caret, the square pixel chevron of the user-message mark, which turns down when its own row opens and nowhere else (an internal change)
* **chat:** the disclosure triggers announce their label once (an internal change)
* **ui:** the JSON view's whitespace repair runs in one linear pass; a partial or unparsable payload over 65,536 characters is shown raw instead of repaired (an internal change)
* **digichat:** the evaluation tenant's starter questions ask about the sample email archive its agent can reach (an internal change)
* **ui:** the theme provider follows every painter, and a pinned embed sets its own `theme-color` (an internal change)
* **chat:** the JSON view that renders tool arguments and results tokenizes in one pass, with no regular expression over strings (an internal change)
* **digichat:** the view-level wording has one home, so the session-preferences refusal no longer names retired command ids (an internal change)

## [2.6.4](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.3...digichat-v2.6.4) (2026-10-21)

The chat shows the backend's own words: what the server says while it works,
every tool argument in full, and the tool's real error under it. A turn that
runs into the model's per-minute token limit now waits and carries on.

### Bug Fixes

* **chat:** the loading row shows text only when the server sent a status ("Waking up services…", a capacity countdown); a plain wait for the response is the animation alone (an internal change)
* **chat:** tool arguments and results show as full JSON in a scroll area, a tool's error sits under its arguments with the whole traceback, and server notices and errors are boxed, the errors in a faded red (an internal change)
* **digichat:** a Foundry turn that hits the model's per-minute token limit mid-stream shows a countdown, waits for the window (Retry-After, capped at 90 s) and resumes the same conversation, up to three times, then explains what happened instead of a generic outage line (an internal change)

## [2.6.3](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.2...digichat-v2.6.3) (2026-10-21)

A turn shows one thing moving: the work block no longer appears before the
agent has done anything, and the composer row does not open with a stray
separator.

### Bug Fixes

* **chat:** a status part alone gets no work block — the loading row waits for the agent, and the work block takes over the moment reasoning, a tool call or the answer arrives (an internal change)
* **chat:** the composer row lists its facts without a dangling separator (an internal change)

## [2.6.2](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.1...digichat-v2.6.2) (2026-10-21)

A turn shows one thing moving at a time, and a tool failure says what went
wrong instead of looking like an outage.

### Bug Fixes

* **chat:** one loading affordance per turn — the dot matrix waits for the agent, and the work block takes over the moment reasoning, a tool call or the answer arrives (an internal change)
* **foundry:** a tool that refuses the call says so — the tool's own complaint reaches the failed row and the turn, not "the assistant is unavailable" (an internal change)

# Changelog

## [2.6.1](https://github.com/digithings-ai/digithings/compare/digichat-v2.6.0...digichat-v2.6.1) (2026-10-20)

The trace of the agent's work gets one voice, and a tenant on an Azure AI
Foundry agent stops advertising models it does not have.

### Features

* **chat:** the chain title follows the latest step — `Working — digisearch` while a tool runs, `Used 3 tools` when it is done — instead of a static word (an internal change)
* **foundry:** a tenant on an Azure AI Foundry agent shows no model list, names its real backend (`Azure AI Foundry`), and reports the token usage the Responses API gives it (an internal change)
* **chat:** the composer menu opens a sub-page on its current value (an internal change)

### Bug Fixes

* **chat:** two work runs with nothing between them are one block, and the block stops working when the answer starts (an internal change)
* **chat:** the provider chip is named from the active backend (an internal change)
* **chat:** the context meter's shares stay inside the turn (an internal change)
* **digichat:** the image packages the `@digithings/catalog` workspace, so the build no longer dies on a missing module (an internal change)
* **ci:** the review-coverage check reads the check rollup through its contexts connection, so the required main check is posted again (an internal change)

## [2.6.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.5.1...digichat-v2.6.0) (2026-10-20)

The composer and the trace of the agent's work, rebuilt on assistant-ui's own
structure: one vocabulary for how much of the work a user sees, one block for
the whole chain, and one voice across the trace.

### Features

* **chat:** the trace is a four-rung ladder — `hidden` folds it to one line, `quiet` shows the titles only, `balanced` opens the rows while they stream, `verbose` leaves everything open (an internal change)
* **chat:** the composer footer shows the model, the provider, the connected MCPs and the context fill, and each of them opens the right panel (an internal change)
* **chat:** `/help` opens a panel with the commands, the shortcuts and how to reach a person (an internal change)
* **chat:** the model picker offers `auto` when the deployment pins no model, and the provider list names the in-house default beside the bring-your-own-key ones (an internal change)
* **chat:** the block cursor stands on the measured text baseline and centres on the letters (an internal change)
* **digichat:** the first turn runs on the tenant's curated default model (an internal change)
* **digichat:** a model at capacity is waited out instead of failing the turn (an internal change)

### Bug Fixes

* **chat:** the reasoning and the tool calls live under one "Working" block that folds as one, and it stays open for the whole turn, so it no longer flickers shut between two tool calls (an internal change, an internal change, an internal change)
* **chat:** the trace keeps its place — the marks are always there, the counts no longer move the arrow, and every arrow sits next to its own text (an internal change, an internal change, an internal change, an internal change)
* **chat:** the scrollbars are square everywhere, and the menu keeps its cursor in view (an internal change, an internal change, an internal change)
* **chat:** the composer is a single row and carries no editing chrome — Escape cancels, and an empty or unchanged edit is never sent (an internal change)
* **chat:** the menu moves with the arrow keys, the right arrow submits and the left one goes back, and the command palette matches the menu (an internal change)

## [2.5.1](https://github.com/digithings-ai/digithings/compare/digichat-v2.5.0...digichat-v2.5.1) (2026-10-19)

Restores the client chat behaviour the 14 Oct build had, which the Cloudflare
split did not carry over.

### Bug Fixes

* **client:** citations are inline markdown only, deduped per turn, with a static source mark and non-web hrefs rendered as plain text (an internal change)
* **client:** Allow/Deny only for an explicit approval or interrupt, not a server tool whose output was cut by a cold start (an internal change)
* **client:** streaming tool args are pretty-printed from a repaired JSON prefix; DeepSeek's echoed search-template line is stripped (an internal change)
* **client:** boot loader shows "Waking up services…" again (an internal change)
* **client:** default model back to `deepseek/deepseek-v4.1-flash` with the six-model session allowlist and matching LiteLLM entries (an internal change)
* **client:** `lockSessionControls` pins the house model and hides the session model/MCP/tool controls (an internal change)
* **digichat:** the digikey `bff_session` exchange retries a cold container with backoff (an internal change)

## [2.5.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.3.2...digichat-v2.5.0) (2026-10-19)

The first tagged digichat release after `digichat-v2.3.2`. It carries the client
chat work: the client surface now lives on its own
Cloudflare worker, and the improvements that were sitting behind that split are
in this image. digichat 2.4.0 was never tagged.

### Features

* **digichat:** client chat on its own worker - `/chat/client*`, the ticket-system MCP bridge and the
  digichat admin surface move to `digithings-digichat` instead of the base stack (an internal change)
* **digichat:** edit-in-composer - an answer can be edited and re-sent (an internal change)
* **digichat:** per-tool toggles - a visitor can switch individual tools off for a session (an internal change)
* **digichat:** session model picker, gated by the tenant allowlist (an internal change)
* **digichat:** prompt translation, inline citations and identity paragraphs in the client system
  prompt (an internal change)
* **ticket-mcp:** the transport security guard now matches a bare `Host` as well as `host:*` (an internal change)

### Bug Fixes

* **digichat:** the grounding tool is advertised as `digisearch`, not `digisearch_semantic` (an internal change)
* **digigraph:** a per-tool toggle now also matches a tool whose registered name keeps its
  camelCase (an internal change)

## [2.4.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.3.2...digichat-v2.4.0) (2026-09-29)


### Features

* **digichat:** searchEngine pref with tenant default and header forward (d8471ec)
* **digigraph:** enforce hosted license scopes at edge (69ca080)
* **digichat:** container license verification + 24h heartbeat + healthz (916c4b5)
* **digichat:** shared branding credit + catalog/product/embed parity (abe2892)
* **digichat:** serve /embed through the single route via internal rewrite (single-route option B) (0a5ac15)
* **digichat:** shim /baseline to /?mode=catalog, keep /embed direct (single-route step 5) (ef99803)
* **digichat:** mode-aware proxy for single-route framing and no-store (single-route step 4) (9c1a67d)
* **digichat:** bare / renders a mode menu instead of the product chat (7f1cfe4)
* **digichat:** single route / with ?mode= plus unified footer behavior (single-route step 3) (02b579b)
* **dashboard:** branded invite signup banner for team invite links (51ebe31)
* **ui:** add the document grammar and the install-command block (an internal change, an internal change) (63316da)
* **digichat:** surface provider built-in web search and citations (an internal change) (609d453)
* **digichat:** add the langgraph, ag-ui and a2a backends (43bd2e4)
* **digichat:** add the anthropic and google-vertex AI-SDK backends (4c33771)
* **digichat:** add openai-compatible AI-SDK backends (e16c625)
* **digichat:** let embed tenants set the feature flags and seed language (701e1b6)
* **digichat:** make chrome.mode modal and sidebar real presentation surfaces (cc3d240)
* **digichat:** drive a release install from one digichat.yaml (27ec4ef)

### Bug Fixes

* **digichat:** build canvas caret font from longhands so measurement uses the real font (be447d8)
* **digichat:** measure composer block caret in pixels so it tracks typing (db61b61)
* **digichat:** cold-boot 503 retries with Retry-After and warming-up state (37414ea)
* **digichat:** wire searchEngine send leg and unset semantics (review-4737) (4fc61d8)
* **digichat:** address license-heartbeat review findings (5) (ced8a15)
* **review:** refresh stale Footer slot comment + record PR #4636 in-session review (an internal change) (4612386)
* **ci:** clear PR gates after the module merge (ea26fb7)
* **digichat:** restore default skin footer/credit behavior (owner: keep defaults, message-only change) (81324eb)
* **digichat:** restore default skin footer layouts (undo 45fd09c41) (8d74969)
* **digichat:** pin the credit to the viewport bottom in all remaining skins (45fd09c)
* **digichat:** borderless symmetric thread footer credit on all skins (ba58d37)
* **digichat:** pin the credit to the page bottom in the empty-state skins (1ad29fa)
* **digichat:** guarantee the product credit, fix the / 500 and the invisible caret (an internal change) (e06cef2)
* **digichat:** make the credit legible, attribution-aware and boot-visible (e87d6da)
* **digichat:** guarantee the product credit, fix the / 500 and the invisible caret (0fe827c)
* **digichat:** close the non-AI-SDK backend review findings (9ee8a61)
* **digichat:** keep stream usage on the openai-compatible backend (3594ca4)
* **digichat:** surface reasoning from openai-compatible backends (37a6cc2)
* **digichat:** close the anthropic/vertex review findings (25a914b)
* **digichat:** close the AI-SDK backend review findings (0eedf9c)
* **digichat:** carry the embed feature flags through the loader bridge (c8132bc)
* **digichat:** tighten the backend-registry review findings (c9e0637)
* **digichat:** close the presentation-modes review findings (e36f69c)
* **digichat:** close the session-path review findings (962a97e)
* **digichat:** honour the deployment config on the authenticated-session path (392caba)
* **digichat:** close the /baseline parity review findings (6e4974e)
* **digichat:** make the /baseline catalog render the first-party skin like /embed (1bed163)
* **digichat:** keep the top anchor fully pinned after the scroll gate change (ba8c715)
* **digichat:** gate the scroll-to-bottom button on content hidden under the composer (e15cf1d)
* **digichat:** charge the free-turn counter at send time so it stops lagging a turn (an internal change) (44de2d0)

### Performance Improvements

* **digichat:** per-skin React.lazy code-splitting (WS4 step 5) (1ef394c)

## [2.3.2](https://github.com/digithings-ai/digithings/compare/digichat-v2.3.1...digichat-v2.3.2) (2026-09-21)


### Bug Fixes

* **digichat:** the embed Send button submits the composer form, so the free-turn gate sees it (an internal change) (b28c3af)

## [2.3.1](https://github.com/digithings-ai/digithings/compare/digichat-v2.3.0...digichat-v2.3.1) (2026-09-20)


### Bug Fixes

* **digichat:** the embed paints one canvas token from the first byte (an internal change) (dea7717)

## [2.3.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.2.0...digichat-v2.3.0) (2026-09-19)


### Features

* **digichat:** config-driven welcome copy, pre-painted theme frame canvas, boot chain yields on warm nav (an internal change) (4f0991d)
* rebuild digithings.ai + digiquant.io from the design reference (an internal change) (b1f1c72)
* **ui:** kit-level pointer cursors, guard enforcement (an internal change) (b007747)
* **ui:** logical properties and RTL support, canon proof route (an internal change) (2b2a1c5)
* **ui:** promote slider, empty-state, skeleton, radio-group, field, icon-button, segmented-control into the kit (an internal change) (371939b)

## [2.2.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.1.0...digichat-v2.2.0) (2026-09-16)


### Features

* **chat:** render upstream failures as a retryable error card (e7278fd)
* **chat:** render upstream failures as a retryable error card (56fe9fd)
* **digichat:** configurable view modes (hidden/compact/balanced/detailed) + 3-mode thinking override (cec11ac)
* **digichat:** curated embed welcome copy + suggestion pools for client and digithings.ai (a1981c1)
* **digichat:** Gloomberb attribution line for tool results (an internal change) (e733165)
* **digichat:** render Gloomberb attribution in the vendored tool fallback (an internal change) (5c2f657)
* **digichat:** wire Gloomberb attribution into the stock tool fallback (an internal change) (f6f1be2)
* **mcp:** close out PR an internal change follow-ups (web_search gate, vault search_notes + write gate, per-server edge keys, id validation, docs) (5453696)
* **mcp:** close out PR an internal change follow-ups (web_search gate, vault search_notes, per-server edge keys, id validation, docs) (1189661)
* **mcp:** config-driven hosted digisearch/digivault MCP + clean {server}_{verb} tool names (59b2396)
* **mcp:** config-driven hosted MCP servers for embeds + single-underscore MCP tool names (b637ccb)


### Bug Fixes

* **digichat:** forward operator MCP setup from the env tenant registry (f7a0d23)
* **digichat:** seat the painted block caret on the compact composer line box (9ce970a)
* **digichat:** seat the painted block caret on the compact line box (02d7cfa)
* **mcp:** review follow-ups — digivault path_prefix, session view/thinking tools, web-search opt-in (an internal change/an internal change/an internal change) (dd72667)
* **review follow-ups:** harden web-search error paths and reload turn mode (90953af)
* **review follow-ups:** harden web-search error paths and reload turn mode (5362be7)
* **review follow-ups:** pin paging slice, guard error-card types, scrub scheme-less userinfo, pin attribution collision (fca20ce)

## [2.1.0](https://github.com/digithings-ai/digithings/compare/digichat-v2.0.0...digichat-v2.1.0) (2026-09-16)


### Features

* **dashboard:** FX-Hub-only single view for FX Hub invitees + digichat proof for fx_hub grantees (ea47a81)
* **dashboard:** FX-Hub-only single view for FX Hub invitees + digichat proof for fx_hub grantees (8fbc332)
* **digichat:** base assistant-ui parity, timing diagnostics, silent page context, focus fixes (2b3fa66)
* **digichat:** base assistant-ui parity, timing diagnostics, silent page context, focus fixes (d33fe83)
* **digichat:** client evaluation embed — used/limit counter, single-row Foundry tool calls, painted block caret (2501bec)
* **digichat:** painted terminal block caret in tenant accent (hide native slim caret) (5c2d6c3)
* **digichat:** painted terminal block caret in tenant accent (hide native slim caret) (7d05c8d)
* **digichat:** show remaining free/evaluation question counter on evaluation_form embeds (6fea518)
* **website:** surface Gloomberb deep links + attribution in dashboard and digichat (an internal change) (an internal change) (be5f3fe)
* **zammad:** expose the in-stack MCP over a secret-gated edge path (6029775)
* **zammad:** reach the in-stack MCP over a secret-gated edge path (4f4c938)
* **zammad:** read-only ticket MCP for the client help chat (2c496f7)
* **zammad:** read-only ticket MCP for the client help chat (8a1ff22)


### Bug Fixes

* **digichat:** align + track the block caret, brighten branch-picker cubes, blend the default attribution footer (321419f)
* **digichat:** caret alignment + tracking, branch-picker cube chrome, blended default attribution footer (61e05dc)
* **digichat:** carry operator MCP servers through the env tenant registry (50312e2)
* **digichat:** carry operator MCP servers through the env tenant registry (b504ca4)
* **digichat:** fail an effectively empty digigraph 200 stream (a0b2427), closes an internal change
* **digichat:** fail closed on unconfigured/unmatched embed defaults (296dd3e), closes an internal change
* **digichat:** key the light shell token on [data-theme] only (f3f8611)
* **digichat:** mark unreturned streamed tool rows failed, not completed (8c55d65)
* **digichat:** mark unreturned streamed tool rows failed, not completed (252a28a), closes an internal change
* **digichat:** render isError tool rows as failed, not success (bed350c)
* **digichat:** restore dropped wide-mode brace + scope the credit strip paint (703d5f8)
* **digichat:** single tool row per Foundry search call, suppress late annotation row; counter hugs composer, borderless attribution (3ad06d0)
* **digichat:** surface upstream failures as stream errors, not fake replies (8034b71)
* **digichat:** surface upstream failures as stream errors, not fake replies (3d44651), closes an internal change
* **digichat:** treat X-Digi-Mcp-* headers as credentials in redirect guard (f1a1396)
* **digichat:** treat X-Digi-Mcp-* headers as credentials in redirect guard (dba8486), closes an internal change
* **digichat:** evaluation counter counts up (used/limit) per pre-2.0 client flow (e27a9de)
* **digigraph:** scope SSE usage totals per stream, not process-global (9580edc)
* **digigraph:** scope SSE usage totals per stream, not process-global (b6d6d69), closes an internal change
* **root:** require compose secrets, disable workers.dev default (an internal change) (an internal change) (12568b4)

## [2.0.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.5.0...digichat-v2.0.0) (2026-09-08)


### ⚠ BREAKING CHANGES

* assistant-ui Thread + AI SDK v7 is the product UI. DigiChatSession is gone; parents stay iframe-only into `/embed`.
* `chrome.skin: digichat` is the digithings.ai / client / dashboard dogfood skin. Page context is a `page-context.html` document chip, not a prompt-prefix-only UX.


### Features

* **digichat:** assistant-ui + AI SDK v7, product skin, tool catalog, page-context attachment (an internal change)

## [1.5.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.4.0...digichat-v1.5.0) (2026-09-05)


### Features

* **dashboard:** ask digichat chrome, expand, HTML page context (an internal change) (2d6af38)
* **dashboard:** ask digichat chrome, expand, HTML page context (an internal change) (bad5a8f)
* **digichat:** add conversation sidebar search filter (an internal change) (2012c45)
* **digichat:** conversation sidebar search (an internal change) (6ccd72a)
* **digichat:** copy turns as markdown with embed-safe fallback (an internal change) (0b20d4f)
* **digichat:** copy turns as markdown with embed-safe fallback (an internal change) (91a5b40)
* **digichat:** last-turn regen + edit on digigraph (an internal change) (5c83a67)
* **digichat:** last-turn regen + edit on digigraph (an internal change) (716039e)
* **digichat:** opt-in web search via digigraph+digillm (an internal change) (e4fc1b9)
* **digichat:** opt-in web search via digigraph+digillm (an internal change) (299f794)
* **digichat:** popup widget embed (dot/bar) + page context (an internal change) (78d5248)
* **digichat:** popup widget launcher with optional page context (an internal change) (739abe2)
* **digichat:** slash palette for websearch, settings, BYOK (4715a7c)
* **digichat:** slash palette for websearch, settings, BYOK (an internal change) (5be95d2)
* **digichat:** thursday demo pack — embed harness, slash, originals (an internal change) (1be8104)
* **digichat:** turn mutation API for digigraph and Foundry (an internal change) (f2f2ea5)
* **digichat:** turn mutation API for digigraph and Foundry (an internal change) (c3a391b)
* **digiweb:** frontend polish phase 1 + wave-1/2 component promotions (a8306c5)
* **digiweb:** wave-4 consume shared primitives in product apps (d3c8a34)
* **frontends:** design polish phases 1-3 — staleness sweep, 11 shared primitives, per-site consistency (0da3f41)
* **frontends:** wave-5 dead-code deletion across three apps (02b8205)
* **frontends:** wave-7 keyboard, shared transcript, hydration fix (2568f20)


### Bug Fixes

* **dashboard:** light the linked tab on deep links; drop embed page-context banner (an internal change) (75fc586)
* **dashboard:** scrub hidden/password values from page HTML context (149c25d)
* **digichat:** align Foundry items.delete with OpenAI SDK arity (an internal change) (38105fe)
* **digichat:** align popup page-context caps and send paths (an internal change) (a7cf098)
* **digichat:** clear lint setState-in-effect on palette index (6c0fc69)
* **digichat:** define page-context helper before BYOK effects (an internal change) (7bee1a4)
* **digichat:** drop a hidden page-context root before serialize (426cf73)
* **digichat:** fail-closed digigraph-only turn mutation chrome (138b5c7)
* **digichat:** narrow Foundry turnMode for TypeScript (an internal change) (edd9b36)
* **digichat:** palette Enter submit + preserve lang dive-in highlight (ad8b441)
* **digichat:** replace QR favicon with D-in-block brand mark (3d7012d), closes an internal change
* **digichat:** sanitize embed page-context with a DOM allowlist (aa1c9c1)
* **digichat:** sanitize embed page-context with a DOM allowlist (an internal change) (7aa5396)
* **digichat:** sync OpenAPI and tenant-config fixtures for webSearch (an internal change) (9fbb706)
* **digichat:** update embed-ui-flags expectations for webSearch (an internal change) (3a77eb4)
* **digichat:** web_search opt-in must not escalate allowlist (an internal change) (49c7572)
* **review:** address in-session review findings (3017ef0)
* **root:** hatch a commit that has no source pull request (an internal change) (1ab152a)


### Performance Improvements

* **root:** faster review-coverage check + retire greek package paths (304cb6c)

## [1.4.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.3.2...digichat-v1.4.0) (2026-09-02)


### Features

* **digichat-ui:** zero-radius ink/paper composer chrome (6291cd3)
* **digichat:** inherit utilitarian-terminal v0.1 chrome (42b93e0)
* **digiweb:** utilitarian terminal blend — Phase 0 canon promotion (4641acf)


### Bug Fixes

* close remaining an internal change BYOK low-risk follow-ups (an internal change) (6b3b922)
* **digichat:** add byok_model_provider_mismatch to remediable codes (an internal change) (6c9f708), closes an internal change
* **digichat:** align embed server theme with referer host (an internal change) (fb278e9)
* **digichat:** drop BYOK upstream messages on digigraph_error SSE (an internal change) (an internal change) (5a1e199)
* **digichat:** gate forwarded rate-limit IPs (an internal change) (59319d2)
* **digichat:** harden BYOK models route error and rate-limit responses (5a18f66), closes an internal change
* **digichat:** harden BYOK models route error and rate-limit responses (an internal change) (4169212), closes an internal change
* **digichat:** promote reviewed task fixes (baa7766)
* **digichat:** reopen BYOK panel when key is bound (an internal change) (9590c54)
* **digichat:** stop stale localStorage from wiping server history (an internal change) (93eba59)

## [1.3.2](https://github.com/digithings-ai/digithings/compare/digichat-v1.3.1...digichat-v1.3.2) (2026-08-21)


### Bug Fixes

* **byok:** kill a dead auth argument and a refusal that named the wrong model (an internal change) (337ff56)
* **byok:** strip the refusal example, and stop a parenthetical crashing startup (an internal change) (98d7a49)

## [1.3.1](https://github.com/digithings-ai/digithings/compare/digichat-v1.3.0...digichat-v1.3.1) (2026-08-20)


### Bug Fixes

* **digichat:** tell an embed visitor a BYOK refusal is fixable (an internal change) (0e23a37)
* **digigraph:** close findings from the independent review of an internal change (cc5accf)
* **digigraph:** correct the "same string" claim and cover the production trace path (an internal change) (7f4ff15)
* **digigraph:** refuse a bound BYOK key the deployment default would not spend (an internal change) (dc0fd59)

## [1.3.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.2.0...digichat-v1.3.0) (2026-08-15)


### Features

* **digichat:** BYOK provider/model catalog + live model list at key step (an internal change) (330a4a0)


### Bug Fixes

* address remaining CodeRabbit findings from the an internal change re-review (1d250c7)
* **digichat:** prefix the BYOK models fetch with the app base path (an internal change) (535a5a9)

## [1.2.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.1.0...digichat-v1.2.0) (2026-08-13)


### Features

* **digichat,digiweb:** bring mermaid/code-block rendering to the primary chat page (98c41d4)
* **digichat,digiweb:** bring mermaid/code-block rendering to the primary chat page (f6ecb04), closes an internal change
* **digigraph:** make the chat agentic — model-driven retrieval, locate-then-load, enforced tenant scope (an internal change) (15940d9)
* **digigraph:** promote agentic chat to develop (155cbcb)
* **digigraph:** promote agentic chat to develop (an internal change) (155cbcb)


### Bug Fixes

* 2 P0 findings from full-UI-suite impeccable critique (invisible button text + free-turn-on-error) (5e37663)
* Controls (/controls) findings from the full-UI-suite critique (bc838a1)
* **digichat:** assign locked-contact mailto: href client-side (an internal change) (an internal change) (dd42166)
* **digichat:** do not map digivault batch errors as hit counts (708a870)
* **digichat:** don't spend a free embed turn on a failed/errored send (95c6b93), closes an internal change
* **digichat:** mark a truncated activity snippet with an ellipsis (7617f8a)
* **digichat:** mark a truncated activity snippet with an ellipsis (8243245), closes an internal change
* **digichat:** split a round's narration from the final answer on round_boundary (04940a3)
* **digichat:** split a round's narration from the final answer on round_boundary (028a835)
* **digiweb:** Controls page findings — money-color reuse, dropdown focus loss, unlabeled toggle (e5d12ce), closes an internal change an internal change

## [1.1.0](https://github.com/digithings-ai/digithings/compare/digichat-v1.0.0...digichat-v1.1.0) (2026-08-11)


### Features

* **digichat:** add curated language list + browser detection (an internal change) (996e2d7)
* **digichat:** add LanguageSelect dropdown component (an internal change) (7a344c6)
* **digichat:** forward response language as X-Digi-Language header (an internal change) (cded3ac)
* **digichat:** forward response language to both backend adapters (an internal change) (e725130)
* **digichat:** Foundry adapter prepends response-language directive (an internal change) (14d6201)
* **digichat:** language selector — digigraph + Foundry (an internal change) (e7a92c7)
* **digichat:** render language selector in embed header (an internal change) (e54a99b)
* **digichat:** thread showLanguageSelector through tenant config (an internal change) (cfe092f)


### Bug Fixes

* address CodeRabbit findings for promote an internal change (an internal change) (d0f4270)
* **digichat:** admit embed BYOK ping without DigiChat session (an internal change) (ef1f41f)
* **digichat:** allow local http parents for embed iframes (an internal change) (287ab38)
* **digichat:** full-height embed, client ready origin, parent theme sync (an internal change) (e1288f2)
* **digichat:** read response language at send time, not mount (an internal change) (7d6d8ee)
* **digichat:** relax exact react/react-dom pin to fix duplicate install (cdca505)
* **digichat:** relax exact react/react-dom pin to fix duplicate install (a26f8d4)
* **digichat:** session-only BYOK via inline terminal flow (an internal change) (9ece6ee)
* **digichat:** style and right-align the LanguageSelect trigger (an internal change) (eab55c1)
* **digigraph:** preserve multi-turn chat history in workflow prompt (an internal change) (9849a8f)
* full-bleed digichat overlay + nav polish for /chat, /chat/client (an internal change) (183f2e0)

## [1.0.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.3...digichat-v1.0.0) (2026-08-10)


### Features

* **digichat:** digigraph-centric adapters and digithings.ai cutover (an internal change) (573b815)
* **digichat:** digithings dogfood completion (6bd3a9d)
* **digichat:** Profile A/B overlays + self-hosted install/deploy docs (Tasks 3–8) (an internal change) (1993606)
* **digichat:** runtime CSP frame-ancestors for stock GHCR (an internal change) (2c30ee4)
* **digichat:** simplify embed gate for dogfood slice 1 (4d05075), closes an internal change
* **digithings:** dogfood cutover — client an internal change onboard + auth Option A (an internal change) (df14c20)
* free-tier digithings LLM + BYOK (digigraph + digichat) (an internal change) (0f0498e)
* **client:** client an internal change chat at digithings.ai/chat/client (209a870)
* **client:** client an internal change chat demo with corpus routing (4f7f5c3)


### Bug Fixes

* **digichat,digigraph:** prefer-const and ruff format for dogfood CI (db4b325)
* **digichat:** embed dogfood contrast and ungated error UX (6fee5e3)
* **digichat:** hide bare graph_update from activity chain (e419830)
* **digichat:** opt out of OpenWebUI chrome for dogfood stream (ea725b2)
* **digichat:** readable Sources rows for dogfood RAG traces (899b802), closes an internal change
* **digichat:** remove unused status bar chrome (7959f4d)
* **digichat:** restore wordmark header without status bar (2f4fec8)
* **digiquant:** Nautilus image + digichat self-hosted docs follow-up (an internal change) (bb14aec)
* **dogfood:** clean answer prose and force dual-sink retrieval (c1aa684)

## [0.9.3](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.2...digichat-v0.9.3) (2026-08-08)


### Bug Fixes

* **digichat:** flush FoundryToolLeakFilter's held buffer at stream end (an internal change) (605d9bd)
* **digichat:** resolve embed tenant theme server-side to kill the load flash (an internal change) (5284970)

## [0.9.2](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.1...digichat-v0.9.2) (2026-08-08)


### Bug Fixes

* **chat:** mermaid diagrams with punctuation in node labels now render instead of falling back to source (an internal change)

## [0.9.1](https://github.com/digithings-ai/digithings/compare/digichat-v0.9.0...digichat-v0.9.1) (2026-08-07)


### Features

* **digichat:** map Foundry azure_ai_search activity into the shared digichat chain


### Bug Fixes

* **digichat:** progressive tool stream + bare wait caret; fourth-turn evaluation form polish (an internal change)

## [0.9.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.8.0...digichat-v0.9.0) (2026-08-07)


### Features

* **chat:** ship the house type-out as digichat's waiting state (c98ceab)
* **chat:** ship the house type-out as digichat's waiting state (3656503)
* **digichat:** unify the chat UI — canon transcript, mermaid/LaTeX, centred embed (ead37ba)


### Bug Fixes

* **chat:** repair what the in-session review of an internal change found (ab54c67)
* **design-system:** scope KaTeX to math-rendering apps, and correct what an internal change and an internal change claimed (an internal change) (286fc87)

## [0.8.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.7.0...digichat-v0.8.0) (2026-08-06)


### Features

* **digichat-ui:** render the canon transcript grammar in the embed — tool chain, reasoning, sources
* **digiweb:** render mermaid and LaTeX in the shared chat markdown
* **digichat:** centre the embed transcript instead of running it full-bleed

## [0.7.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.6.0...digichat-v0.7.0) (2026-08-06)


### Features

* **digichat:** accept and store the chat access token from the unlock message
* **digichat:** send the chat access token at request time
* **digichat:** add an optional per-tenant quota gate config
* **digichat:** enforce chat quota server-side when a tenant configures a gate

## [0.6.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.5.0...digichat-v0.6.0) (2026-08-05)


### Features

* **design-system:** retire the QR favicon for a terminal identity (an internal change) (7966e3b), closes an internal change
* **digichat:** add digichat ready/seed postMessage validators (30094d8)
* **digichat:** allow first-party digithings hosts without embed token (556d9a7)
* **digichat:** drive embed BYOK/status/layout from tenant flags (9dfe479)
* **digichat:** parse independent embed UI flags from tenant config (984c0d6)
* **digichat:** Phase 2 unification — digivault port + digigraph rich mapping (an internal change) (8f56e17)
* **digichat:** project embed UI flags through tenant-config API (e4373f0)
* **digichat:** scaffold digithings digichat on Cloudflare Containers (032493e)
* **digichat:** shared activity protocol (unification phase 1) (an internal change) (32f8e92)
* **digichat:** wire ready/seed protocol into embed session (2a6c075)
* **website:** Phase 3 Pages-native digichat-ui (no Containers) (eefac60)
* **website:** retire CF chat Function and native useStackChat stack (b54c73d)


### Bug Fixes

* **digichat:** accept readonly messages in embed seed (1767bf3)
* **digichat:** apply URL hex accent after mount on embed (an internal change) (720f96c)
* **digichat:** read embed token/host via useSearchParams (2763be4)
* **digichat:** read embed token/host via useSearchParams (5b167df)
* **digichat:** retarget Phase 3 embed to same-origin /embed (21ee786)
* **digichat:** send evaluation unlock header at request time (0daa626)
* **digichat:** send evaluation unlock header at request time (80e2f85)

## [0.5.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.4.1...digichat-v0.5.0) (2026-07-31)


### Features

* **digichat:** add evaluation_form gate mode and shared turn-limit constants (4a6706c)
* **digichat:** carry chat session id and questions on client:gated (f06cdf9)
* **digichat:** enforce evaluation_form gate in /api/chat (402, unlock flag, fail-open) (fb58be2)
* **digichat:** in-memory per-IP evaluation-turn quota (f86a03a)
* **digichat:** evaluation_form embed — postMessage gate/unlock handshake + unlock header (6004410)
* **digichat:** evaluation_form embed gate mode (4fcf107)


### Bug Fixes

* **digichat:** fall back to the contact card when the parent never answers the gate (e155c76)
* **digichat:** hold the server-side turn cap at the advertised 3 (bde4bfd)
* **digichat:** persist the evaluation unlock and harden the gate's failure modes (110d74c)
* **digichat:** post client:gated once per payload, not per stream chunk (6bb9d72)

## [0.4.1](https://github.com/digithings-ai/digithings/compare/digichat-v0.4.0...digichat-v0.4.1) (2026-07-19)


### Bug Fixes

* **digichat:** parse azure_ai_search's url_citation annotation shape (bf5bbe7)
* **digichat:** parse azure_ai_search's url_citation annotation shape (91caa0e), closes an internal change

## [0.4.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.3.0...digichat-v0.4.0) (2026-07-16)


### Features

* **digichat:** add foundry backend, retiring the orphaned relay Function (c1c10b7)
* **digichat:** add foundry backend, retiring the orphaned relay Function (7c9866a), closes an internal change

## [0.3.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.2.0...digichat-v0.3.0) (2026-07-12)


### Features

* **design:** canon post-merge batch — deck-at-rest, quiet surfaces, rules-only cleanup, the colophon (bee93aa)
* **design:** teal ruling + Motion package standardization (51ac2c8)
* **design:** the conformance pass — apply the six rulings to the apps (a2b68ce)
* **design:** the design canon, the 28-reference mine, and the ruled conformance pass (342d452)
* **digichat,digithings-web:** load chat-core/chat-widgets css (an internal change) (81d558b)
* **digichat:** client-safe embed tenant-config endpoint [an internal change] (890533e)
* **digichat:** config-driven embed gate/theme/accent/attribution [an internal change] (6e5744a)
* **digichat:** derive embed frame-ancestors from the tenant registry [an internal change] (b5237c7)
* **digichat:** embed markdown rendering, activity box, relay conversation continuity [an internal change] (8c4b9dd)
* **digichat:** embed tenant registry from DIGICHAT_EMBED_TENANTS env [an internal change] (830f647)
* **digichat:** external-relay SSE stream adapter [an internal change] (8b8eea0)
* **digichat:** flip theme onto [data-theme] via shared ThemeProvider (425a941)
* **digichat:** pluggable external backends + ungated mode for /embed (57c7fb3)
* **digichat:** promote 0.1.1 embed UI release to main (an internal change) (dda37a9)
* **digichat:** resolve embed tenants from the registry in /api/chat context [an internal change] (08cdefa)
* **digichat:** reverse the token bridge — shadcn vars derive from canon tokens (32c8db8)
* **digichat:** route external-relay embed tenants through the relay adapter [an internal change] (50d82dc)
* **digichat:** shared embed UI for clientStream iframe (an internal change) (76808eb)
* **digichat:** swap ui/* to thin re-exports of @digithings/ui controls (an internal change) (7079da4)
* **digichat:** terminal-style embed chat matching digithings.ai/chat idiom [an internal change] (f596d0b)
* **digiweb:** create frontend design-suite module (reference + agent surface + tailwind bridge) (c8072de)
* **frontend:** canon ratchet — CI guard, MIGRATION.md, skill update (a73bafe)


### Bug Fixes

* **digichat:** §16 conformance — tool chips wear the accent, semantics use tokens (a15ca84)
* **digichat:** BYOK test error rides --down, not digikey's livery (§16) (0cfa709)
* **digichat:** dedupe relay's terminal full-text re-emit in embed answers (an internal change) (48b043b)
* **digichat:** Dockerfile @digithings/ui copy, embed theme override, relay dedup (an internal change) (6f5f67e)
* **digichat:** Dockerfile @digithings/ui copy, embed theme override, relay dedup (Part of an internal change) (595cc3d)
* **digichat:** drop misleading EMBED_FRAME_ANCESTORS compat export [an internal change] (42df93a)
* **digichat:** embed polish — pinned input, dead copy button, duplicated traces (an internal change) (8209e26)
* **digichat:** include digichat-ui workspace in Docker build (an internal change) (b61424a)
* **digichat:** make digigraph/digiquant/digismith health checks optional (94db2a9)
* **digichat:** make digigraph/digiquant/digismith health checks optional (6971d32), closes an internal change
* **digichat:** make embed light theme override the app-level dark class [an internal change] (41ffd13)
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps (69d14d4)
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps (343b826), closes an internal change
* **digichat:** propagate the rose livery split into the live app theme (6ac3502), closes an internal change
* **digichat:** read embed token/host from URL at send time (an internal change) (91d1cd9)
* **digichat:** require per-tenant token for embed registry resolution (a7f31cd)
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build (83d1d73)
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build (9363398), closes an internal change
* **digichat:** stop embed host resolution from claiming its own origin (41d0c2b)
* **digichat:** stop embed host resolution from claiming its own origin (eb10fa1), closes an internal change
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services (dcfaa22)
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services (0fbacac)
* **digichat:** type-safe embedConfig narrowing for the relay branch [an internal change] (00f4180)
* **frontend:** hero/nav clearance, TerminalManifest aria-pressed, digichat dev CSP (an internal change) (ff93649)
* **frontend:** hero/nav clearance, TerminalManifest aria-pressed, digichat dev CSP (Part of an internal change) (b109ad6)

## [0.2.0](https://github.com/digithings-ai/digithings/compare/digichat-v0.1.0...digichat-v0.2.0) (2026-07-07)


### Features

* **design:** canon post-merge batch — deck-at-rest, quiet surfaces, rules-only cleanup, the colophon (bee93aa)
* **design:** teal ruling + Motion package standardization (51ac2c8)
* **design:** the conformance pass — apply the six rulings to the apps (a2b68ce)
* **design:** the design canon, the 28-reference mine, and the ruled conformance pass (342d452)
* **digichat:** client-safe embed tenant-config endpoint [an internal change] (890533e)
* **digichat:** config-driven embed gate/theme/accent/attribution [an internal change] (6e5744a)
* **digichat:** derive embed frame-ancestors from the tenant registry [an internal change] (b5237c7)
* **digichat:** embed markdown rendering, activity box, relay conversation continuity [an internal change] (8c4b9dd)
* **digichat:** embed tenant registry from DIGICHAT_EMBED_TENANTS env [an internal change] (830f647)
* **digichat:** external-relay SSE stream adapter [an internal change] (8b8eea0)
* **digichat:** per-IP rate limiting on the anonymous /embed chat path (c452f68)
* **digichat:** per-IP rate limiting on the anonymous /embed chat path (5707ae9), closes an internal change
* **digichat:** pluggable external backends + ungated mode for /embed (57c7fb3)
* **digichat:** product-as-hero /welcome marketing route + CodeSampleBand (an internal change) (50a55e1)
* **digichat:** product-as-hero /welcome marketing route + CodeSampleBand [an internal change] (fc94366)
* **digichat:** resolve embed tenants from the registry in /api/chat context [an internal change] (08cdefa)
* **digichat:** route external-relay embed tenants through the relay adapter [an internal change] (50d82dc)
* **digichat:** shared embed UI for clientStream iframe (an internal change) (76808eb)
* **digichat:** terminal-style embed chat matching digithings.ai/chat idiom [an internal change] (f596d0b)
* **digiquant:** DB calibration sync and tearsheet UX overhaul (4357523), closes an internal change
* **digiquant:** DB calibration sync, tearsheet refresh, and digiquant-web landing polish (f060458)


### Bug Fixes

* **digichat:** §16 conformance — tool chips wear the accent, semantics use tokens (a15ca84)
* **digichat:** BYOK test error rides --down, not digikey's livery (§16) (0cfa709)
* **digichat:** dedupe relay's terminal full-text re-emit in embed answers (an internal change) (48b043b)
* **digichat:** drop misleading EMBED_FRAME_ANCESTORS compat export [an internal change] (42df93a)
* **digichat:** embed polish — pinned input, dead copy button, duplicated traces (an internal change) (8209e26)
* **digichat:** include digichat-ui workspace in Docker build (an internal change) (b61424a)
* **digichat:** make digigraph/digiquant/digismith health checks optional (94db2a9)
* **digichat:** make digigraph/digiquant/digismith health checks optional (6971d32), closes an internal change
* **digichat:** make embed light theme override the app-level dark class [an internal change] (41ffd13)
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps (69d14d4)
* **digichat:** pass DIGICHAT_EMBED_TENANTS at Docker build time, fix musl native deps (343b826), closes an internal change
* **digichat:** require per-tenant token for embed registry resolution (a7f31cd)
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build (83d1d73)
* **digichat:** split non-secret embed hostnames from DIGICHAT_EMBED_TENANTS at build (9363398), closes an internal change
* **digichat:** stop embed host resolution from claiming its own origin (41d0c2b)
* **digichat:** stop embed host resolution from claiming its own origin (eb10fa1), closes an internal change
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services (dcfaa22)
* **digichat:** treat explicit empty DIGICHAT_ENABLED_SERVICES as zero services (0fbacac)
* **digichat:** type-safe embedConfig narrowing for the relay branch [an internal change] (00f4180)


### Reverts

* **frontend:** undo epic an internal change landing redesign per design review [an internal change] (05a9a9d)
* **frontend:** undo epic an internal change landing redesign per design review [an internal change] (bea43d7)
