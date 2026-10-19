# In-session review — digichat devkit P0 (uncommitted diff)

- Reviewer: fresh-context subagent (general), 2026-09-26. Author session did not review its own work.
- Subject: uncommitted P0 diff — `apps/digichat/src/lib/devkit-configs.ts`, `app/api/devkit/{configs,validate}/route.ts`, `app/(devkit)/**`, plan doc. `route-menu.tsx` out of scope.
- Verdict: **needs-changes** (0 blockers, 2 major, 3 minor, 1 nit).

## Findings

Major:
1. `apps/digichat/src/lib/devkit-configs.ts:57-66` — `redactSecretLines` (line-regex) misses quoted keys (`"token": …`) and block-scalar continuations (`token: |` + indented lines); served `redactedText` keeps secret bytes. Note: `stripDeploymentSecrets` is structural (safe) — leak is display-text only.
2. `apps/digichat/src/app/api/devkit/configs/route.ts:13-16` — zero route tests (no prod-404, non-loopback-404, or HTTP-level secret-absence); only `src/lib` tested.

Minor:
3. `devkit-configs.ts:69-78` — `stripDeploymentSecrets` leaves `mcp.servers[].setup` (arbitrary record forwarded to digigraph) in browser-served JSON.
4. `app/(devkit)/devkit/page.tsx:7-9` — production-only gate, no loopback check (shell carries no data; APIs gate loopback). Diverges from plan's `isLocalBaselinePreview` contract.
5. `devkit-isolation.test.ts:12-41` — string-match assertions, not behavioral.

Nit:
6. `devkit-client.tsx:13` vs `devkit-configs.ts:36` — `path: string | null` vs server `string`; harmless, align.

## Verified clean

Loopback+production gating on both API routes; no user-supplied fetch URLs/paths; zod `.strict()` + unknown-key tests; `(devkit)/layout.tsx` isolated (fonts + baseline.css only); no `packages/ui`/skin/deploy-config changes; plan-doc prose lowercase; 17/17 tests green.

## Fix resolution (build session, 2026-09-26)

- Major 1 (fixed): `redactSecretLines` rewritten — quoted keys (`"token"`,
  `'consumeUrl'`) masked with quoting preserved; block scalars (`|`, `>`,
  chomping/indent variants) mask header + continuations until indentation
  returns; `#`-comment lines still pass through. +2 unit tests.
- Major 2 (fixed): `app/api/devkit/configs/route.test.ts` — prod-404,
  off-loopback-404, and an HTTP-level sweep asserting every secret-looking
  line in served text holds only the sentinel and served deployments carry
  no `token`/`consumeUrl`/`setup`.
- Minor 3 (fixed): `stripDeploymentSecrets` also deletes `mcp.servers[].setup`;
  route test asserts its absence at HTTP level; unit test pins it.
- Minor 4 (declined with reason): `page.tsx` keeps the production-only gate
  in exact parity with `(baseline)/baseline/page.tsx` — the shell carries no
  data and both API routes enforce loopback; a novel async-headers host check
  would diverge from the established pattern for zero data protection.
- Minor 5 (addressed behaviorally): new `devkit-wire-contract.test.ts` pins
  the server→client JSON shape with real `listDevkitEntries` output (the
  regression net for the T4 `issues` drift). Full RTL render skipped:
  node-environment suite + heavy client chain (assistant-ui runtime, skins)
  would make it brittle; string-match layout tests retained for the
  import-graph invariants vitest cannot execute (CSS imports).
- Nit 6 (fixed): wire `path: string | null` → `string` (server never null).

Re-verified: app suite 1343/1343, lint 0 errors (27 warnings, pre-existing
count unchanged).

## T5 verification record (author session)

Lint 0 errors (27 pre-existing warnings); app 1337/1337, ui 560/560; prod build green (`/devkit` + APIs listed); prod `next start` : `/devkit`, both APIs 404 (`/baseline` 307 control); browser `:3001/devkit` — 25 entries, redacted YAML + live preview, theme toggle verified working, 0 console errors. Known non-blocker F1: welcome.title/suggestions don't project (shared baseline pipeline limitation, parity by construction; P1 follow-up).
