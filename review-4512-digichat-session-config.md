# Review — PR #4512, digichat authenticated-session deployment config

**Subject:** PR #4512 — `fix(digichat): honour the deployment config on the authenticated-session path`
**Branch:** `task/4510-digichat-session-config` → `module/digichat`
**Issue:** #4510 (program plan: `docs/architecture/digichat-config-program-plan.md`, Phase 2b)
**Reviewed revision:** `392cabafb` (fixes in `962a97e08`)
**Reviewer:** independent fresh-context read-only subagent (`general`, delegation `eager-indigo-otter`, 2026-09-22T22:33:33Z → 22:37:27Z). The author session did not review its own work. The reviewer had no shell tool, so verification was static — it reconstructed the diff from the GitHub API and read the sources.

## Verdict

**APPROVE WITH NITS** — 0 blocker / 0 major / 3 minor / 2 nit.

All nine change claims checked out. No regression on the embed surface's authorization gates, and no scope or shadowing bug.

## Findings

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | minor | `route.ts:172` — the hoisted deployment resolution picked `dep` from the client-supplied `X-Embed-Host` header on *every* request. On the session path that header was the only input, and `dep` now drives `backend` and `requiredPlanTier`. An authenticated user on a multi-host container could name another registered host to route to that host's foundry backend, or name an ungated host to null out `requiredPlanTier`. Not a regression (the session path had no gate and always ran digigraph before). | **Fixed in `962a97e08`.** The session path now uses `config.deployment ?? null`; only the embed path — which has already verified the host via token / first-party origin — consults the header. |
| 2 | minor | The `models.available` allowlist moved ahead of the foundry branch, so a foundry *embed* with an allowlist and an out-of-list `X-Digi-Model` now 400s where it previously succeeded. No in-repo foundry config sets `models.available`, so there is no live impact, but the PR body's "embed path byte-identical" claim was overstated. | **Accepted, wording corrected.** The enforcement is intended (the plan asked for `models.available` on the foundry path). The PR body now states that the embed surface's authorization gates are unchanged while the allowlist also applies to foundry requests. |
| 3 | minor | An unreadable deploy config began failing *open* for an explicit `X-Digi-Model`: the allowlist used to call `getDigichatConfig()` inside its own try (config error → 400 `model_not_allowed`), but after the hoist the error was swallowed by the outer catch, leaving `dep === null` and forwarding the client's model. | **Fixed in `962a97e08`.** A `configFailed` flag is set in both catches and restores the 400 for an explicit model. |
| 4 | nit | The new foundry test sent a *disallowed* model and asserted 400 + foundry not called — which also passed against the pre-change code (with `embedConfig === null` the old foundry branch was false, so the old digigraph-path allowlist produced the same 400). It proved nothing foundry-specific. Tests 1–3 do fail pre-change. | **Fixed in `962a97e08`.** The test now also sends an allowlisted model and asserts the foundry adapter is reached exactly once — reachable only because the allowlist runs ahead of the foundry branch. |
| 5 | nit | Session `activityDetail` defaults to `"labels"` instead of the previous hard-coded `"full"` when `dep` is null (hosts-only container, or a config error). | **Accepted.** More conservative and matches the schema default. Checked: `config/examples/local-app.yaml:50` and `local-app-memory.yaml:43` both set `activityDetail: full`, and `digithings-ai-embed.yaml:95` sets `full` on the digithings.ai host (embed path, where `embedConfig` still wins). A session install that wants full detail must set it explicitly. |

## Verified clean

- Embed-path authorization gates unchanged: `embedConfig?.gateMode === "trial_form"`, `embedConfig.gate.consumeUrl`, the web-search gate `embedConfig?.webSearch === true || (!embedConfig && process.env.DIGICHAT_WEB_SEARCH === "1")`, and `backend`/`activityDetail` where `embedConfig?.… ?? dep.…` means the embed value always wins.
- `isPlanTierSatisfied({ requiredPlanTier }, callerTier)` reads only `requiredPlanTier`, so the narrowed object is equivalent; the param narrowing is source-compatible (only caller is the route; `embed-tenants.test.ts:979-1006` still passes).
- No shadowing: one `let dep`, all references the hoisted one; `modelId` is declared before `provider(modelId)`.
- `resolveDeploymentForHost(null, config)` returns `config.deployment ?? null`, and a hosts-only config returns `null` (`loader.ts:493-501`), so a multi-tenant install's session path is a no-op.
- Config-load failures cannot 500 a previously-working request (`loader.ts:393-405` sticky error, caught by the outer try); the later MCP / allowlist helpers are null-safe and fail closed (`force-tool.ts:54-62,111-129`, `mcp-servers.ts:216-242,283-316`).
- Test isolation is sound: each new test wraps `setDigichatConfigForTests` in `try/finally { resetDigichatConfigForTests() }`; tests 1–3 exercise the session path via `mockAuthCtx` (no `embedConfig`) and `chatReq()` sends no `X-Embed-Host`.
- Deleting the second `dep` resolution in the MCP / forced-tool block is behaviour-neutral (`normalizeConfigHost` trims internally, `loader.ts:459-469`).

## Evidence inspected by the reviewer

PR #4512 diff and metadata; `src/app/api/chat/route.ts`; `src/lib/deploy-config/loader.ts`; `schema.ts`; `force-tool.ts`; `mcp-servers.ts`; `src/lib/embed-tenants.ts`; `embed-chat-tenant.ts`; `chat-route-context.ts`; `src/test/route-auth-mock.ts`; `src/app/api/chat/route.test.ts`; `embed-tenants.test.ts:979-1007`; `config/examples/{local-app,local-app-memory,dashboard-modal,digithings-ai-embed}.yaml`; `config/datatap-trial-foundry.yaml`; `infra/digichat-release/config/digichat.yaml.example`.

## Verification after the fixes

```
apps/digichat  npx vitest run src/app/api/chat/route.test.ts   1 file / 61 tests passed
apps/digichat  npm run test                                    125 files / 1252 tests passed
apps/digichat  npm run lint                                    30 problems, 0 errors (all pre-existing)
apps/digichat  npm run build                                   TypeScript clean, all routes generated
make doc-check                                                 OK (418 markdown files)
```
