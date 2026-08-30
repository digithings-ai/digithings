-- ============================================================================
-- RLS isolation proof matrix (post-cutover)
-- ============================================================================
-- For each identity: SET ROLE + set_config(request.jwt.claims) then count rows.
-- Captures expected vs actual. Exit via proof_failures table.
-- ============================================================================

\set ON_ERROR_STOP on
\echo '=== PROOF: begin matrix ==='

DROP TABLE IF EXISTS proof_results;
CREATE TEMP TABLE proof_results (
  identity text NOT NULL,
  family text NOT NULL,
  query_label text NOT NULL,
  expected text NOT NULL,
  actual text NOT NULL,
  pass boolean NOT NULL,
  detail text
);

CREATE OR REPLACE FUNCTION pg_temp.safe_count(sql text)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
  n bigint;
BEGIN
  EXECUTE sql INTO n;
  RETURN n::text;
EXCEPTION
  WHEN insufficient_privilege THEN
    RETURN 'permission_denied';
  WHEN undefined_table THEN
    RETURN 'undefined_table';
  WHEN OTHERS THEN
    RETURN 'error:' || SQLSTATE || ':' || SQLERRM;
END;
$$;

CREATE OR REPLACE FUNCTION pg_temp.record_proof(
  p_identity text,
  p_family text,
  p_label text,
  p_expected text,
  p_sql text
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  a text;
  ok boolean;
BEGIN
  a := pg_temp.safe_count(p_sql);
  -- expected may be '0', '>0', 'permission_denied', or '0|permission_denied'
  IF p_expected = '>0' THEN
    ok := (a ~ '^[0-9]+$' AND a::bigint > 0);
  ELSIF p_expected = '0|permission_denied' THEN
    ok := (a = '0' OR a = 'permission_denied');
  ELSIF p_expected = 'false' THEN
    -- boolean query returning text 't'/'f' or 'true'/'false'
    ok := (a IN ('f', 'false', '0'));
  ELSE
    ok := (a = p_expected);
  END IF;
  INSERT INTO proof_results(identity, family, query_label, expected, actual, pass, detail)
  VALUES (p_identity, p_family, p_label, p_expected, a, ok, p_sql);
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    p_identity, p_family, p_label, p_expected, a,
    CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END;
END;
$$;

-- Helper: assume identity
-- claims_json must include sub + role + app_metadata.plan_tier

-- ---------------------------------------------------------------------------
-- ANON
-- ---------------------------------------------------------------------------
RESET ROLE;
SELECT set_config('request.jwt.claims', '', true);
SET ROLE anon;

SELECT pg_temp.record_proof('anon', 'positions', 'count_all', '0',
  'SELECT count(*) FROM public.positions');
SELECT pg_temp.record_proof('anon', 'position_events', 'count_all', '0',
  'SELECT count(*) FROM public.position_events');
SELECT pg_temp.record_proof('anon', 'nav_history', 'count_all', '0',
  'SELECT count(*) FROM public.nav_history');
SELECT pg_temp.record_proof('anon', 'portfolio_metrics', 'count_all', '0',
  'SELECT count(*) FROM public.portfolio_metrics');
SELECT pg_temp.record_proof('anon', 'daily_snapshots', 'base_count', '0|permission_denied',
  'SELECT count(*) FROM public.daily_snapshots');
SELECT pg_temp.record_proof('anon', 'portfolio_ledger', 'commits', '0|permission_denied',
  'SELECT count(*) FROM public.portfolio_ledger_commits');
SELECT pg_temp.record_proof('anon', 'olympus_accounting', 'periods', '0|permission_denied',
  'SELECT count(*) FROM public.olympus_accounting_periods');
SELECT pg_temp.record_proof('anon', 'broker_connections', 'count_all', '0|permission_denied',
  'SELECT count(*) FROM public.broker_connections');
SELECT pg_temp.record_proof('anon', 'notification_prefs', 'count_all', '0|permission_denied',
  'SELECT count(*) FROM public.notification_prefs');
SELECT pg_temp.record_proof('anon', 'olympus_profile_config', 'count_all', '0|permission_denied',
  'SELECT count(*) FROM public.olympus_profile_config');
SELECT pg_temp.record_proof('anon', 'documents', 'weight_pm_rebalance', '0',
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''');
SELECT pg_temp.record_proof('anon', 'documents', 'overlay_docs', '0',
  'SELECT count(*) FROM public.documents WHERE workspace_id NOT IN (
     ''6b753576-ced9-5319-9bfa-c5d0aacd9319''::uuid,
     ''1105372f-4109-5815-be5a-21091ccfc8ad''::uuid)');
SELECT pg_temp.record_proof('anon', 'views', 'public_portfolio_positions', '0|permission_denied',
  'SELECT count(*) FROM public.public_portfolio_positions');
SELECT pg_temp.record_proof('anon', 'views', 'public_nav_history', '0|permission_denied',
  'SELECT count(*) FROM public.public_nav_history');
SELECT pg_temp.record_proof('anon', 'views', 'public_accounting_nav_history', '0|permission_denied',
  'SELECT count(*) FROM public.public_accounting_nav_history');
SELECT pg_temp.record_proof('anon', 'views', 'public_finalized_nav', '0|permission_denied',
  'SELECT count(*) FROM public.public_finalized_nav');
SELECT pg_temp.record_proof('anon', 'views', 'public_daily_realized_attribution', '0|permission_denied',
  'SELECT count(*) FROM public.public_daily_realized_attribution');
SELECT pg_temp.record_proof('anon', 'views', 'public_accounting_period_status', '0|permission_denied',
  'SELECT count(*) FROM public.public_accounting_period_status');
SELECT pg_temp.record_proof('anon', 'research', 'public_daily_research', '>0',
  'SELECT count(*) FROM public.public_daily_research');
SELECT pg_temp.record_proof('anon', 'research', 'research_has_portfolio_key', '0',
  'SELECT count(*) FROM public.public_daily_research WHERE research_snapshot ? ''portfolio''');
SELECT pg_temp.record_proof('anon', 'research', 'theses_shared', '>0',
  'SELECT count(*) FROM public.theses');
SELECT pg_temp.record_proof('anon', 'research', 'house_non_weight_docs', '>0',
  'SELECT count(*) FROM public.documents WHERE document_key = ''analyst/macro-note''');

-- ---------------------------------------------------------------------------
-- USER A (custom) — own workspace only
-- ---------------------------------------------------------------------------
RESET ROLE;
SELECT set_config(
  'request.jwt.claims',
  '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"custom"}}',
  false
);
SET ROLE authenticated;

SELECT pg_temp.record_proof('user_a_custom', 'positions', 'own', '1',
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'positions', 'peer_b', '0',
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'positions', 'house', '0',
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''6b753576-ced9-5319-9bfa-c5d0aacd9319''');
SELECT pg_temp.record_proof('user_a_custom', 'position_events', 'own', '1',
  'SELECT count(*) FROM public.position_events WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'position_events', 'peer_b', '0',
  'SELECT count(*) FROM public.position_events WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'nav_history', 'own', '1',
  'SELECT count(*) FROM public.nav_history WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'nav_history', 'peer_b', '0',
  'SELECT count(*) FROM public.nav_history WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'portfolio_metrics', 'own', '1',
  'SELECT count(*) FROM public.portfolio_metrics WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'portfolio_metrics', 'peer_b', '0',
  'SELECT count(*) FROM public.portfolio_metrics WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'portfolio_ledger', 'commits_own', '1',
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'portfolio_ledger', 'commits_peer', '0',
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'olympus_accounting', 'periods_own', '1',
  'SELECT count(*) FROM public.olympus_accounting_periods WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'olympus_accounting', 'periods_peer', '0',
  'SELECT count(*) FROM public.olympus_accounting_periods WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'olympus_profile_config', 'overlay_own', '1',
  'SELECT count(*) FROM public.olympus_profile_config WHERE id = ''aa000020-0020-4020-8020-000000000020''');
SELECT pg_temp.record_proof('user_a_custom', 'documents', 'overlay_own', '1',
  'SELECT count(*) FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_a_custom', 'documents', 'overlay_peer', '0',
  'SELECT count(*) FROM public.documents WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_a_custom', 'documents', 'house_pm_rebalance_tier', '1',
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''');
SELECT pg_temp.record_proof('user_a_custom', 'broker_connections', 'no_client_grant', '0|permission_denied',
  'SELECT count(*) FROM public.broker_connections');
SELECT pg_temp.record_proof('user_a_custom', 'notification_prefs', 'no_client_grant', '0|permission_denied',
  'SELECT count(*) FROM public.notification_prefs');
SELECT pg_temp.record_proof('user_a_custom', 'daily_snapshots', 'base_revoked', '0|permission_denied',
  'SELECT count(*) FROM public.daily_snapshots');
SELECT pg_temp.record_proof('user_a_custom', 'views', 'public_portfolio_positions', '0|permission_denied',
  'SELECT count(*) FROM public.public_portfolio_positions');

-- ---------------------------------------------------------------------------
-- USER B (baseline) — isolation + can read house weight docs
-- ---------------------------------------------------------------------------
RESET ROLE;
SELECT set_config(
  'request.jwt.claims',
  '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"baseline"}}',
  false
);
SET ROLE authenticated;

SELECT pg_temp.record_proof('user_b_baseline', 'positions', 'own', '1',
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_b_baseline', 'positions', 'peer_a', '0',
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_b_baseline', 'portfolio_ledger', 'commits_own', '1',
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''');
SELECT pg_temp.record_proof('user_b_baseline', 'portfolio_ledger', 'commits_peer', '0',
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');
SELECT pg_temp.record_proof('user_b_baseline', 'documents', 'house_pm_rebalance_tier', '1',
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''');
SELECT pg_temp.record_proof('user_b_baseline', 'documents', 'overlay_peer_a', '0',
  'SELECT count(*) FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''');

-- ---------------------------------------------------------------------------
-- USER C (free) — cannot read house weight-bearing keys
-- ---------------------------------------------------------------------------
RESET ROLE;
SELECT set_config(
  'request.jwt.claims',
  '{"sub":"cccccccc-cccc-cccc-cccc-cccccccccccc","role":"authenticated","app_metadata":{"plan_tier":"free"}}',
  false
);
SET ROLE authenticated;

SELECT pg_temp.record_proof('user_c_free', 'documents', 'house_pm_rebalance_blocked', '0',
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''');
SELECT pg_temp.record_proof('user_c_free', 'documents', 'house_research_ok', '>0',
  'SELECT count(*) FROM public.documents WHERE document_key = ''analyst/macro-note''');
SELECT pg_temp.record_proof('user_c_free', 'research', 'public_daily_research', '>0',
  'SELECT count(*) FROM public.public_daily_research');
SELECT pg_temp.record_proof('user_c_free', 'positions', 'no_private', '0',
  'SELECT count(*) FROM public.positions');
SELECT pg_temp.record_proof('user_c_free', 'views', 'public_portfolio_positions', '0|permission_denied',
  'SELECT count(*) FROM public.public_portfolio_positions');

-- ---------------------------------------------------------------------------
-- SERVICE_ROLE — bypass sanity
-- ---------------------------------------------------------------------------
RESET ROLE;
SELECT set_config('request.jwt.claims', '{"role":"service_role"}', false);
SET ROLE service_role;

SELECT pg_temp.record_proof('service_role', 'positions', 'all_rows', '3',
  'SELECT count(*) FROM public.positions');
SELECT pg_temp.record_proof('service_role', 'documents', 'all_docs', '5',
  'SELECT count(*) FROM public.documents');
SELECT pg_temp.record_proof('service_role', 'broker_connections', 'all', '2',
  'SELECT count(*) FROM public.broker_connections');
SELECT pg_temp.record_proof('service_role', 'daily_snapshots', 'base', '1',
  'SELECT count(*) FROM public.daily_snapshots');
SELECT pg_temp.record_proof('service_role', 'views', 'public_portfolio_positions', '>0',
  'SELECT count(*) FROM public.public_portfolio_positions');

RESET ROLE;

\echo '=== PROOF: results table ==='
SELECT identity, family, query_label, expected, actual, pass
FROM proof_results
ORDER BY identity, family, query_label;

\echo '=== PROOF: summary ==='
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE pass) AS passed,
  count(*) FILTER (WHERE NOT pass) AS failed
FROM proof_results;

DO $$
DECLARE
  fails int;
BEGIN
  SELECT count(*) INTO fails FROM proof_results WHERE NOT pass;
  IF fails > 0 THEN
    RAISE EXCEPTION 'RLS proof FAILED: % assertion(s) failed — see proof_results', fails;
  END IF;
  RAISE NOTICE 'RLS proof PASSED: all assertions green';
END $$;
