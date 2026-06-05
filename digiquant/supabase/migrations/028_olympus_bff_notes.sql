-- REM-036 skeleton: Olympus BFF reads via service role (Next.js route), not anon RLS.
-- No policy changes in this migration; documents future tighten when OLYMPUS_USE_BFF=1 is default.
-- See frontend/olympus/README.md and docs/reviews/REM-deferred-ops.md

COMMENT ON TABLE daily_snapshots IS
  'Olympus dashboard rows. Public static export uses anon_read (011); optional BFF uses service role server-side.';
