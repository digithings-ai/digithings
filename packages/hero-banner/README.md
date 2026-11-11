# @digithings/hero-banner

One banner definition, rendered to a terminal (half-blocks) and to the web
(canvas). The definition — cells, animation, palette — is declared once in
`src/definitions/`; the renderers only decide how a cell becomes output.

```ts
import { BANNERS } from "@digithings/hero-banner/definitions";
```

| Entry | What it is |
|---|---|
| `@digithings/hero-banner` | The engine: `sampleBanner`, `canonicalLayout`, `fitTerminal`, the animation builders and the layout maths |
| `@digithings/hero-banner/definitions` | The shipped banner definitions (`BANNERS`), one per module |
| `@digithings/hero-banner/web` | The canvas renderer for React surfaces (`react` is an optional peer) |

`src/tui.ts` and `src/ssr.ts` are the terminal and server-side renderers. The
spec is [`docs/architecture/hero-banner-spec.md`](../../docs/architecture/hero-banner-spec.md).

## Publishing

This package is published to npm as part of the digithings R0 release. Its
`exports` point at **TypeScript source**, not a build output, so the published
tarball is the same code the workspace consumes.

A Next.js consumer must therefore transpile it — add the package to
`transpilePackages` in `next.config.mjs`:

```js
const nextConfig = {
  transpilePackages: ["@digithings/hero-banner"],
};
```

A bundler that already compiles TS (Vite, tsup, Bun) resolves the source
directly and needs no extra configuration.

Tests: `bun test`. Build (type declarations): `npm run build --workspace @digithings/hero-banner`.
