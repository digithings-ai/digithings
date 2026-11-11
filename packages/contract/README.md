# @digithings-ai/contract

The shared contract for the digiquant desk and its API: types and pure
functions, with no React, no DOM and no I/O, so the same module runs in a
browser bundle, a Worker and a Node service.

| Entry | What it is |
|---|---|
| `@digithings-ai/contract` | Every type and helper, re-exported |
| `@digithings-ai/contract/types` | The wire types the desk and the API exchange |
| `@digithings-ai/contract/accounting-views` | Accounting view models |
| `@digithings-ai/contract/benchmark-tickers` | Benchmark ticker identity |
| `@digithings-ai/contract/book-reconciliation` | Book reconciliation shapes and helpers |
| `@digithings-ai/contract/brief-book-event` | The brief book-event shape |
| `@digithings-ai/contract/dashboard-ssot` | The dashboard's single source of truth |
| `@digithings-ai/contract/performance-ssot` | The performance single source of truth |
| `@digithings-ai/contract/position-event-economics` | Position event economics |

```ts
import type { DeskPosition } from "@digithings-ai/contract/types";
```

Portfolio performance maths lives in `@digithings-ai/perf-math`, which this
package depends on at an exact version.

## Publishing

This package is published to npm as part of the digithings R0 release. Its
`exports` point at **TypeScript source**, not a build output, so the published
tarball is the same code the workspace consumes.

A Next.js consumer must therefore transpile it — add the package to
`transpilePackages` in `next.config.mjs`:

```js
const nextConfig = {
  transpilePackages: ["@digithings-ai/contract", "@digithings-ai/perf-math"],
};
```

A bundler that already compiles TS (Vite, tsup, Bun) resolves the source
directly and needs no extra configuration.

Tests: `npm test --workspace @digithings-ai/contract`.
