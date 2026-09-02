-- ============================================================================
-- RLS isolation proof matrix (post-cutover)
-- SET ROLE inside DO (invoker); capture into _probe only AFTER RESET ROLE.
-- ============================================================================
\set ON_ERROR_STOP on
\echo '=== PROOF: begin matrix ==='

DROP TABLE IF EXISTS public.rls_proof_results;
CREATE TABLE public.rls_proof_results (
  id serial PRIMARY KEY,
  identity text NOT NULL,
  family text NOT NULL,
  query_label text NOT NULL,
  expected text NOT NULL,
  actual text NOT NULL,
  pass boolean NOT NULL,
  detail text
);

CREATE TEMP TABLE IF NOT EXISTS _probe (actual text);

-- anon / positions / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'positions', 'count_all', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / position_events / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.position_events' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'position_events', 'count_all', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.position_events'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / nav_history / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.nav_history' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'nav_history', 'count_all', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.nav_history'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / portfolio_metrics / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_metrics' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'portfolio_metrics', 'count_all', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.portfolio_metrics'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / daily_snapshots / base_count
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.daily_snapshots' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'daily_snapshots', 'base_count', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.daily_snapshots'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / portfolio_ledger / commits
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_ledger_commits' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'portfolio_ledger', 'commits', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.portfolio_ledger_commits'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / olympus_accounting / periods
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.olympus_accounting_periods' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'olympus_accounting', 'periods', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.olympus_accounting_periods'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / broker_connections / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.broker_connections' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'broker_connections', 'count_all', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.broker_connections'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / notification_prefs / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.notification_prefs' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'notification_prefs', 'count_all', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.notification_prefs'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / olympus_profile_config / count_all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.olympus_profile_config' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'olympus_profile_config', 'count_all', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.olympus_profile_config'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / documents / weight_pm_rebalance
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'documents', 'weight_pm_rebalance', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / documents / overlay_docs
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE workspace_id NOT IN (''6b753576-ced9-5319-9bfa-c5d0aacd9319''::uuid,''1105372f-4109-5815-be5a-21091ccfc8ad''::uuid)' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'documents', 'overlay_docs', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.documents WHERE workspace_id NOT IN (''6b753576-ced9-5319-9bfa-c5d0aacd9319''::uuid,''1105372f-4109-5815-be5a-21091ccfc8ad''::uuid)'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / views / public_portfolio_positions
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_portfolio_positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'views', 'public_portfolio_positions', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_portfolio_positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / views / public_nav_history
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_nav_history' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'views', 'public_nav_history', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_nav_history'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / views / public_accounting_nav_history
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_accounting_nav_history' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'views', 'public_accounting_nav_history', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_accounting_nav_history'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / views / public_finalized_nav
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_finalized_nav' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'views', 'public_finalized_nav', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_finalized_nav'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / views / public_daily_realized_attribution
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_daily_realized_attribution' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'views', 'public_daily_realized_attribution', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_daily_realized_attribution'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / views / public_accounting_period_status
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_accounting_period_status' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'views', 'public_accounting_period_status', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_accounting_period_status'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / research / public_daily_research
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_daily_research' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'research', 'public_daily_research', '>0', p.actual,
  CASE
    WHEN '>0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '>0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '>0'
  END,
  'SELECT count(*) FROM public.public_daily_research'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / research / research_has_portfolio_key
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_daily_research WHERE research_snapshot ? ''portfolio''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'research', 'research_has_portfolio_key', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.public_daily_research WHERE research_snapshot ? ''portfolio'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / research / theses_shared
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.theses' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'research', 'theses_shared', '>0', p.actual,
  CASE
    WHEN '>0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '>0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '>0'
  END,
  'SELECT count(*) FROM public.theses'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- anon / research / house_non_weight_docs
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '', false);
  EXECUTE 'SET ROLE anon';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE document_key = ''analyst/macro-note''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'anon', 'research', 'house_non_weight_docs', '>0', p.actual,
  CASE
    WHEN '>0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '>0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '>0'
  END,
  'SELECT count(*) FROM public.documents WHERE document_key = ''analyst/macro-note'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / positions / own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'positions', 'own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / positions / peer_b
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'positions', 'peer_b', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / positions / house
-- Post-cutover (900 A2): 109 house-teaser UUID is gone; non-members see 0.
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions WHERE workspace_id = ''6b753576-ced9-5319-9bfa-c5d0aacd9319''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'positions', 'house', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''6b753576-ced9-5319-9bfa-c5d0aacd9319'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / position_events / own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.position_events WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'position_events', 'own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.position_events WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / position_events / peer_b
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.position_events WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'position_events', 'peer_b', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.position_events WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / nav_history / own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.nav_history WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'nav_history', 'own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.nav_history WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / nav_history / peer_b
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.nav_history WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'nav_history', 'peer_b', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.nav_history WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / portfolio_metrics / own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_metrics WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'portfolio_metrics', 'own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.portfolio_metrics WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / portfolio_metrics / peer_b
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_metrics WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'portfolio_metrics', 'peer_b', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.portfolio_metrics WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / portfolio_ledger / commits_own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'portfolio_ledger', 'commits_own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / portfolio_ledger / commits_peer
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'portfolio_ledger', 'commits_peer', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / olympus_accounting / periods_own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.olympus_accounting_periods WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'olympus_accounting', 'periods_own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.olympus_accounting_periods WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / olympus_accounting / periods_peer
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.olympus_accounting_periods WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'olympus_accounting', 'periods_peer', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.olympus_accounting_periods WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / olympus_profile_config / overlay_own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.olympus_profile_config WHERE id = ''aa000020-0020-4020-8020-000000000020''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'olympus_profile_config', 'overlay_own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.olympus_profile_config WHERE id = ''aa000020-0020-4020-8020-000000000020'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / documents / overlay_own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'documents', 'overlay_own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / documents / overlay_peer
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'documents', 'overlay_peer', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.documents WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / documents / house_pm_rebalance_tier
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'documents', 'house_pm_rebalance_tier', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / broker_connections / no_client_grant
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.broker_connections' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'broker_connections', 'no_client_grant', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.broker_connections'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / notification_prefs / no_client_grant
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.notification_prefs' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'notification_prefs', 'no_client_grant', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.notification_prefs'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / daily_snapshots / base_revoked
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.daily_snapshots' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'daily_snapshots', 'base_revoked', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.daily_snapshots'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_a_studio / views / public_portfolio_positions
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"studio"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_portfolio_positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_a_studio', 'views', 'public_portfolio_positions', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_portfolio_positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_b_desk / positions / own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"desk"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_b_desk', 'positions', 'own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_b_desk / positions / peer_a
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"desk"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_b_desk', 'positions', 'peer_a', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_b_desk / portfolio_ledger / commits_own
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"desk"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_b_desk', 'portfolio_ledger', 'commits_own', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_b_desk / portfolio_ledger / commits_peer
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"desk"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_b_desk', 'portfolio_ledger', 'commits_peer', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.portfolio_ledger_commits WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_b_desk / documents / house_pm_rebalance_tier
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"desk"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_b_desk', 'documents', 'house_pm_rebalance_tier', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_b_desk / documents / overlay_peer_a
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","role":"authenticated","app_metadata":{"plan_tier":"desk"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_b_desk', 'documents', 'overlay_peer_a', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_c_free / documents / house_pm_rebalance_blocked
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"cccccccc-cccc-cccc-cccc-cccccccccccc","role":"authenticated","app_metadata":{"plan_tier":"free"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_c_free', 'documents', 'house_pm_rebalance_blocked', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.documents WHERE document_key = ''pm-rebalance'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_c_free / documents / house_research_ok
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"cccccccc-cccc-cccc-cccc-cccccccccccc","role":"authenticated","app_metadata":{"plan_tier":"free"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents WHERE document_key = ''analyst/macro-note''' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_c_free', 'documents', 'house_research_ok', '>0', p.actual,
  CASE
    WHEN '>0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '>0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '>0'
  END,
  'SELECT count(*) FROM public.documents WHERE document_key = ''analyst/macro-note'''
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_c_free / research / public_daily_research
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"cccccccc-cccc-cccc-cccc-cccccccccccc","role":"authenticated","app_metadata":{"plan_tier":"free"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_daily_research' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_c_free', 'research', 'public_daily_research', '>0', p.actual,
  CASE
    WHEN '>0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '>0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '>0'
  END,
  'SELECT count(*) FROM public.public_daily_research'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_c_free / positions / no_private
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"cccccccc-cccc-cccc-cccc-cccccccccccc","role":"authenticated","app_metadata":{"plan_tier":"free"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_c_free', 'positions', 'no_private', '0', p.actual,
  CASE
    WHEN '0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0'
  END,
  'SELECT count(*) FROM public.positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- user_c_free / views / public_portfolio_positions
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"sub":"cccccccc-cccc-cccc-cccc-cccccccccccc","role":"authenticated","app_metadata":{"plan_tier":"free"}}', false);
  EXECUTE 'SET ROLE authenticated';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_portfolio_positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'user_c_free', 'views', 'public_portfolio_positions', '0|permission_denied', p.actual,
  CASE
    WHEN '0|permission_denied' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '0|permission_denied' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '0|permission_denied'
  END,
  'SELECT count(*) FROM public.public_portfolio_positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- service_role / positions / all_rows
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"role":"service_role"}', false);
  EXECUTE 'SET ROLE service_role';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'service_role', 'positions', 'all_rows', '3', p.actual,
  CASE
    WHEN '3' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '3' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '3'
  END,
  'SELECT count(*) FROM public.positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- service_role / documents / all_docs
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"role":"service_role"}', false);
  EXECUTE 'SET ROLE service_role';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.documents' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'service_role', 'documents', 'all_docs', '5', p.actual,
  CASE
    WHEN '5' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '5' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '5'
  END,
  'SELECT count(*) FROM public.documents'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- service_role / broker_connections / all
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"role":"service_role"}', false);
  EXECUTE 'SET ROLE service_role';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.broker_connections' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'service_role', 'broker_connections', 'all', '2', p.actual,
  CASE
    WHEN '2' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '2' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '2'
  END,
  'SELECT count(*) FROM public.broker_connections'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- service_role / daily_snapshots / base
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"role":"service_role"}', false);
  EXECUTE 'SET ROLE service_role';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.daily_snapshots' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'service_role', 'daily_snapshots', 'base', '1', p.actual,
  CASE
    WHEN '1' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '1' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '1'
  END,
  'SELECT count(*) FROM public.daily_snapshots'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;
-- service_role / views / public_portfolio_positions
TRUNCATE _probe;
DO $$
DECLARE
  n bigint;
  a text;
BEGIN
  PERFORM set_config('request.jwt.claims', '{"role":"service_role"}', false);
  EXECUTE 'SET ROLE service_role';
  BEGIN
    EXECUTE 'SELECT count(*) FROM public.public_portfolio_positions' INTO n;
    a := n::text;
  EXCEPTION
    WHEN insufficient_privilege THEN a := 'permission_denied';
    WHEN undefined_table THEN a := 'undefined_table';
    WHEN OTHERS THEN a := 'error:' || SQLSTATE || ':' || left(SQLERRM, 160);
  END;
  RESET ROLE;
  INSERT INTO _probe VALUES (a);
END $$;
INSERT INTO public.rls_proof_results(identity, family, query_label, expected, actual, pass, detail)
SELECT 'service_role', 'views', 'public_portfolio_positions', '>0', p.actual,
  CASE
    WHEN '>0' = '>0' THEN p.actual ~ '^[0-9]+$' AND p.actual::bigint > 0
    WHEN '>0' = '0|permission_denied' THEN p.actual IN ('0', 'permission_denied')
    ELSE p.actual = '>0'
  END,
  'SELECT count(*) FROM public.public_portfolio_positions'
FROM _probe p;
DO $$
DECLARE r public.rls_proof_results%ROWTYPE;
BEGIN
  SELECT * INTO r FROM public.rls_proof_results ORDER BY id DESC LIMIT 1;
  RAISE NOTICE 'PROOF % | % | % | expected=% | actual=% | %',
    r.identity, r.family, r.query_label, r.expected, r.actual,
    CASE WHEN r.pass THEN 'PASS' ELSE 'FAIL' END;
END $$;

\echo '=== PROOF: results table ==='
SELECT identity, family, query_label, expected, actual, pass
FROM public.rls_proof_results ORDER BY id;

\echo '=== PROOF: summary ==='
SELECT count(*) AS total,
       count(*) FILTER (WHERE pass) AS passed,
       count(*) FILTER (WHERE NOT pass) AS failed
FROM public.rls_proof_results;

DO $$
DECLARE fails int;
BEGIN
  SELECT count(*) INTO fails FROM public.rls_proof_results WHERE NOT pass;
  IF fails > 0 THEN
    RAISE EXCEPTION 'RLS proof FAILED: % assertion(s) failed — see rls_proof_results', fails;
  END IF;
  RAISE NOTICE 'RLS proof PASSED: all assertions green';
END $$;
