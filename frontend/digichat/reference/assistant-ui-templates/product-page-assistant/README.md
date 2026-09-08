# Support Troubleshooting Assistant

First Xulux support assistant template app. It is a Next.js + TypeScript app using assistant-ui generated components, the assistant-ui AI SDK runtime, frontend tool registration, attachment primitives, and a real local `/api/chat` route.

## Run

```sh
npm install
npm run dev
```

Open `http://localhost:3000`.

No API key is required for the preview. Without `OPENAI_API_KEY`, `/api/chat` streams a deterministic support demo that renders the issue analysis card, support summary card, final handoff guidance, and a visible demo-mode notice.

To enable real AI mode:

```sh
cp .env.example .env.local
# add OPENAI_API_KEY
npm run dev
```

## What To Try

Open the floating support widget and click `Integration stopped syncing`. You can also type `I cannot sign in`.

Attachments are handled through assistant-ui attachment primitives. The template accepts PNG, JPG, WebP, TXT, LOG, and JSON files up to 5 MB.

## Customization

The runtime preview config uses three top-level keys:

- `hostUi`: JSON component tree for the mock product dashboard behind the assistant.
- `assistant`: modal/thread labels, welcome copy, suggested prompts, tool metadata, demo flows, and mock tool data.
- `brandTheme`: shared visual tokens.

Source defaults live in:

- `lib/support/host-ui.ts` for the default mock dashboard JSON.
- `lib/support/assistant-config.ts` for assistant/thread/tool defaults and `brandTheme`.
- `lib/support/tool-data.ts` for deterministic mock tool data and scenario packs.
- `lib/support/settings.ts` for attachment limits and layout-level defaults.

Do not duplicate host-page dashboard text in `assistant.toolData`. If a preview config provides `hostUi`, the preview renders that tree exactly. Defaults are used only when `hostUi` is omitted.

Edit `lib/support/tool-parameters.ts` to change tool schemas, `lib/support/mock-tools.ts` to change deterministic tool behavior, and `components/support/tool-cards.tsx` / `lib/support/tool-ui.tsx` to change visual card design.

Supported default card renderer types are `analysis`, `summary`, and `generic`. Unknown tools or outputs that do not match the expected custom card shape should render through the generic card instead of breaking the preview.

The default preview uses `components/assistant-ui/assistant-modal.tsx`. `components/assistant-ui/assistant-sidebar.tsx` is included as a generated-compatible alternate layout for always-open support panels.

## Runtime Preview And Download

Small preview configs can use a URL token:

```txt
/preview?p=<encoded-config>
/api/download?p=<encoded-config>
```

Larger preview configs should use a short session URL:

```txt
POST /api/preview/session
/preview?s=<session-id>
/api/download?s=<session-id>
```

Preview sessions are in-memory and expire after one hour. If a token or session
cannot be loaded, the preview shows a warning and falls back to the source
defaults.

The shared runtime helpers live in `lib/template-runtime/*`. Support-specific
schema, session, config resolution, and download materialization live in
`lib/support/*`.

## Architecture

- `app/assistant.tsx` wires `useChatRuntime`, `AssistantChatTransport`, `AssistantRuntimeProvider`, `Tools({ toolkit })`, `Suggestions(...)`, and attachment adapters.
- `app/api/chat/route.ts` chooses real provider streaming when `OPENAI_API_KEY` exists, otherwise streams deterministic UI-message chunks.
- `app/api/preview/session/route.ts` stores larger validated preview configs and returns short preview/download URLs.
- `app/preview/page.tsx` renders preview config from either `p=<encoded-config>` or `s=<session-id>`.
- `lib/template-runtime/*` contains copyable generic helpers for preview tokens,
  preview sessions, config merge, download exclusions, and zip generation.
- `lib/support/runtime-config.ts`, `lib/support/preview-schema.ts`,
  `lib/support/preview-sessions.ts`, and `lib/support/download-materializer.ts`
  are preview/download glue for this template and are excluded from downloaded
  app bundles.
- `lib/support/host-ui.ts` defines the default JSON UI tree for the mock dashboard and the allowed component contract.
- `components/support/host-ui-renderer.tsx` renders `hostUi` during preview and is excluded from downloads.
- `lib/support/assistant-config.ts` defines assistant, thread, tool metadata, demo-flow, and theme defaults.
- `lib/support/tool-data.ts` contains deterministic scenario data used by mock tools.
- `lib/support/toolkit.tsx` registers support tools, while `lib/support/tool-parameters.ts` owns schemas and `lib/support/tool-ui.tsx` maps tools to cards.
- `app/api/support/tools/[toolId]/route.ts` executes tool calls on the backend and shows where to replace mocks with real integrations.
- `components/assistant-ui/thread.tsx` keeps the generated assistant-ui thread/composer/message primitives generic and receives labels/welcome copy as props.
- `components/support/support-assistant-shell.tsx` adapts the generic assistant-ui modal/thread to this support template.
- `components/support/product-dashboard.tsx` renders the mock SaaS product surface from `hostUi` in preview. Download materialization rewrites it into normal static React.
