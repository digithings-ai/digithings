# Kairos + tenancy — issue pack (epic + 12 work packages)

**Status (2026-09-01): DELIVERED.** Owner closed without a live E2E / house schedule.
Live-proof follow-up: [#3388](https://github.com/digithings-ai/digithings/issues/3388).
See [`EPIC.md`](EPIC.md) and [`HUMAN-UNBLOCK.md`](HUMAN-UNBLOCK.md).

Ready-to-file GitHub issue bodies for the program specced in
[`docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md`](../../superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md).
Each WP file is a **self-contained executor briefing**: a cost-effective model should be able to
implement it from the issue body alone, without re-deriving anything from the spec.

**House vs overlay book isolation (Group A):** see the scannable ops guide
[`docs/ops/HOUSE_BOOK_SCOPE.md`](../../ops/HOUSE_BOOK_SCOPE.md) before changing
`positions` / `nav_history` / `position_events` / `portfolio_metrics` readers or
writers. Epic status and cutover 113 notes stay in [`EPIC.md`](EPIC.md).

## Filing (human or authorized session)

```bash
cd docs/agent-backlog/kairos-tenancy
gh issue create --title "[epic] Olympus client-ready: Kairos execution + user tenancy" \
  --body-file EPIC.md --label agent-task --label "component:digiquant" --label epic
# Note the epic number E, then for each WP (replace labels per the table below):
gh issue create --title "[agent] K0 — Kairos execution contracts" --body-file K0.md \
  --label agent-task --label "component:digiquant" --label "risk:low"
# … repeat for K1–K5, T0–T5 (titles in each file's first line)
```

After filing, edit each issue to add `Parent: #E` (or use the epic checklist to link).

## Labels / routing / model per WP

| WP | Title | Component label | Base branch | Risk | Exec tier | Model | Human gate |
|----|-------|-----------------|-------------|------|-----------|-------|------------|
| K0 | Execution contracts | `component:digiquant` | `module/digiquant` | low | cursor | sonnet | no |
| K1 | Alpaca paper adapter | `component:digiquant` | `module/digiquant` | med | claude | sonnet | policy (broker adapter) |
| K2 | IBKR read-first adapter | `component:digiquant` | `module/digiquant` | med | claude | sonnet | policy (broker adapter) |
| K3 | Credential vault | `component:digiquant` | `module/digiquant` | high | claude | opus | **yes — crypto** |
| K4 | Intent router + broker sync | `component:digiquant` | `module/digiquant` | med | claude | sonnet | no (paper only) |
| K5 | Email notifications v0 | `component:digiquant` | `module/digiquant` | low | cursor | sonnet | no |
| T0 | Workspaces + RLS boundary | `component:digiquant` | `module/digiquant` | high | claude | sonnet | review RLS carefully |
| T1 | Supabase Auth login | (dashboard UI) | `develop` | med | claude | sonnet | **yes — auth flow** |
| T2 | Stripe tiers | `component:digiquant` | `module/digiquant` | med | claude | sonnet | **yes — webhook secrets** |
| T3 | Settings: profile/brokers/notify | (dashboard UI) | `develop` | med | claude | sonnet | no |
| T4 | Overlay pipeline runs | `component:digiquant` | `module/digiquant` | high | claude | sonnet | no (budget-guarded) |
| T5 | Tier-gated UI | (dashboard UI) | `develop` | med | cursor | sonnet | no |

Dashboard UI WPs (T1/T3/T5) are one-hop to `develop` (no module tier — `frontend/dashboard` routes
per `docs/agents/COMPONENT_ROUTING.md`); use a `cursor/<slug>` or `task/<N>-<slug>` branch off
`origin/develop`. digiquant WPs use `make task ISSUE=N` (module branches were synced 2026-08-29,
PRs #3083–#3090).

**Settings IA addendum:** [`SETTINGS-IA.md`](SETTINGS-IA.md) — Pipeline + Keys (BYOK) tabs,
tier matrix, models semantics (provider BYOK v0). Gap artifact:
`/opt/cursor/artifacts/kairos-settings-spec-gap.md`.

## Running this with cheap models in parallel multitask (read before dispatching)

1. **One WP per agent session.** Paste the WP file as the task prompt (or point the agent at the
   issue). Do NOT hand an agent the whole spec or multiple WPs — scope creep is the failure mode.
2. **Waves, not a free-for-all.** Dependencies are hard:
   - Wave A: **K0 ∥ T0** (disjoint files, safe together)
   - Wave B: **K1 ∥ K2 ∥ T1** (after K0 merges; K1/K2 both touch `digiquant/pyproject.toml` +
     `digiquant/ARCHITECTURE.md` — see conflict rules below)
   - Wave C: **K3 ∥ T2 ∥ T5** (K3 after K1 merges)
   - Wave D: **K4 ∥ T3** (K4 after K1+K3; T3 after T1+K3)
   - Wave E: **K5 ∥ T4** (K5 after K4; T4 after T0+T2+K4)
3. **File-ownership discipline** (prevents cross-agent merge conflicts):
   - Each WP lists `Files — create/modify`. An agent must not touch files outside its list except
     the two shared append points below.
   - Shared append points: `digiquant/pyproject.toml` (optional-extras block — add your own line,
     never reorder) and `digiquant/ARCHITECTURE.md` (add your own `##`/`###` section, never edit
     another WP's section). Rebase on the base branch immediately before opening the PR.
   - Supabase migration numbers are allocated at PR time: take the next free
     `digiquant/supabase/migrations/NNN_*.sql` **when you open the PR**, and renumber if another
     migration merges first. Update `digiquant/supabase/SCHEMA.md` in the same PR.
4. **Verification is the exit condition.** Every WP ends with exact commands; the agent must run
   them and paste output in the PR. `make score` must pass (≥8/8/7/9). Do not open the PR red.
5. **Stop-and-report rule for executors:** if an acceptance criterion cannot be met as written,
   STOP and report the blocker on the issue — do not improvise architecture. The spec decision
   table (D1–D10) is locked; deviations need a human.
6. **Never touch:** live-trading paths (`digiquant/brokers/live/` must not exist yet), digikey
   auth code, `.github/workflows/` (unless the WP says so), another WP's files.

## External prerequisites (human-owned; agents must not block on these)

| Needed by | Item | Status 2026-08-29 |
|-----------|------|--------------------|
| K1 tests (integration marker only) | Alpaca paper API keys | missing — unit tests use mocks, so K1 can merge without |
| K2 (manual verify only) | IBKR paper username / self-service OAuth creds | missing — mocked unit tests suffice to merge |
| K3/T2 deploy | `DIGIQUANT_VAULT_MASTER_KEY`, Stripe test keys + price ids, webhook secret | missing |
| K5 deploy | Working Mailgun API key + domain | MCP key currently failing auth |
| T1 deploy | Google + GitHub OAuth apps in Supabase Auth (`core` project) | not configured |
| Product launch | Alpaca Connect app review; IBKR OAuth 1.0a vendor onboarding | not started — long poles |

Code merges on mocked tests; deploys wait on the table above.

## Deployment / cutover

Operator runbook (merge state, migrations 096–105, Edge Functions, dashboard flags,
human prerequisites, cutover checklist, E2E skeleton, rollback):
[`DEPLOYMENT.md`](DEPLOYMENT.md).

Credential / PAT / vendor secret naming (**digithings**, not “cursor cloud agent”):
[`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md).

Post-cutover RLS verification harness (vanilla Postgres or production clone):
[`scripts/rls_proof/`](../../../scripts/rls_proof/) — run after §6 staged SQL is applied.

Staged anon-policy-drop SQL (inert until renamed into the live migrations dir at
cutover):
[`digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql`](../../../digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql).
