# dashboard-api local D1 (DIG-2901, supabase exit 13)

Local parity for `dashboard-api` without touching prod:

- `wrangler.local.toml` — local-only config. No routes, no secrets, no
  Supabase vars (worker serves stub doubles). Never deployed.
- `migrations/` — schema-only DDL auto-applied by `wrangler dev --local`
  on every `./scripts/run_stack_local.sh` boot. Real DDL arrives via
  DIG-2890 / DIG-2891; `0001_schema.sql` is a placeholder proving the path.
- Seeding — gated on ticket 0 (DIG-2888). Until
  `$SUPABASE_EXIT_SNAPSHOT_DIR` (default `~/Backups/supabase-exit`)
  contains a snapshot, the stack boots schema-only. Afterwards ticket 5
  (DIG-2893) owns the `pg dump -> batched D1 import` path; the script
  applies `<snapshot>/d1-seed.sql` via `wrangler d1 execute --local`
  when present and otherwise stays schema-only.

Rules (from the epic): nothing here deploys to Cloudflare prod, nothing
reads or writes Supabase, and no production cutover happens without Chris.
