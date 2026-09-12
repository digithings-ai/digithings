# assistant-ui elements catalog

Canonical index of every public [assistant-ui element](https://www.assistant-ui.com/elements).
This is the **library**: discover here, fetch from the registry when a deploy
needs it. Do **not** vendor all ~120 cards into digichat or digiweb.

digichat is the BFF (auth, stream, deploy YAML). digiweb is the frontend suite.
Product Thread copies live in `@digithings/web/chat/thread` (gallery
`thread.aui.tsx` + slots). Gallery `/chatbot` imports that same module.
This file is the single map — do not duplicate the table in digichat.

## How to fetch

digichat `components.json` already registers:

```json
"@assistant-ui": "https://r.assistant-ui.com/styles/{style}/{name}.json"
```

Style pin: **base-nova**. From `cloudflare/digichat/` (or the gallery app with the
same registry):

```bash
npx shadcn add @assistant-ui/<slug>
```

Docs / MCP: `read_page` with path `/elements/<slug>` (assistant-ui MCP), or open
`https://www.assistant-ui.com/elements/<slug>`.

Primitives already ship in `@assistant-ui/react` — many cards are styled
compositions of those primitives.

## Attach kinds

| Kind | Meaning |
| ---- | ------- |
| **in gallery** | Fixture `/chatbot` page mounts `@digithings/web/chat/thread` (not a second copy) |
| **in product** | Copied under digichat `src/app/(baseline)/stock/` (or slotted inside that Thread) |
| **part-driven** | Shows when the AI SDK / digigraph stream emits the matching part |
| **chrome-driven** | Shows when deploy YAML (`features.*` / `tools.catalog` / `gate.*`) enables it |
| **on demand** | Not copied yet — `shadcn add` when a deploy needs it |

BYOK is `gate.showByok` (not a catalog element). Browser-side user MCP
(`mcp-config`, `mcp-server-panel`, elicitation) is a **human gate** before
production enable.

When copying for product: land in `(baseline)/stock/`, slot into
`thread.aui.tsx`, and import the **same** renderer from DigichatThread — no
third tree. Gallery `/chatbot` stays the digichat **skin** lab on the
product Thread module; it does not host this catalog as live specimens.

## Catalog

| Slug | What it is for | Fetch | Attach | Notes |
| ---- | -------------- | ----- | ------ | ----- |
| [`activity-graph`](https://www.assistant-ui.com/elements/activity-graph) | A half-year of runs as a calendar of cells, dense where the work was. | `npx shadcn add @assistant-ui/activity-graph` | on demand | — |
| [`agent-card`](https://www.assistant-ui.com/elements/agent-card) | Who you are about to talk to: its skills, its model, and the endpoint behind it. | `npx shadcn add @assistant-ui/agent-card` | on demand | — |
| [`agent-handoff`](https://www.assistant-ui.com/elements/agent-handoff) | Control passing between agents, with the reason and what came along. | `npx shadcn add @assistant-ui/agent-handoff` | part-driven | digigraph multi-agent handoff part |
| [`agent-plan`](https://www.assistant-ui.com/elements/agent-plan) | A checklist the agent works through, with progress you can glance. | `npx shadcn add @assistant-ui/agent-plan` | part-driven | — |
| [`agent-status`](https://www.assistant-ui.com/elements/agent-status) | One pill that always answers: what is it doing, and for how long. | `npx shadcn add @assistant-ui/agent-status` | part-driven | — |
| [`approval-card`](https://www.assistant-ui.com/elements/approval-card) | Human in the loop: the agent asks before it runs anything with side effects. | `npx shadcn add @assistant-ui/approval-card` | part-driven | approval / interrupt UI |
| [`artifact-card`](https://www.assistant-ui.com/elements/artifact-card) | A generated document as a tangible object, written live and versioned. | `npx shadcn add @assistant-ui/artifact-card` | part-driven | — |
| [`assistant-modal`](https://www.assistant-ui.com/elements/assistant-modal) | A floating chat bubble for support widgets, help desks, and embedded assistants. | `npx shadcn add @assistant-ui/assistant-modal` | on demand | webpage-assistant skin uses a related pattern; not this registry card |
| [`assistant-sidebar`](https://www.assistant-ui.com/elements/assistant-sidebar) | A resizable side panel for copilot experiences and contextual assistance. | `npx shadcn add @assistant-ui/assistant-sidebar` | on demand | — |
| [`attachment`](https://www.assistant-ui.com/elements/attachment) | Runtime attachments for the composer and messages, with previews, progress, and removal. | `npx shadcn add @assistant-ui/attachment` | in gallery · in product · chrome-driven | `features.attachments` |
| [`background-inbox`](https://www.assistant-ui.com/elements/background-inbox) | Work still going somewhere else, and the results waiting to be collected. | `npx shadcn add @assistant-ui/background-inbox` | on demand | — |
| [`canvas-split`](https://www.assistant-ui.com/elements/canvas-split) | The thread steps aside and the document takes the room, still being written as you read. | `npx shadcn add @assistant-ui/canvas-split` | on demand | — |
| [`chart`](https://www.assistant-ui.com/elements/chart) | Area, line, and bars, with points landing one at a time as the series streams in. | `npx shadcn add @assistant-ui/chart` | part-driven | prefer digiweb finance-charts for digiquant; this is the assistant-ui card |
| [`chat-panel`](https://www.assistant-ui.com/elements/chat-panel) | The whole family working together: a message, a pause, a streamed reply. | `npx shadcn add @assistant-ui/chat-panel` | on demand | demo composition; product uses Thread |
| [`checkpoint-history`](https://www.assistant-ui.com/elements/checkpoint-history) | Points you can fall back to, with what each one would give back. | `npx shadcn add @assistant-ui/checkpoint-history` | on demand | — |
| [`code-diff`](https://www.assistant-ui.com/elements/code-diff) | A unified diff with tinted additions and removals, sized for chat. | `npx shadcn add @assistant-ui/code-diff` | part-driven | — |
| [`code-runner`](https://www.assistant-ui.com/elements/code-runner) | A snippet with a run button, and the output it produced attached below it. | `npx shadcn add @assistant-ui/code-runner` | part-driven | — |
| [`command-palette`](https://www.assistant-ui.com/elements/command-palette) | Everything the app can do, one keystroke away and grouped by where it acts. | `npx shadcn add @assistant-ui/command-palette` | chrome-driven | digiweb has its own chrome command palette; this is assistant-ui's |
| [`comparison-card`](https://www.assistant-ui.com/elements/comparison-card) | Two options weighed side by side, with the pick named and argued. | `npx shadcn add @assistant-ui/comparison-card` | part-driven | — |
| [`composer-attachments`](https://www.assistant-ui.com/elements/composer-attachments) | Files stage inside the composer with per-file progress before the message sends. | `npx shadcn add @assistant-ui/composer-attachments` | in gallery · in product · chrome-driven | bundled with Thread attachment slots; `features.attachments` |
| [`composer-context`](https://www.assistant-ui.com/elements/composer-context) | A token ring in the rail fills as the conversation grows, warning near the limit. | `npx shadcn add @assistant-ui/composer-context` | chrome-driven | alias of context-display for composer rail |
| [`composer-mentions`](https://www.assistant-ui.com/elements/composer-mentions) | Type @ to pull people and agents into the conversation, filtered as you go. | `npx shadcn add @assistant-ui/composer-mentions` | chrome-driven | — |
| [`composer-model-picker`](https://www.assistant-ui.com/elements/composer-model-picker) | The model lives in the composer rail, one tap away with context at a glance. | `npx shadcn add @assistant-ui/composer-model-picker` | chrome-driven | `features.modelPicker` |
| [`composer-slash-commands`](https://www.assistant-ui.com/elements/composer-slash-commands) | Type a slash and the command menu floats above the input, filtering as you continue. | `npx shadcn add @assistant-ui/composer-slash-commands` | chrome-driven | digisearch `/` is the first candidate |
| [`composer-trigger-popover`](https://www.assistant-ui.com/elements/composer-trigger-popover) | A character-triggered picker for mentions, slash commands, and nested composer actions. | `npx shadcn add @assistant-ui/composer-trigger-popover` | chrome-driven | shared primitive under slash/mentions; the digichat skin's category copy is a deliberate exemption from the one-Thread-module rule (#3818) |
| [`composer-voice`](https://www.assistant-ui.com/elements/composer-voice) | The mic morphs the input into a live waveform, then lands the transcript as text. | `npx shadcn add @assistant-ui/composer-voice` | chrome-driven | `features.dictation` — Thread already has a Mic slot when enabled |
| [`composer`](https://www.assistant-ui.com/elements/composer) | The unified input: attachments, commands, mentions, models, voice, and context in one surface. | `npx shadcn add @assistant-ui/composer` | in gallery · in product | bundled inside Thread; do not mount a second standalone Composer |
| [`computer-use`](https://www.assistant-ui.com/elements/computer-use) | The screen the agent is driving, with a cursor trail and what it is doing right now. | `npx shadcn add @assistant-ui/computer-use` | part-driven | — |
| [`confidence-marker`](https://www.assistant-ui.com/elements/confidence-marker) | Which claims came from a source, which were inferred, and which are guesses. | `npx shadcn add @assistant-ui/confidence-marker` | part-driven | — |
| [`connection-state`](https://www.assistant-ui.com/elements/connection-state) | The socket drops, the run keeps going on the server, and the stream is picked back up. | `npx shadcn add @assistant-ui/connection-state` | chrome-driven | — |
| [`context-breakdown`](https://www.assistant-ui.com/elements/context-breakdown) | Where the window actually went: prompt, tools, files, conversation, and what's left. | `npx shadcn add @assistant-ui/context-breakdown` | chrome-driven | — |
| [`context-display`](https://www.assistant-ui.com/elements/context-display) | Model context usage as a ring, bar, or text value with a detailed hover view. | `npx shadcn add @assistant-ui/context-display` | chrome-driven | digichat skin may later map fill to cube matrix |
| [`conversation-search`](https://www.assistant-ui.com/elements/conversation-search) | Find inside a long thread, with every hit marked down the scrollbar. | `npx shadcn add @assistant-ui/conversation-search` | chrome-driven | — |
| [`cost-meter`](https://www.assistant-ui.com/elements/cost-meter) | What the run spent, split by model, against the session total. | `npx shadcn add @assistant-ui/cost-meter` | chrome-driven | — |
| [`data-table`](https://www.assistant-ui.com/elements/data-table) | A small comparison table the model can answer with directly. | `npx shadcn add @assistant-ui/data-table` | part-driven | — |
| [`day-separator`](https://www.assistant-ui.com/elements/day-separator) | Chronology in a long thread: days marked, times on hover. | `npx shadcn add @assistant-ui/day-separator` | chrome-driven | — |
| [`diagram`](https://www.assistant-ui.com/elements/diagram) | A drawn answer with zoom, reset, and a full-bleed view; you hand it the rendered graphic. | `npx shadcn add @assistant-ui/diagram` | part-driven | — |
| [`directive-text`](https://www.assistant-ui.com/elements/directive-text) | A message renderer that turns mention directives into inline, runtime-aware chips. | `npx shadcn add @assistant-ui/directive-text` | part-driven | — |
| [`document-reference`](https://www.assistant-ui.com/elements/document-reference) | A document the answer leans on, with the quoted passage and the page to jump to. | `npx shadcn add @assistant-ui/document-reference` | part-driven | digivault / digisearch citations |
| [`draft-restore`](https://www.assistant-ui.com/elements/draft-restore) | Come back to a thread and the sentence you never sent is still waiting. | `npx shadcn add @assistant-ui/draft-restore` | chrome-driven | — |
| [`edit-message`](https://www.assistant-ui.com/elements/edit-message) | Rewrite a turn in place, told up front how many replies the edit throws away. | `npx shadcn add @assistant-ui/edit-message` | in gallery · in product | Thread action bar Edit already present |
| [`elicitation-form`](https://www.assistant-ui.com/elements/elicitation-form) | A server pausing mid-tool-call to ask you for the fields it still needs. | `npx shadcn add @assistant-ui/elicitation-form` | part-driven | MCP elicitation; human-gate before production enable |
| [`empty-state`](https://www.assistant-ui.com/elements/empty-state) | The first screen: a greeting, three ways in, and the composer front and center. | `npx shadcn add @assistant-ui/empty-state` | on demand | duplicates composer — gallery uses Thread `components.Welcome` instead |
| [`error-state`](https://www.assistant-ui.com/elements/error-state) | A quiet failure banner with a retry path, not a modal in your face. | `npx shadcn add @assistant-ui/error-state` | in gallery · in product | Thread ErrorPrimitive slot |
| [`feedback-dialog`](https://www.assistant-ui.com/elements/feedback-dialog) | A thumbs-down that asks why, so the signal arrives with a reason attached. | `npx shadcn add @assistant-ui/feedback-dialog` | chrome-driven | pairs with message-actions thumbs |
| [`file-tree`](https://www.assistant-ui.com/elements/file-tree) | Everything a run touched, as a tree, with the churn spelled out per file. | `npx shadcn add @assistant-ui/file-tree` | part-driven | — |
| [`file`](https://www.assistant-ui.com/elements/file) | File message parts with type-aware icons, filename, size, and download actions. | `npx shadcn add @assistant-ui/file` | in gallery · in product · part-driven | — |
| [`flow-graph`](https://www.assistant-ui.com/elements/flow-graph) | Work as a graph rather than a list: branches that fan out and rejoin. | `npx shadcn add @assistant-ui/flow-graph` | part-driven | — |
| [`follow-up-suggestions`](https://www.assistant-ui.com/elements/follow-up-suggestions) | Prompt chips populated from the runtime's generated follow-up suggestions. | `npx shadcn add @assistant-ui/follow-up-suggestions` | in gallery · in product · part-driven | `chrome.suggestions` / runtime suggestions |
| [`generative-ui`](https://www.assistant-ui.com/elements/generative-ui) | A styled component library for rendering structured generative UI output. | `npx shadcn add @assistant-ui/generative-ui` | part-driven | — |
| [`guardrail-notice`](https://www.assistant-ui.com/elements/guardrail-notice) | A refusal in its own shape, with the nearest thing it can do instead. | `npx shadcn add @assistant-ui/guardrail-notice` | part-driven | — |
| [`heat-graph`](https://www.assistant-ui.com/elements/heat-graph) | An activity heat map with month labels, weekday labels, legend, and tooltip. | `npx shadcn add @assistant-ui/heat-graph` | on demand | related to activity-graph |
| [`image-generation`](https://www.assistant-ui.com/elements/image-generation) | A dot grid holds the frame while the image resolves out of a blur. | `npx shadcn add @assistant-ui/image-generation` | part-driven | — |
| [`image`](https://www.assistant-ui.com/elements/image) | Image message parts with preview, loading states, actions, and a fullscreen view. | `npx shadcn add @assistant-ui/image` | in gallery · in product · part-driven | — |
| [`inline-citation`](https://www.assistant-ui.com/elements/inline-citation) | Numbered references inside a sentence, each with a hover preview of its source. | `npx shadcn add @assistant-ui/inline-citation` | part-driven | pairs with `features.sources` |
| [`job-progress`](https://www.assistant-ui.com/elements/job-progress) | Work measured in minutes: weighted stages, an ETA, and a way out. | `npx shadcn add @assistant-ui/job-progress` | part-driven | — |
| [`launcher-bubble`](https://www.assistant-ui.com/elements/launcher-bubble) | The floating entry point, and the panel it opens into. | `npx shadcn add @assistant-ui/launcher-bubble` | on demand | product uses first-party DigichatLauncher in digiweb, not this card |
| [`loading-state`](https://www.assistant-ui.com/elements/loading-state) | A pixel matrix that keeps time while the model has nothing to show yet. | `npx shadcn add @assistant-ui/loading-state` | in gallery · part-driven | gallery forks DotMatrix; product Thread uses registry loader |
| [`logos`](https://www.assistant-ui.com/elements/logos) | Inline SVG marks for OpenAI, Anthropic, and Google model providers. | `npx shadcn add @assistant-ui/logos` | on demand | — |
| [`map-answer`](https://www.assistant-ui.com/elements/map-answer) | A location answer: pins, a route between them, and the list they came from. | `npx shadcn add @assistant-ui/map-answer` | part-driven | — |
| [`markdown-text`](https://www.assistant-ui.com/elements/markdown-text) | Assistant markdown with headings, lists, links, tables, and code blocks. | `npx shadcn add @assistant-ui/markdown-text` | in gallery · in product · part-driven | — |
| [`math-block`](https://www.assistant-ui.com/elements/math-block) | Rendered expressions with the working shown, one step at a time. | `npx shadcn add @assistant-ui/math-block` | part-driven | digichat markdown already has KaTeX paths; this is the registry card |
| [`mcp-config`](https://www.assistant-ui.com/elements/mcp-config) | A dialog for connectors and custom MCP servers, including authentication and connection state. | `npx shadcn add @assistant-ui/mcp-config` | chrome-driven | human-gate: browser MCP is new network exposure |
| [`mcp-server-panel`](https://www.assistant-ui.com/elements/mcp-server-panel) | Which servers are connected, what each one brought, and which is still waiting on you. | `npx shadcn add @assistant-ui/mcp-server-panel` | chrome-driven | human-gate |
| [`memory-chips`](https://www.assistant-ui.com/elements/memory-chips) | What it now remembers about you, written during the turn and removable. | `npx shadcn add @assistant-ui/memory-chips` | part-driven | — |
| [`mermaid-diagram`](https://www.assistant-ui.com/elements/mermaid-diagram) | Mermaid diagrams rendered inside messages, including partial streaming input. | `npx shadcn add @assistant-ui/mermaid-diagram` | part-driven | digiweb ChatMermaidBlock already exists for legacy chat family |
| [`message-actions`](https://www.assistant-ui.com/elements/message-actions) | Copy, rate, and regenerate. Each action confirms itself with a small state change. | `npx shadcn add @assistant-ui/message-actions` | in gallery · in product | Thread ActionBar |
| [`message-branches`](https://www.assistant-ui.com/elements/message-branches) | Navigate between regenerated versions of the same answer without losing your place. | `npx shadcn add @assistant-ui/message-branches` | in gallery · in product · chrome-driven | `features.branchPicker` |
| [`message-pair`](https://www.assistant-ui.com/elements/message-pair) | A user bubble and a streaming assistant reply, with actions that appear on hover. | `npx shadcn add @assistant-ui/message-pair` | on demand | demo pair; product uses Thread messages |
| [`message-queue`](https://www.assistant-ui.com/elements/message-queue) | Turns you typed while a run was in flight, stacked and cancelable until it finishes. | `npx shadcn add @assistant-ui/message-queue` | chrome-driven | — |
| [`message-timing`](https://www.assistant-ui.com/elements/message-timing) | Streaming statistics for the current message, including first token, total time, and speed. | `npx shadcn add @assistant-ui/message-timing` | chrome-driven | base skin has a message-timing element copy under skins/base/elements |
| [`mobile-composer`](https://www.assistant-ui.com/elements/mobile-composer) | The bottom sheet: keyboard-aware, quick actions above, thumb-sized targets. | `npx shadcn add @assistant-ui/mobile-composer` | on demand | — |
| [`model-selector`](https://www.assistant-ui.com/elements/model-selector) | A searchable runtime model picker with grouped providers and reasoning effort controls. | `npx shadcn add @assistant-ui/model-selector` | chrome-driven | `features.modelPicker` / `models.available` |
| [`number-ticker`](https://www.assistant-ui.com/elements/number-ticker) | Digits that roll into place as a count updates in real time. | `npx shadcn add @assistant-ui/number-ticker` | part-driven | digiweb Odometer/StatCounter are preferred for marketing surfaces |
| [`onboarding`](https://www.assistant-ui.com/elements/onboarding) | First run: three moves that teach what this assistant is actually for. | `npx shadcn add @assistant-ui/onboarding` | chrome-driven | — |
| [`orb`](https://www.assistant-ui.com/elements/orb) | The realtime voice orb, with connection, mute, and speaking state controls. | `npx shadcn add @assistant-ui/orb` | chrome-driven | `features.speech` / voice |
| [`permission-grant`](https://www.assistant-ui.com/elements/permission-grant) | Granting a capability rather than approving one action, with the reach spelled out. | `npx shadcn add @assistant-ui/permission-grant` | part-driven | — |
| [`prompt-library`](https://www.assistant-ui.com/elements/prompt-library) | Prompts you saved, searchable, with their variables shown before you insert one. | `npx shadcn add @assistant-ui/prompt-library` | chrome-driven | — |
| [`quota-banner`](https://www.assistant-ui.com/elements/quota-banner) | How much is left, when it comes back, and the way to get more. | `npx shadcn add @assistant-ui/quota-banner` | chrome-driven | pairs with digichat gate / paywall chrome |
| [`quote`](https://www.assistant-ui.com/elements/quote) | Select message text, quote it from a floating toolbar, and carry it into the composer. | `npx shadcn add @assistant-ui/quote` | chrome-driven | — |
| [`read-aloud`](https://www.assistant-ui.com/elements/read-aloud) | An answer played back, the spoken word lit as it goes, speed under your thumb. | `npx shadcn add @assistant-ui/read-aloud` | chrome-driven | `features.speech` |
| [`reasoning-effort`](https://www.assistant-ui.com/elements/reasoning-effort) | How hard to think, and how much of that budget the run actually spent. | `npx shadcn add @assistant-ui/reasoning-effort` | chrome-driven | — |
| [`reasoning`](https://www.assistant-ui.com/elements/reasoning) | A collapsible renderer for assistant reasoning that follows the active message part. | `npx shadcn add @assistant-ui/reasoning` | in gallery · in product · part-driven · chrome-driven | `features.reasoning` disclosure mode |
| [`recommendation-card`](https://www.assistant-ui.com/elements/recommendation-card) | The agent proposes a change with its confidence, and waits for a yes. | `npx shadcn add @assistant-ui/recommendation-card` | part-driven | — |
| [`regenerate-menu`](https://www.assistant-ui.com/elements/regenerate-menu) | Fork the same turn to a different model instead of rolling the same dice. | `npx shadcn add @assistant-ui/regenerate-menu` | chrome-driven | — |
| [`research-report`](https://www.assistant-ui.com/elements/research-report) | An outline that fills in section by section, each carrying the sources behind it. | `npx shadcn add @assistant-ui/research-report` | part-driven | — |
| [`retrieval-chunks`](https://www.assistant-ui.com/elements/retrieval-chunks) | The passages a retrieval answer stands on, scored, before the answer itself arrives. | `npx shadcn add @assistant-ui/retrieval-chunks` | part-driven | digisearch RAG |
| [`reviewable-diff`](https://www.assistant-ui.com/elements/reviewable-diff) | The same diff, but each hunk is a decision: keep it, discard it, apply what survived. | `npx shadcn add @assistant-ui/reviewable-diff` | part-driven | — |
| [`schedule-card`](https://www.assistant-ui.com/elements/schedule-card) | A run that repeats on its own, with its cadence and how it has been doing. | `npx shadcn add @assistant-ui/schedule-card` | part-driven | — |
| [`score-breakdown`](https://www.assistant-ui.com/elements/score-breakdown) | A verdict with its arithmetic shown: criteria, weights, and what pulled it down. | `npx shadcn add @assistant-ui/score-breakdown` | part-driven | — |
| [`scroll-anchor`](https://www.assistant-ui.com/elements/scroll-anchor) | Streaming never steals your scroll position; a pill offers the way back down. | `npx shadcn add @assistant-ui/scroll-anchor` | in gallery · in product | Thread ScrollToBottom |
| [`settings-panel`](https://www.assistant-ui.com/elements/settings-panel) | Model, system prompt, temperature, and what the assistant is allowed to do. | `npx shadcn add @assistant-ui/settings-panel` | chrome-driven | — |
| [`shared-conversation`](https://www.assistant-ui.com/elements/shared-conversation) | A read-only transcript someone sent you, with a way to pick it up yourself. | `npx shadcn add @assistant-ui/shared-conversation` | on demand | — |
| [`shiki-highlighter`](https://www.assistant-ui.com/elements/shiki-highlighter) | Shiki code highlighting that defers tokenization until a message part settles. | `npx shadcn add @assistant-ui/shiki-highlighter` | part-driven | attach to markdown-text |
| [`sources`](https://www.assistant-ui.com/elements/sources) | Runtime sources with favicon links for URLs and file badges for documents. | `npx shadcn add @assistant-ui/sources` | part-driven · chrome-driven | `features.sources` |
| [`speaker-identity`](https://www.assistant-ui.com/elements/speaker-identity) | Who is talking, once a thread holds more than a user and one model. | `npx shadcn add @assistant-ui/speaker-identity` | part-driven | — |
| [`spec-sheet`](https://www.assistant-ui.com/elements/spec-sheet) | The most common structured answer after a table: one object, labeled. | `npx shadcn add @assistant-ui/spec-sheet` | part-driven | — |
| [`stopped-run`](https://www.assistant-ui.com/elements/stopped-run) | You pressed stop. The half-written answer stays, and continuing is one tap away. | `npx shadcn add @assistant-ui/stopped-run` | in gallery · in product | Thread cancel / continue path |
| [`streaming-text`](https://www.assistant-ui.com/elements/streaming-text) | Tokens arrive softly: the newest words land in blue and settle into ink. | `npx shadcn add @assistant-ui/streaming-text` | on demand | optional effect; Thread markdown streams without this card |
| [`subagent-list`](https://www.assistant-ui.com/elements/subagent-list) | Parallel workers with their own progress, models, and completions. | `npx shadcn add @assistant-ui/subagent-list` | part-driven | digigraph subgraph fan-out |
| [`syntax-highlighter`](https://www.assistant-ui.com/elements/syntax-highlighter) | Prism-based code highlighting for assistant markdown code blocks. | `npx shadcn add @assistant-ui/syntax-highlighter` | part-driven | attach to markdown-text; alternative to shiki |
| [`terminal-block`](https://www.assistant-ui.com/elements/terminal-block) | Command output that streams line by line and ends with an exit status. | `npx shadcn add @assistant-ui/terminal-block` | part-driven | — |
| [`thinking-indicator`](https://www.assistant-ui.com/elements/thinking-indicator) | A live status line that names what the agent is doing right now, with elapsed time. | `npx shadcn add @assistant-ui/thinking-indicator` | part-driven | — |
| [`thread-list-sidebar`](https://www.assistant-ui.com/elements/thread-list-sidebar) | A complete sidebar shell that places the runtime thread list beside the active conversation. | `npx shadcn add @assistant-ui/thread-list-sidebar` | chrome-driven | product ChatShell / MemoryThreadListSidebar is first-party |
| [`thread-list`](https://www.assistant-ui.com/elements/thread-list) | Runtime-backed conversation switching with search, active selection, and thread actions. | `npx shadcn add @assistant-ui/thread-list` | chrome-driven | product uses first-party conversation list |
| [`thread-search`](https://www.assistant-ui.com/elements/thread-search) | History you can actually get back into: pinned first, then grouped by when. | `npx shadcn add @assistant-ui/thread-search` | chrome-driven | — |
| [`thread`](https://www.assistant-ui.com/elements/thread) | A complete chat container with messages, composer, auto-scroll, and accessibility built in. | `npx shadcn add @assistant-ui/thread` | in gallery · in product | capability host — digichat `(baseline)/stock/thread.aui.tsx` |
| [`timeline`](https://www.assistant-ui.com/elements/timeline) | Events on a time axis, with what already happened and what is still coming. | `npx shadcn add @assistant-ui/timeline` | part-driven | — |
| [`todo-list`](https://www.assistant-ui.com/elements/todo-list) | The agent's own working list, rewritten mid-run as it discovers what else is needed. | `npx shadcn add @assistant-ui/todo-list` | part-driven | — |
| [`tool-call`](https://www.assistant-ui.com/elements/tool-call) | One tool invocation with its request and result tucked behind a disclosure. | `npx shadcn add @assistant-ui/tool-call` | part-driven · chrome-driven | `features.toolCalls`; named tool UIs override ToolFallback |
| [`tool-error`](https://www.assistant-ui.com/elements/tool-error) | One call failed. The error, the attempt count, and a retry that doesn't restart the turn. | `npx shadcn add @assistant-ui/tool-error` | part-driven | — |
| [`tool-fallback`](https://www.assistant-ui.com/elements/tool-fallback) | The default runtime renderer for tool calls that do not have dedicated UI. | `npx shadcn add @assistant-ui/tool-fallback` | in gallery · in product · part-driven · chrome-driven | `features.toolCalls` |
| [`tool-group`](https://www.assistant-ui.com/elements/tool-group) | A collapsible runtime wrapper around consecutive tool calls in one assistant turn. | `npx shadcn add @assistant-ui/tool-group` | in gallery · in product · part-driven · chrome-driven | `features.toolCalls` |
| [`tool-timeline`](https://www.assistant-ui.com/elements/tool-timeline) | A whole working session summarized as verbs, targets, and file stats. | `npx shadcn add @assistant-ui/tool-timeline` | part-driven | — |
| [`tooltip-icon-button`](https://www.assistant-ui.com/elements/tooltip-icon-button) | An accessible icon button with a tooltip label and shared interaction states. | `npx shadcn add @assistant-ui/tooltip-icon-button` | in gallery · in product | shared stock primitive |
| [`trace-waterfall`](https://www.assistant-ui.com/elements/trace-waterfall) | Every span in a run on one time axis, nested, so you can see where it actually went. | `npx shadcn add @assistant-ui/trace-waterfall` | part-driven | digismith traces |
| [`typing-indicator`](https://www.assistant-ui.com/elements/typing-indicator) | The classic three dots, tuned to read as presence rather than noise. | `npx shadcn add @assistant-ui/typing-indicator` | on demand | gallery prefers cube loader |
| [`voice-conversation`](https://www.assistant-ui.com/elements/voice-conversation) | A live call: the orb tracks your voice, the caption names the turn, the transcript follows. | `npx shadcn add @assistant-ui/voice-conversation` | chrome-driven | `features.speech` |
| [`web-preview`](https://www.assistant-ui.com/elements/web-preview) | Chrome for a sandboxed preview: a URL bar, reload, and open-in-new around a frame you isolate. | `npx shadcn add @assistant-ui/web-preview` | part-driven | — |
| [`web-search`](https://www.assistant-ui.com/elements/web-search) | A search query and its results landing one by one as the agent reads. | `npx shadcn add @assistant-ui/web-search` | part-driven · chrome-driven | `tools.catalog` / `gate.webSearch` named tool UI |

## Already in baseline (do not re-copy)

These registry pieces are already under digichat `(baseline)/stock/` and/or
the digiweb gallery elements folder:

- **Both hosts:** `thread`, `attachment`, `file`, `image`, `markdown-text`,
  `reasoning`, `tool-fallback`, `tool-group`, `follow-up-suggestions`,
  `tooltip-icon-button`
- **Gallery only (skin lab extras):** `loading-state` (plus local `action-icons`,
  `surfaces`, forked DotMatrix — not separate catalog slugs)
- **Wired in Thread without a standalone card file:** composer, message actions,
  branch picker (`features.branchPicker`), edit, error banner, scroll-to-bottom,
  stop/cancel
- **Deploy flags already in schema:** `attachments`, `dictation`, `speech`,
  `reasoning`, `toolCalls`, `sources`, `modelPicker`, `branchPicker`

Refresh this section when a new card is copied into either host.

## Related digithings docs

- [CHAT_THEME.md](./CHAT_THEME.md) — first-party digichat skin grammar on `/chatbot`
- digichat `(baseline)/stock/SOURCE.md` — do not restyle stock copies for digichat
- digichat deploy `features` in `cloudflare/digichat/src/lib/deploy-config/schema.ts`

