# Repo split (G07)

Plan for splitting the digithings monorepo into one public repo and seven private repos,
with per-repo release branches and no Cloudflare deploys from `main`.

| File | What it is |
|---|---|
| [review.md](review.md) | Critical review of the 8-repo proposal. **Verdict: MODIFY** — topology agreed, mechanics changed. |
| [migration-plan.md](migration-plan.md) | Phased plan P0–P6: order of moves, per-repo recipe, validation, rollback, docs to update. |
| [decisions.md](decisions.md) | Decision register: gate decisions for Chris, changed and unchanged recommendations. |
| [repo-split.mmd](repo-split.mmd) / [repo-split.png](repo-split.png) | Target topology after the modifications. |

The original proposal (with the file:line coupling inventory) and the per-path manifest are kept on
the tracking issue (DIG-3518), not in this public repo: they map where non-public files sit in history.

## Target repos

| # | Repo | Visibility | Role |
|---|---|---|---|
| R0 | `digithings` | public | OSS modules, SDKs, UI packages, digichat engine, MCP tooling |
| R1 | `digiquant-strategies` | private | proprietary strategies + optimiser (plugin) |
| R2 | `digiquant-stack` | private | production backend (runner, desk API, schema, pipeline) |
| R3 | `digiquant-web` | private | Brief desk + digiquant.io |
| R4 | `digithings-web` | private | digithings.ai, digibook, brand |
| R5 | `digithings-stack` | private | shared production platform (stack, digichat Worker, Langfuse, cron) |
| R6 | `digichat-tenants` | private | client tenant corpora + rollout tooling (writes KV/R2) |
| R7 | `twelve-x` (exists) | private | client desk + digidata-api |

## Status

Gate decisions answered 2026-10-14 (Free plan, mono public until cutover, fresh R0, tags, self-hosted runners); plan revised to match. Open: D-G5 (deploy runner host) and D-G6 (signed-tag deploy gate) in [decisions.md](decisions.md). Nothing has moved yet.
