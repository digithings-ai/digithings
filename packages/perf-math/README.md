# @digithings/perf-math

Framework-free portfolio performance math: live KPIs, base-100 continuity index,
since-inception, Jensen alpha and information ratio.

**Dependency-free on purpose.** No React, no React DOM, no DOM, no I/O, no
`@digithings/*` edges. That is what lets `@digiquant/contract` and the R5 Worker
bundle use this math without pulling the `@digithings/ui` component layer — which
would drag React into a Worker that cannot run it.

`@digithings/ui` re-exports every symbol here from its tearsheet entry point, so
existing `@digithings/ui` imports keep working.

```ts
import { computeLivePerformanceKpis } from "@digithings/perf-math";
```

Tests: `npm test --workspace @digithings/perf-math`
