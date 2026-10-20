# Cutover runbook: twelve-x off Supabase (DIG-2902, supabase exit 14)

Scope: twelve-x only. Core gets its own runbook (DIG-2903) after twelve-x.
Stop rule: this ticket ends at **ready-to-cut-over**. No production cutover,
no Cloudflare prod binding or deploy change, without Chris.

Standing rules (from the epic DIG-2887, repeated here so the runbook is
self-contained):

- Code lands via PRs into `develop` (merge into `develop` OK; never `main`).
- No Cloudflare prod binding or deploy changes and no production cutover
  without Chris.
- Supabase stays live and untouched (never delete, pause, or prune) as the
  2-week rollback.
- No data work until Chris's snapshot exists (ticket 0, DIG-2888).

## 1. Gates (all must hold before Phase A with data)

| # | Gate | State at time of writing (11 Oct 2026) |
|---|------|----------------------------------------|
| 0 | Snapshot exists: Chris ran `scripts/snapshot.sh` (DIG-2888, PR #5408), `~/Backups/supabase-exit/<ts>/` + SHA-256 sidecars + `manifest.json` verified (`pg_restore -l`, `shasum -c`), copied to R2 `digithings-archive/backups/supabase-exit/<ts>/` with read-back compare | OPEN. PR #5408 unmerged; Chris runs the script by hand (prompts for DSNs, never stored). **Nothing below that touches data runs until this lands.** |
| 1 | Caller inventory (DIG-2889) and twelve-x DDL port (DIG-2890, 26 tables) merged | DIG-2890 todo. Chris holds a local DDL draft (`twelve-x.d1.sql`, 26 tables) in his scratch dir; it is his WIP, not reviewed, not in the repo. |
| 2 | Principal review of schema + RLS-to-Worker auth rewrite (DIG-2892) | blocked |
| 3 | Migration scripts with verification (DIG-2893): pg dump to batched D1 import, row counts + checksums per table, local-only | blocked |
| 4 | Local stack parity (DIG-2901, PR #5405): `run_stack_local.sh` starts dashboard-api via `wrangler dev --persist-to` on `apps/dashboard-api/wrangler.local.toml`, seed gated on `SUPABASE_EXIT_SNAPSHOT_DIR`, schema-only placeholder migration `d1-local/migrations/0001_schema.sql` | Issue done; PR #5405 open, left for the merge queue. |

Schema-only local boot (no data) is allowed before gate 0. Everything in
Phase A marked DATA waits for gate 0; everything marked SCHEMA may run now.

## 2. Phase A: local dry run

Local surface (all local-only, never deployed):

- `scripts/run_stack_local.sh` boots the host-native stack plus dashboard-api
  on `wrangler dev --persist-to` with `--config apps/dashboard-api/wrangler.local.toml`.
  The local config carries the `DASHBOARD_D1` binding, a placeholder
  `database_id` (dev `--local` never contacts the API), no routes, no custom
  domains, no secrets, and no Supabase vars, so the worker serves stub
  doubles and cannot read prod Supabase. `apps/dashboard-api/wrangler.toml`
  (prod) carries no `d1_databases` section; keep it that way until Chris
  approves the cutover.
- `scripts/stop_stack_local.sh` stops the stack.

Steps:

1. `git fetch origin` and confirm PR #5405 (or its merged equivalent) is in
   your checkout: `apps/dashboard-api/wrangler.local.toml`,
   `apps/dashboard-api/d1-local/migrations/0001_schema.sql`, and the
   `SUPABASE_EXIT_SNAPSHOT_DIR` seed gate in `scripts/run_stack_local.sh`
   must all be present. Without a snapshot dir the seed step prints the
   schema-only notice and no-ops; that is the expected SCHEMA state.
2. SCHEMA: `./scripts/run_stack_local.sh`, then `./scripts/stop_stack_local.sh`.
   Pass = clean boot, D1 placeholder migration applied to the persisted local
   D1, dashboard-api healthy on `$PORT_D1API` (default 8787), no `wrangler
   deploy` invoked anywhere.
3. DATA (only after gate 0): set `SUPABASE_EXIT_SNAPSHOT_DIR` to the verified
   snapshot dir (the one covered by `manifest.json`), re-run the stack
   script. It builds `d1-seed.sql` from the snapshot and applies it with
   `wrangler d1 execute --local`. Pass = apply clean, per-table row counts
   reported, zero diff against the snapshot manifest counts.
4. DATA: run the twelve-x DDL (DIG-2890 output, post DIG-2892 review) and the
   DIG-2893 migration import against the same local D1, then re-run step 3.
   Both paths must converge on identical row counts and checksums per table
   (that comparison is Phase B).

Twelve-x repo notes (read-only recon, 11 Oct 2026): twelve-x reads/writes
Supabase through `digibase.connectors.supabase` via `config.py`
(`TWELVEX_SUPABASE_URL`, `TWELVEX_SUPABASE_SERVICE_KEY`, plus the
`CORE_*` pair for core reads). DDL reaches prod only through
`.github/workflows/db-migrate.yml` (ledger-gated `scripts/apply_migrations.py`
on push to `main`, `SUPABASE_DB_URL` session-pooler on 6543). The dry run
never touches either: no migration files added, no workflow dispatch, no
secret use.

## 3. Phase B: parity tests

Run each check twice (once against live Supabase, once against the seeded
local D1) and diff. Ship the diff, not just green ticks.

1. **Row counts + checksums per table** (DIG-2893 verification output): every
   twelve-x table, counts equal, per-table checksum equal. Type-mapping
   risks to watch (from the DDL draft): `numeric` to REAL money precision,
   `timestamptz` to TEXT ISO ordering, arrays/`jsonb` to TEXT json key order.
2. **Desk outputs**: `scripts/parity_pricing.py` in twelve-x and the
   `digisearch_parity_check.yml` workflow are the existing parity models;
   extend, do not fork. `tests/test_confirm_feed_published.py` must pass
   against both backends with identical verdicts.
3. **Dashboard reads**: the `dashboard-api` stub doubles already serve fixed
   fixtures; after the D1 data API Worker (DIG-2895) lands, the same
   dashboard routes must return byte-identical payloads from Supabase and
   from local D1 for a frozen `run_date`.
4. **pg_cron jobs stay on Supabase paths** throughout (DIG-2897): the four
   jobs (`prices-live-day`, `prices-live-late`, checkpoint prune, vacuum)
   keep firing on Postgres until cutover. The Grok Bot design
   (`prices-live` DO alarm + checkpoint SqliteSaver on the runner with R2
   archive) is the cutover target, not the dry-run setup.

Acceptance: all four checks diff-clean on the same snapshot. Any diff stops
the runbook at Phase B and goes back to the owning ticket (2, 4, 5, 7, or 8)
with the diff attached. It never goes forward as "close enough".

## 4. Phase C: switch (procedure only; executes only with Chris)

Preconditions: Phases A + B diff-clean, DIG-2892 review approved, Chris
explicit approval (promotion-style: prepared change, Chris approves; the
merge queue rule for `main` applies by analogy — nothing into prod without
his explicit go).

1. Freeze twelve-x writes: pause the writer paths (daily_run workflows stay
   green but write to Supabase, which remains primary until the flip).
2. Final snapshot + final seeded import + final Phase B diff on the fresh
   snapshot. The diff must be clean on cutover-day data, not on last week's.
3. Flip read paths per the caller map (DIG-2889) behind flags (default
   Supabase, same pattern as `NEXT_PUBLIC_LIVE_PRICES_TRANSPORT=supabase|do`
   in the prices-live design): dashboard first, then twelve-x readers, then
   writers. One lane at a time, each with a Phase B re-check.
4. db-migrate: after the flip, Supabase DDL is frozen (no new migration
   files, no workflow dispatch). The ledger stays as the record of what was
   applied.
5. Observe for the agreed window (recommendation: one full daily cycle plus
   the Monday-Friday prices-live window) before declaring the cutover done.

## 5. Phase D: rollback (Supabase is the rollback)

Supabase is never deleted, paused, or pruned during the 2-week rollback
window. Rollback at any point before window expiry:

1. Flip the read flags back to Supabase (reverse order of Phase C step 3).
   Rollback is a flag flip, not a data migration: Supabase kept receiving
   writes until the Phase C flip, and after the flip the window's writes
   live in D1/R2.
2. If writes reached D1 before rollback: replay them into Supabase from the
   R2-archived runner outputs and the D1 export (procedure to be written
   against the DIG-2893 import tooling in reverse; until that tooling
   exists, rollback after write-flip requires a written replay plan
   approved by the CTO — prefer rolling back before the write flip).
3. Resume/confirm the four pg_cron jobs on Postgres (they never stopped).
4. Post-mortem on the issue: the Phase B diff that forced rollback, attached.

## 6. Ready-to-cut-over checklist (the ticket's stop point)

- [ ] Gate 0: snapshot verified (manifest + SHA-256 + R2 read-back).
- [ ] Phase A DATA: local D1 seeded from the snapshot, clean apply.
- [ ] Phase B: all four checks diff-clean on the same snapshot.
- [ ] DIG-2892 review approved; DIG-2895/DIG-2896/DIG-2898/DIG-2900 ports
      needed for the flip lanes are merged into `develop`.
- [ ] Phase C/D procedures reviewed in the Tuesday/Thursday batch.
- [ ] Ask Chris: explicit go for cutover (and only then does Phase C execute).

## Appendix: references

- Epic DIG-2887; tickets DIG-2888 (PR #5408), DIG-2890, DIG-2892, DIG-2893,
  DIG-2901 (PR #5405), DIG-2903 (core runbook, after twelve-x).
- Plan/status docs named in the brief (`/workspace/release/...`, Grok Bot
  box) were not reachable from this checkout; this runbook is written from
  the repo state (PR #5405/#5408 diffs, twelve-x `config.py`,
  `db-migrate.yml`, `daily_run_reusable.yml`) instead.
- digithings brand: one word, all lowercase, everywhere.
