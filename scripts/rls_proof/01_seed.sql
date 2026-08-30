-- ============================================================================
-- Seed: two tenants + free observer + representative private rows
-- ============================================================================
-- Runs as table owner / superuser (bypasses RLS) AFTER migrations + cutover.
-- Deterministic UUIDs for proof assertions.
-- ============================================================================

\echo '=== SEED: begin ==='

-- Fixed ids
-- user-a (custom), user-b (baseline), user-c (free)
-- ws-a, ws-b, ws-c
DO $$
DECLARE
  user_a uuid := 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  user_b uuid := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  user_c uuid := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
  ws_a   uuid := 'a1111111-1111-4111-8111-111111111111';
  ws_b   uuid := 'b2222222-2222-4222-8222-222222222222';
  ws_c   uuid := 'c3333333-3333-4333-8333-333333333333';
  house  uuid := '6b753576-ced9-5319-9bfa-c5d0aacd9319';
  system uuid := '1105372f-4109-5815-be5a-21091ccfc8ad';
  commit_a uuid := 'aa000001-0001-4001-8001-000000000001';
  commit_b uuid := 'bb000001-0001-4001-8001-000000000001';
  intent_a uuid := 'aa000002-0002-4002-8002-000000000002';
  intent_b uuid := 'bb000002-0002-4002-8002-000000000002';
  req_a    uuid := 'aa000003-0003-4003-8003-000000000003';
  req_b    uuid := 'bb000003-0003-4003-8003-000000000003';
  period_a uuid := 'aa000010-0010-4010-8010-000000000010';
  period_b uuid := 'bb000010-0010-4010-8010-000000000010';
  overlay_a uuid := 'aa000020-0020-4020-8020-000000000020';
  run_a date := '2026-08-01';
  run_b date := '2026-08-02';
  house_date date := '2026-08-03';
BEGIN
  INSERT INTO auth.users (id) VALUES (user_a), (user_b), (user_c)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.workspaces (id, slug, type, name, plan_tier, subscription_status)
  VALUES
    (ws_a, 'tenant-a-custom', 'user', 'Tenant A Custom', 'custom', 'active'),
    (ws_b, 'tenant-b-baseline', 'user', 'Tenant B Baseline', 'baseline', 'active'),
    (ws_c, 'tenant-c-free', 'user', 'Tenant C Free', 'free', 'none')
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.workspace_members (workspace_id, user_id, role)
  VALUES
    (ws_a, user_a, 'owner'),
    (ws_b, user_b, 'owner'),
    (ws_c, user_c, 'owner')
  ON CONFLICT DO NOTHING;

  -- Group A private book (legacy UNIQUE(date[,ticker]) still active — distinct dates/tickers)
  INSERT INTO public.positions (date, ticker, name, category, weight_pct, workspace_id)
  VALUES
    (run_a, 'AAA', 'Asset A', 'equity_broad', 40, ws_a),
    (run_b, 'BBB', 'Asset B', 'equity_broad', 55, ws_b),
    (house_date, 'HOUSE', 'House Asset', 'equity_broad', 25, house)
  ON CONFLICT DO NOTHING;

  INSERT INTO public.position_events (date, ticker, event, weight_pct, workspace_id)
  VALUES
    (run_a, 'AAA', 'OPEN', 40, ws_a),
    (run_b, 'BBB', 'OPEN', 55, ws_b),
    (house_date, 'HOUSE', 'OPEN', 25, house)
  ON CONFLICT DO NOTHING;

  INSERT INTO public.nav_history (date, nav, cash_pct, invested_pct, workspace_id)
  VALUES
    (run_a, 100000, 0.10, 0.90, ws_a),
    (run_b, 200000, 0.20, 0.80, ws_b),
    (house_date, 500000, 0.05, 0.95, house)
  ON CONFLICT DO NOTHING;

  INSERT INTO public.portfolio_metrics (date, pnl_pct, sharpe, invested_pct, workspace_id)
  VALUES
    (run_a, 1.0, 1.2, 90, ws_a),
    (run_b, 2.0, 0.8, 80, ws_b),
    (house_date, 0.5, 1.5, 95, house)
  ON CONFLICT DO NOTHING;

  -- Minimal portfolio_ledger chain (commit → decision → requested_target) per workspace
  INSERT INTO public.portfolio_ledger_commits (
    id, run_date, policy_version_id, supersedes_id, effective_at, workspace_id
  ) VALUES
    (commit_a, run_a, 'policy-a-v1', NULL, run_a::timestamptz, ws_a),
    (commit_b, run_b, 'policy-b-v1', NULL, run_b::timestamptz, ws_b)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.portfolio_ledger_decision_intents (
    id, portfolio_commit_id, run_date, symbol, action, reason, effective_at, workspace_id
  ) VALUES
    (intent_a, commit_a, run_a, 'AAA', 'add', 'new_conviction', run_a::timestamptz, ws_a),
    (intent_b, commit_b, run_b, 'BBB', 'add', 'new_conviction', run_b::timestamptz, ws_b)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.portfolio_ledger_requested_targets (
    id, decision_intent_id, run_date, symbol, requested_weight, requested_quantity,
    effective_at, workspace_id
  ) VALUES
    (req_a, intent_a, run_a, 'AAA', 0.40, NULL, run_a::timestamptz, ws_a),
    (req_b, intent_b, run_b, 'BBB', 0.55, NULL, run_b::timestamptz, ws_b)
  ON CONFLICT (id) DO NOTHING;

  -- olympus_accounting_periods (minimal final row)
  INSERT INTO public.olympus_accounting_periods (
    id, period_date, policy_version_id, status, quality_reasons,
    opening_equity, closing_equity, opening_cash, closing_cash, cash_pnl,
    gross_pnl_total, net_pnl_total, fees_total, slippage_total, residual,
    absolute_tolerance, relative_tolerance, supersedes_id, effective_at, workspace_id
  ) VALUES
    (period_a, run_a, 'policy-a-v1', 'final', '{}'::text[],
     100000, 101000, 10000, 10000, 0,
     1000, 1000, 0, 0, 0,
     1, 0.01, NULL, run_a::timestamptz, ws_a),
    (period_b, run_b, 'policy-b-v1', 'final', '{}'::text[],
     200000, 204000, 20000, 20000, 0,
     4000, 4000, 0, 0, 0,
     1, 0.01, NULL, run_b::timestamptz, ws_b)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.olympus_accounting_contributions (
    id, period_id, period_date, symbol,
    opening_quantity, closing_quantity, gross_pnl, fees, slippage, net_pnl,
    workspace_id
  )
  SELECT gen_random_uuid(), period_a, run_a, 'AAA',
         10, 10, 1000, 0, 0, 1000, ws_a
  WHERE NOT EXISTS (
    SELECT 1 FROM public.olympus_accounting_contributions c
    WHERE c.period_id = period_a AND c.symbol = 'AAA'
  );

  INSERT INTO public.olympus_accounting_contributions (
    id, period_id, period_date, symbol,
    opening_quantity, closing_quantity, gross_pnl, fees, slippage, net_pnl,
    workspace_id
  )
  SELECT gen_random_uuid(), period_b, run_b, 'BBB',
         20, 20, 4000, 0, 0, 4000, ws_b
  WHERE NOT EXISTS (
    SELECT 1 FROM public.olympus_accounting_contributions c
    WHERE c.period_id = period_b AND c.symbol = 'BBB'
  );

  INSERT INTO public.olympus_accounting_holdings (
    id, period_id, period_date, symbol, quantity, mark, market_value, workspace_id
  )
  SELECT gen_random_uuid(), period_a, run_a, 'AAA', 10, 100, 1000, ws_a
  WHERE NOT EXISTS (
    SELECT 1 FROM public.olympus_accounting_holdings h
    WHERE h.period_id = period_a AND h.symbol = 'AAA'
  );

  INSERT INTO public.olympus_accounting_holdings (
    id, period_id, period_date, symbol, quantity, mark, market_value, workspace_id
  )
  SELECT gen_random_uuid(), period_b, run_b, 'BBB', 20, 100, 2000, ws_b
  WHERE NOT EXISTS (
    SELECT 1 FROM public.olympus_accounting_holdings h
    WHERE h.period_id = period_b AND h.symbol = 'BBB'
  );

  -- Overlay profile config (non-house) for workspace A
  INSERT INTO public.olympus_profile_config (
    id, profile_key, schema_version, is_house_default, label, payload,
    supersedes_id, workspace_id
  ) VALUES (
    overlay_a,
    'overlay-a',
    1,
    false,
    'Tenant A overlay',
    '{"profile_key":"overlay-a","schema_version":1,"is_house_default":false,"label":"Tenant A overlay","watchlist":[],"themes":[],"investment":{"schema_version":1,"risk_tolerance":"moderate","horizon_years":5,"liquidity_needs":"medium","base_currency":"USD","tax_jurisdiction":"US","esg_preference":"none","excluded_sectors":[],"experience_level":"intermediate"},"assets":null}'::jsonb,
    NULL,
    ws_a
  ) ON CONFLICT (id) DO NOTHING;

  -- broker_connections (service_role-only; ciphertext > 16 bytes, nonce = 12)
  INSERT INTO public.broker_connections (
    workspace_id, broker, env, auth_kind, ciphertext, nonce, key_id, fingerprint, scopes, status
  ) VALUES
    (ws_a, 'alpaca', 'paper', 'api_key',
     decode('00112233445566778899aabbccddeeff0011', 'hex'),
     decode('00112233445566778899aabb', 'hex'),
     'v1', 'aaaaaaaa', ARRAY['trade']::text[], 'active'),
    (ws_b, 'alpaca', 'paper', 'api_key',
     decode('ffeeddccbbaa9988776655443322110000ff', 'hex'),
     decode('ffeeddccbbaa998877665544', 'hex'),
     'v1', 'bbbbbbbb', ARRAY['trade']::text[], 'active')
  ON CONFLICT DO NOTHING;

  INSERT INTO public.notification_prefs (
    workspace_id, email, daily_digest, holding_change_alerts, execution_alerts
  ) VALUES
    (ws_a, 'a@example.com', true, true, false),
    (ws_b, 'b@example.com', false, true, true)
  ON CONFLICT (workspace_id) DO NOTHING;

  -- Documents: overlay pm-direction-memo, house pm-rebalance, shared research
  INSERT INTO public.documents (
    date, title, doc_type, category, run_type, document_key, content, payload, workspace_id
  ) VALUES
    (run_a, 'Overlay PM Direction A', 'PM Direction Memo', 'portfolio', 'baseline',
     'pm-direction-memo', 'direction only', '{}'::jsonb, ws_a),
    (run_b, 'Overlay PM Direction B', 'PM Direction Memo', 'portfolio', 'baseline',
     'pm-direction-memo', 'direction only', '{}'::jsonb, ws_b),
    (house_date, 'House PM Rebalance', 'Rebalance Decision', 'portfolio', 'baseline',
     'pm-rebalance', 'weights here', '{"recommended_portfolio":{"AAA":0.25}}'::jsonb, house),
    (house_date, 'Shared Research Note', 'Custom Research', 'macro', 'baseline',
     'analyst/macro-note', 'shared research body', '{}'::jsonb, house),
    (house_date, 'System Research', 'Deep Dive', 'macro', 'baseline',
     'research/system-dive', 'system corpus', '{}'::jsonb, system)
  ON CONFLICT DO NOTHING;

  -- daily_snapshots with weight-bearing portfolio jsonb (house/operator shape)
  INSERT INTO public.daily_snapshots (
    date, run_type, baseline_date, snapshot, digest_markdown
  ) VALUES (
    house_date,
    'baseline',
    NULL,
    jsonb_build_object(
      'portfolio', jsonb_build_object(
        'positions', jsonb_build_array(
          jsonb_build_object('ticker', 'HOUSE', 'weight_pct', 0.25)
        )
      ),
      'narrative', jsonb_build_object(
        'summary', 'research prose',
        'portfolio_recs', 'should be stripped'
      )
    ),
    E'# Digest\n| Ticker | Weight |\n| HOUSE | 25% |'
  ) ON CONFLICT DO NOTHING;

  -- Shared research row on theses (anon KEEP)
  INSERT INTO public.theses (date, thesis_id, name, status, notes)
  VALUES (house_date, 'geo-risk-gold', 'Geo Risk Gold', 'ACTIVE', 'shared thesis')
  ON CONFLICT DO NOTHING;

END $$;

\echo '=== SEED: done ==='
SELECT 'workspaces' AS t, count(*) FROM public.workspaces
UNION ALL SELECT 'auth.users', count(*) FROM auth.users
UNION ALL SELECT 'positions', count(*) FROM public.positions
UNION ALL SELECT 'documents', count(*) FROM public.documents
UNION ALL SELECT 'daily_snapshots', count(*) FROM public.daily_snapshots;
