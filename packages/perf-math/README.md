# @digithings-ai/perf-math

Framework-free portfolio performance math: live KPIs, base-100 continuity index,
since-inception, Jensen alpha and information ratio.

**Dependency-free on purpose.** No React, no React DOM, no DOM, no I/O, no
`@digithings-ai/*` edges. That is what lets `@digithings-ai/contract` and the R5 Worker
bundle use this math without pulling the `@digithings-ai/ui` component layer — which
would drag React into a Worker that cannot run it.

`@digithings-ai/ui` re-exports every symbol here from its tearsheet entry point, so
existing `@digithings-ai/ui` imports keep working.

```ts
import { computeLivePerformanceKpis } from "@digithings-ai/perf-math";
```

Tests: `npm test --workspace @digithings-ai/perf-math`
