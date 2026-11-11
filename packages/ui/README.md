# @digithings-ai/ui

The shared React component layer for the digithings surfaces: the terminal and
emblem grammar, `ThemeProvider`, motion primitives, the chat kit
(`assistant-ui` skins), the finance chart shells and the stylesheets that pin
them. It consumes `@digithings-ai/design` tokens and `@digithings-ai/hero-banner`
definitions; it owns no data and no network I/O.

```tsx
import { Terminal, ThemeProvider } from "@digithings-ai/ui";
import "@digithings-ai/ui/styles/web-theme.css";
```

Entry points are listed under `exports` in
[`package.json`](package.json) — the barrel (`.`) plus one deep entry per
component family (`./theme`, `./chat/thread`, `./chat/transcript`,
`./chart-scale`, `./styles/*`, …). Import the narrowest entry that has what you
need: `./styles/*` is CSS, the rest is TypeScript or TSX source.

The kit grammar, the tokens-never-literals rule and the chart house rules are
described in [`DESIGN.md`](DESIGN.md), [`CHAT_THEME.md`](CHAT_THEME.md) and
[`CHARTS.md`](CHARTS.md).

## Publishing

This package is published to npm as part of the digithings R0 release. Its
`exports` point at **TypeScript source**, not a build output, so the published
tarball is the same code the workspace consumes.

A Next.js consumer must therefore transpile it — add the package (and its
`@digithings-ai/*` dependencies, which are source too) to `transpilePackages` in
`next.config.mjs`:

```js
const nextConfig = {
  transpilePackages: [
    "@digithings-ai/ui",
    "@digithings-ai/design",
    "@digithings-ai/hero-banner",
    "@digithings-ai/perf-math",
  ],
};
```

A bundler that already compiles TS (Vite, tsup, Bun) resolves the source
directly and needs no extra configuration. `react` and `react-dom` are peers;
`@assistant-ui/react` is a peer because the chat entries import it.

Tests: `npm test --workspace @digithings-ai/ui`.
