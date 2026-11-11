# @digithings-ai/digichat-ui

Shared digichat CSS and helpers: the `.dc-*` session grammar, the caret styles,
the slash palette, the brand mark and the transcript markdown export.

It is **not** a session shell. digichat 2.0 renders its session through the
stock `assistant-ui` Thread in `apps/digichat`; parents (digithings-web, the
dashboard popup, `widget.js`) embed digichat through `/embed`. The transcript
helpers live in `@digithings-ai/ui/chat/transcript` and are re-exported here.

| Entry | What it is |
|---|---|
| `@digithings-ai/digichat-ui` | `DigiChatMark`, the slash-command helpers, the transcript helpers |
| `@digithings-ai/digichat-ui/styles/session.css` | The `.dc-*` session grammar |
| `@digithings-ai/digichat-ui/styles/cursor.css` | The caret and keyframe tokens |

```tsx
import { DigiChatMark } from "@digithings-ai/digichat-ui";
import "@digithings-ai/digichat-ui/styles/session.css";
```

[`ARCHITECTURE.md`](ARCHITECTURE.md) has the module map and the public API
contract.

## Publishing

This package is published to npm as part of the digithings R0 release. Its
`exports` point at **TypeScript source** and raw CSS, not a build output, so the
published tarball is the same code the workspace consumes.

A Next.js consumer must therefore transpile it — add the package to
`transpilePackages` in `next.config.mjs`:

```js
const nextConfig = {
  transpilePackages: ["@digithings-ai/digichat-ui", "@digithings-ai/ui"],
};
```

A bundler that already compiles TS (Vite, tsup, Bun) resolves the source
directly and needs no extra configuration. `react` and `react-dom` are peers.

Tests: `npm test --workspace @digithings-ai/digichat-ui`.
