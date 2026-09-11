# Docs Website Assistant

A Next.js and assistant-ui starter for a product documentation assistant. It shows a docs navigation, article content, source-search tools, page preview cards, code snippets, and a desktop assistant sidebar with a mobile assistant modal.

## Run

```sh
npm install
npm run dev
```

Open `http://localhost:3000`.

`OPENAI_API_KEY` is optional. Without it, `/api/chat` uses deterministic demo mode so the default prompts still show `searchDocs`, `openPage`, `generateCodeSnippet`, source references, and final guidance. With a key, the route uses the AI SDK provider path and the same assistant-ui tools.

## Customize

- Main safe customization: `lib/docs/customization.ts`
- Docs corpus and snippets: `lib/docs/mock-data.ts`
- Tool schemas: `lib/docs/tool-parameters.ts`
- Mock tool behavior: `lib/docs/mock-tools.ts`
- Tool card rendering: `components/docs/tool-cards.tsx`

Suggested prompts can set `prompt` when the sent message should differ from
the visible title, and `flowId` when no-key demo mode should force a specific
demo flow.

Preview config can customize the fixed docs tools' display names, model-facing
descriptions, implementation hints, and renderer type. Adding new tool schemas,
changing tool parameters, or replacing handlers is intentionally a source-code
edit in `lib/docs/tool-parameters.ts`, `lib/docs/mock-tools.ts`, and
`lib/docs/toolkit.tsx`, not a runtime preview-config feature.

The default prompts are:

- Debug a 401 response
- Find webhook setup docs

## App Versions

The template includes five user-case presets in `lib/docs/version-presets.ts`.
Use them with `v=<version-id>`:

- `product-docs`: Product Docs Assistant
- `developer-api`: Developer API Integration Assistant
- `website-copilot`: Website Page Copilot
- `docs-search`: Search-and-Navigate Docs Helper
- `code-examples`: Code Example Generator

Examples:

```txt
/preview?v=developer-api
/api/download?v=developer-api
```

`p` tokens and `s` sessions can still override a selected version when you need
runtime customization on top of a preset.

## Preview And Download

Runtime previews support small URL tokens and larger server-side sessions:

```txt
/preview?v=<version-id>
/preview?p=<encoded-config>
POST /api/preview/session
/preview?s=<session-id>
GET /api/download?v=<version-id>
GET /api/download?p=<encoded-config>
GET /api/download?s=<session-id>
```

The downloaded zip writes selected values into normal source defaults and excludes preview/download/runtime-only code.
