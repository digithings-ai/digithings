# @digithings/catalog

Framework-neutral shared catalogs — no React, no Next.js, no app aliases, so
any runtime can import them.

| Entry | What it is |
|---|---|
| `@digithings/catalog` | Every catalog, re-exported |
| `@digithings/catalog/byok-providers` | The BYOK provider catalog (ids, labels, key hints) |
| `@digithings/catalog/openapi` | The OpenAPI service registry |
| `@digithings/catalog/page-context-sanitize` | The page-context sanitiser shared by the surfaces that ship it |

```ts
import { BYOK_PROVIDERS } from "@digithings/catalog/byok-providers";
```

## Publishing

This package is published to npm as part of the digithings R0 release. Its
`exports` point at **TypeScript source**, not a build output, so the published
tarball is the same code the workspace consumes.

A Next.js consumer must therefore transpile it — add the package to
`transpilePackages` in `next.config.mjs`:

```js
const nextConfig = {
  transpilePackages: ["@digithings/catalog"],
};
```

A bundler that already compiles TS (Vite, tsup, Bun) resolves the source
directly and needs no extra configuration.

Tests: `npm test --workspace @digithings/catalog`.
