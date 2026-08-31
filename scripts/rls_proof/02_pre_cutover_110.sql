-- ============================================================================
-- Pre-cutover 110 proof — anon house-only private books (BEFORE 900)
-- ============================================================================
-- Seed must already be applied. Cutover 900 must NOT have run yet: anon is
-- expected to see the house book (1 position) and zero overlay rows.
-- Post-cutover 02_proof.sql expects anon positions = 0.
-- ============================================================================
\set ON_ERROR_STOP on
\echo '=== 110 PRE-CUTOVER PROOF: begin ==='

DROP TABLE IF EXISTS public.rls_110_results;
CREATE TABLE public.rls_110_results (
    id serial PRIMARY KEY,
    identity text NOT NULL,
    query_label text NOT NULL,
    expected text NOT NULL,
    actual text NOT NULL,
    pass boolean NOT NULL
);

CREATE OR REPLACE FUNCTION public._rls_110_probe(
    p_identity text,
    p_label text,
    p_role text,
    p_claims text,
    p_sql text,
    p_expected text
) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    n text;
BEGIN
    PERFORM set_config('request.jwt.claims', coalesce(p_claims, ''), false);
    EXECUTE format('SET ROLE %I', p_role);
    BEGIN
        EXECUTE p_sql INTO n;
    EXCEPTION
        WHEN insufficient_privilege THEN n := 'permission_denied';
        WHEN undefined_table THEN n := 'undefined_table';
        WHEN OTHERS THEN n := 'error:' || SQLSTATE;
    END;
    RESET ROLE;
    INSERT INTO public.rls_110_results(identity, query_label, expected, actual, pass)
    VALUES (p_identity, p_label, p_expected, n, n IS NOT DISTINCT FROM p_expected);
    RAISE NOTICE '110 % | % | expected=% | actual=% | %',
        p_identity, p_label, p_expected, n,
        CASE WHEN n IS NOT DISTINCT FROM p_expected THEN 'PASS' ELSE 'FAIL' END;
END;
$$;

-- anon sees house book only (seed: 1 house + 2 overlay → 1)
SELECT public._rls_110_probe(
    'anon', 'positions_total', 'anon', '',
    'SELECT count(*)::text FROM public.positions', '1'
);
SELECT public._rls_110_probe(
    'anon', 'overlay_positions_hidden', 'anon', '',
    'SELECT count(*)::text FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''',
    '0'
);
SELECT public._rls_110_probe(
    'anon', 'overlay_docs_hidden', 'anon', '',
    'SELECT count(*)::text FROM public.documents WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''',
    '0'
);
SELECT public._rls_110_probe(
    'anon', 'house_research_doc', 'anon', '',
    'SELECT count(*)::text FROM public.documents WHERE document_key = ''analyst/macro-note''',
    '1'
);
SELECT public._rls_110_probe(
    'anon', 'system_research_doc', 'anon', '',
    'SELECT count(*)::text FROM public.documents WHERE document_key = ''research/system-dive''',
    '1'
);
-- Pre-900: house pm-rebalance is still a house document (110 does not denylist keys)
SELECT public._rls_110_probe(
    'anon', 'house_pm_rebalance_still_visible', 'anon', '',
    'SELECT count(*)::text FROM public.documents WHERE document_key = ''pm-rebalance''',
    '1'
);

-- Member isolation still holds under 109+110 (authenticated)
SELECT public._rls_110_probe(
    'user_a_custom', 'own_positions', 'authenticated',
    '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"custom"}}',
    'SELECT count(*)::text FROM public.positions WHERE workspace_id = ''a1111111-1111-4111-8111-111111111111''',
    '1'
);
SELECT public._rls_110_probe(
    'user_a_custom', 'peer_positions_hidden', 'authenticated',
    '{"sub":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","role":"authenticated","app_metadata":{"plan_tier":"custom"}}',
    'SELECT count(*)::text FROM public.positions WHERE workspace_id = ''b2222222-2222-4222-8222-222222222222''',
    '0'
);

DO $$
DECLARE
    failed int;
BEGIN
    SELECT count(*) INTO failed FROM public.rls_110_results WHERE NOT pass;
    IF failed > 0 THEN
        RAISE EXCEPTION '110 pre-cutover proof FAILED (% assertion(s))', failed;
    END IF;
    RAISE NOTICE '110 pre-cutover proof PASSED: all assertions green';
END $$;

DROP FUNCTION public._rls_110_probe(text, text, text, text, text, text);

\echo '=== 110 PRE-CUTOVER PROOF: pass ==='
SELECT identity, query_label, expected, actual, pass FROM public.rls_110_results ORDER BY id;
