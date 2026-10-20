-- D1 (SQLite) schema for twelve-x, ported from the live pg catalog (read-only) 2026-10-11.
-- POST-REVIEW: 9 pg table CHECKs are real constraints; 20 measured jsonb columns carry
-- json_valid(); the 1 non-btree (GIN) index is resolved as a documented decision.
-- See 0001_init.notes.md for the type map, the measured census and the OPEN items.
-- Review: ticket 'supabase exit 2' + Claude review. Types: uuid/timestamptz/date->TEXT, jsonb->TEXT(json), bool->INTEGER 0/1, numeric->REAL (check money precision), arrays->TEXT(json).
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS fx_archive_objects (
  id INTEGER NOT NULL,
  source_table TEXT NOT NULL,
  source_key TEXT NOT NULL,
  source_key_text TEXT NOT NULL,
  r2_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  owner TEXT NOT NULL DEFAULT 'twelve-x',
  archived_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  status TEXT NOT NULL DEFAULT 'active',
  PRIMARY KEY (id),
  UNIQUE (r2_key)
);

CREATE TABLE IF NOT EXISTS fx_bank_trades (
  id INTEGER NOT NULL,
  bank_trade_id INTEGER NOT NULL,
  pair TEXT NOT NULL,
  bank_name TEXT NOT NULL DEFAULT '',
  trade_date TEXT NOT NULL,
  trade_entry REAL NOT NULL,
  trade_stop_loss REAL NOT NULL,
  trade_take_profit REAL NOT NULL,
  trade_status TEXT NOT NULL DEFAULT '',
  order_type TEXT NOT NULL DEFAULT '',
  direction TEXT,
  source_slug TEXT NOT NULL DEFAULT 'bank-trades',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (bank_trade_id),
  PRIMARY KEY (id)
);

-- ported from pg_dump table CHECK: ((timeframe IS NULL) OR (timeframe = ANY (ARRAY['short'::text, 'medium'::text, 'long'::text])))
CREATE TABLE IF NOT EXISTS fx_bookkeeper_verdicts (
  run_date TEXT NOT NULL,
  axis TEXT NOT NULL,
  idea_rank INTEGER NOT NULL DEFAULT 0,
  idea_run_date TEXT NOT NULL,
  verdict TEXT NOT NULL,
  verdict_reason TEXT NOT NULL DEFAULT '',
  bookkeeper_ok INTEGER NOT NULL DEFAULT 1,
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  idea_id TEXT,
  timeframe TEXT,
  PRIMARY KEY (run_date, idea_run_date, idea_rank),
  -- ported from the pg_dump CHECK comment above
  CHECK (((timeframe IS NULL) OR (timeframe IN ('short', 'medium', 'long'))))
);

CREATE TABLE IF NOT EXISTS fx_calendar_pmt (
  id INTEGER NOT NULL,
  event_date TEXT NOT NULL,
  currency TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  event_name TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT '',
  impact TEXT NOT NULL DEFAULT 'medium',
  event_time TEXT,
  actual TEXT,
  forecast TEXT,
  prior TEXT,
  pmt_event_id TEXT NOT NULL DEFAULT '',
  updated_on TEXT,
  source_slug TEXT NOT NULL DEFAULT 'event-calendar',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (event_date, currency, normalized_name),
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS fx_confluence_snapshot (
  run_date TEXT NOT NULL,
  rank INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  currency TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL DEFAULT '',
  score REAL NOT NULL DEFAULT 0,
  components TEXT NOT NULL DEFAULT '[]' CHECK (components IS NULL OR json_valid(components)),
  brief_keys TEXT NOT NULL DEFAULT '[]' CHECK (brief_keys IS NULL OR json_valid(brief_keys)),
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (run_date, rank)
);

CREATE TABLE IF NOT EXISTS fx_consensus_eval (
  run_date TEXT NOT NULL,
  currency TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  weighted INTEGER NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  tilt REAL NOT NULL DEFAULT 0,
  agreement REAL NOT NULL DEFAULT 0,
  n_brokers INTEGER NOT NULL DEFAULT 0,
  n_brokers_prev INTEGER,
  delta_score REAL,
  delta_tilt REAL,
  delta_agreement REAL,
  delta_score_pred REAL,
  clip_flag INTEGER,
  sign_flip INTEGER,
  abs_delta_score REAL,
  accuracy_status TEXT NOT NULL DEFAULT 'carried',
  currency_ret_5d REAL,
  sigma_entry REAL,
  hit_5d INTEGER,
  significant_hit_5d INTEGER,
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (run_date, currency, timeframe, weighted)
);

CREATE TABLE IF NOT EXISTS fx_consensus_snapshot (
  run_date TEXT NOT NULL,
  currency TEXT NOT NULL,
  weighted INTEGER NOT NULL,
  score REAL NOT NULL,
  confidence REAL NOT NULL,
  agreement REAL NOT NULL,
  tilt REAL NOT NULL,
  n_eff REAL NOT NULL DEFAULT 0,
  n_brokers INTEGER NOT NULL DEFAULT 0,
  n_views INTEGER NOT NULL DEFAULT 0,
  bullish_pct REAL NOT NULL DEFAULT 0,
  bearish_pct REAL NOT NULL DEFAULT 0,
  neutral_pct REAL NOT NULL DEFAULT 0,
  watch_pct REAL NOT NULL DEFAULT 0,
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  timeframe TEXT NOT NULL DEFAULT 'unspecified',
  horizon_weeks INTEGER,
  PRIMARY KEY (run_date, currency, timeframe, weighted)
);

CREATE TABLE IF NOT EXISTS fx_daily_digest (
  run_date TEXT NOT NULL,
  summary TEXT,
  key_themes TEXT DEFAULT '[]' CHECK (key_themes IS NULL OR json_valid(key_themes)),
  doc_count INTEGER DEFAULT 0,
  broker_count INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (run_date)
);

-- ported from pg_dump table CHECK: (outcome = ANY (ARRAY['written'::text, 'failed'::text, 'skipped'::text, 'reused'::text]))
CREATE TABLE IF NOT EXISTS fx_digest_publish_attempts (
  id INTEGER NOT NULL,
  run_date TEXT NOT NULL,
  attempted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  outcome TEXT NOT NULL,
  row_written INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id),
  -- ported from the pg_dump CHECK comment above
  CHECK ((outcome IN ('written', 'failed', 'skipped', 'reused')))
);

-- ported from pg_dump table CHECK: (impact = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text]))
CREATE TABLE IF NOT EXISTS fx_economic_calendar (
  id INTEGER NOT NULL,
  event_date TEXT NOT NULL,
  event_time TEXT,
  country TEXT NOT NULL,
  event_name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'other',
  impact TEXT NOT NULL DEFAULT 'medium',
  actual TEXT,
  forecast TEXT,
  prior TEXT,
  source TEXT NOT NULL DEFAULT 'trading_economics',
  external_id TEXT NOT NULL,
  scraped_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  event_datetime_utc TEXT,
  UNIQUE (external_id),
  PRIMARY KEY (id),
  -- ported from the pg_dump CHECK comment above
  CHECK ((impact IN ('high', 'medium', 'low')))
);

CREATE TABLE IF NOT EXISTS fx_events_snapshot (
  run_date TEXT NOT NULL,
  event_key TEXT NOT NULL,
  event_name TEXT NOT NULL DEFAULT '',
  event_date TEXT,
  calendar_external_id TEXT NOT NULL DEFAULT '',
  release_at TEXT,
  category TEXT NOT NULL DEFAULT 'other',
  currencies TEXT NOT NULL DEFAULT '[]' CHECK (currencies IS NULL OR json_valid(currencies)),
  mentions INTEGER NOT NULL DEFAULT 0,
  brokers TEXT NOT NULL DEFAULT '[]' CHECK (brokers IS NULL OR json_valid(brokers)),
  citations TEXT NOT NULL DEFAULT '[]' CHECK (citations IS NULL OR json_valid(citations)),
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (run_date, event_key)
);

CREATE TABLE IF NOT EXISTS fx_hub_grants (
  email TEXT NOT NULL,
  granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  note TEXT,
  PRIMARY KEY (email)
);

-- ported from pg_dump table CHECK: ((closed_by IS NULL) OR (closed_by = ANY (ARRAY['target'::text, 'stop'::text, 'both'::text, 'drop'::text, 'successor'::text])))
-- ported from pg_dump table CHECK: ((grade_basis IS NULL) OR (grade_basis = ANY (ARRAY['measured'::text, 'directional'::text])))
-- ported from pg_dump table CHECK: (horizon_days = ANY (ARRAY[0, 1, 5]))
-- ported from pg_dump table CHECK: ((outcome IS NULL) OR (outcome = ANY (ARRAY['right'::text, 'wrong'::text])))
CREATE TABLE IF NOT EXISTS fx_idea_eval (
  run_date TEXT NOT NULL,
  rank INTEGER NOT NULL,
  horizon_days INTEGER NOT NULL,
  pair TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'carried',
  entry_date TEXT,
  exit_date TEXT,
  entry_fix REAL,
  exit_fix REAL,
  ret REAL,
  sigma_entry REAL,
  hit INTEGER,
  significant_hit INTEGER,
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  hold_return REAL,
  directional_win INTEGER,
  n_sessions INTEGER NOT NULL DEFAULT 0,
  bias_verdict TEXT,
  max_favorable REAL,
  max_adverse REAL,
  decisive_session TEXT,
  entry_fill_session TEXT,
  stop_price REAL,
  target_prices TEXT,
  level_outcome TEXT,
  verdict_reason TEXT NOT NULL DEFAULT '',
  outcome TEXT,
  grade_basis TEXT,
  closed_by TEXT,
  idea_id TEXT,
  timeframe TEXT,
  PRIMARY KEY (run_date, rank, horizon_days),
  -- ported from the pg_dump CHECK comment above
  CHECK (((closed_by IS NULL) OR (closed_by IN ('target', 'stop', 'both', 'drop', 'successor'))))
  -- ported from the pg_dump CHECK comment above
  CHECK (((grade_basis IS NULL) OR (grade_basis IN ('measured', 'directional'))))
  -- ported from the pg_dump CHECK comment above
  CHECK ((horizon_days IN (0, 1, 5)))
  -- ported from the pg_dump CHECK comment above
  CHECK (((outcome IS NULL) OR (outcome IN ('right', 'wrong'))))
);

CREATE TABLE IF NOT EXISTS fx_macro_history (
  series_id TEXT NOT NULL,
  obs_date TEXT NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY (series_id, obs_date)
);

-- ported from pg_dump table CHECK: (frequency = ANY (ARRAY['M'::text, 'Q'::text, 'Y'::text]))
CREATE TABLE IF NOT EXISTS fx_macro_snapshot (
  country TEXT NOT NULL,
  indicator TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  last_value REAL,
  previous_value REAL,
  highest_value REAL,
  lowest_value REAL,
  unit TEXT,
  frequency TEXT NOT NULL DEFAULT 'M',
  higher_is_better INTEGER,
  last_obs_date TEXT,
  previous_obs_date TEXT,
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (country, indicator),
  -- ported from the pg_dump CHECK comment above
  CHECK ((frequency IN ('M', 'Q', 'Y')))
);

CREATE TABLE IF NOT EXISTS fx_market_snapshots (
  id TEXT NOT NULL DEFAULT (lower(hex(randomblob(4)))||'-'||lower(hex(randomblob(2)))||'-4'||substr(lower(hex(randomblob(2))),2)||'-'||substr('89ab',1+(abs(random())%4),1)||substr(lower(hex(randomblob(2))),2)||'-'||lower(hex(randomblob(6)))),
  source_slug TEXT NOT NULL,
  instrument TEXT NOT NULL DEFAULT '',
  captured_at TEXT NOT NULL,
  pmt_as_of TEXT,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (id),
  UNIQUE (source_slug, instrument, captured_at)
);

CREATE TABLE IF NOT EXISTS fx_position_book (
  id INTEGER NOT NULL,
  pair TEXT NOT NULL,
  close_price REAL NOT NULL,
  levels TEXT NOT NULL DEFAULT '[]' CHECK (levels IS NULL OR json_valid(levels)),
  source_slug TEXT NOT NULL DEFAULT 'position-book',
  captured_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  avg_long REAL,
  avg_short REAL,
  UNIQUE (pair, captured_at),
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS fx_relevance_ledger (
  id INTEGER NOT NULL,
  run_date TEXT NOT NULL,
  source_file TEXT NOT NULL,
  view_index INTEGER NOT NULL,
  broker_name TEXT NOT NULL DEFAULT '',
  currency TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL DEFAULT '',
  conviction TEXT NOT NULL DEFAULT '',
  report_date TEXT,
  calendar_external_id TEXT NOT NULL DEFAULT '',
  w_time REAL NOT NULL,
  w_event REAL NOT NULL,
  w_review REAL NOT NULL,
  relevance REAL NOT NULL,
  classification TEXT NOT NULL DEFAULT 'active',
  reason TEXT NOT NULL DEFAULT '',
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (id),
  UNIQUE (run_date, source_file, view_index)
);

CREATE TABLE IF NOT EXISTS fx_relevance_llm_cache (
  cache_key TEXT NOT NULL,
  currency TEXT NOT NULL,
  reviews TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (cache_key)
);

CREATE TABLE IF NOT EXISTS fx_research_history (
  id INTEGER NOT NULL,
  file_id TEXT NOT NULL DEFAULT '',
  run_date TEXT NOT NULL,
  broker_name TEXT NOT NULL,
  analyst_names TEXT NOT NULL DEFAULT '[]' CHECK (analyst_names IS NULL OR json_valid(analyst_names)),
  report_date TEXT,
  source_file TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  trader_relevance TEXT NOT NULL DEFAULT '',
  trader_relevance_note TEXT NOT NULL DEFAULT '',
  central_thesis TEXT NOT NULL DEFAULT '',
  brief_markdown TEXT DEFAULT '',
  currency_views TEXT DEFAULT '[]' CHECK (currency_views IS NULL OR json_valid(currency_views)),
  macro_themes TEXT DEFAULT '[]' CHECK (macro_themes IS NULL OR json_valid(macro_themes)),
  risk_events TEXT DEFAULT '[]' CHECK (risk_events IS NULL OR json_valid(risk_events)),
  positioning_signals TEXT DEFAULT '[]' CHECK (positioning_signals IS NULL OR json_valid(positioning_signals)),
  vault_path TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  document_title TEXT,
  pdf_url TEXT,
  summary TEXT DEFAULT '',
  summary_points TEXT DEFAULT '[]' CHECK (summary_points IS NULL OR json_valid(summary_points)),
  source_spans TEXT DEFAULT '[]' CHECK (source_spans IS NULL OR json_valid(source_spans)),
  extraction_method TEXT NOT NULL DEFAULT 'single',
  chunk_count INTEGER NOT NULL DEFAULT 0,
  quality TEXT,
  release_date TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (id),
  UNIQUE (file_id, run_date)
);

CREATE TABLE IF NOT EXISTS fx_retail_book_stats (
  id INTEGER NOT NULL,
  pair TEXT NOT NULL,
  as_of TEXT NOT NULL,
  long_positions INTEGER NOT NULL DEFAULT 0,
  short_positions INTEGER NOT NULL DEFAULT 0,
  total_positions INTEGER NOT NULL DEFAULT 0,
  avg_long_price REAL NOT NULL DEFAULT 0,
  avg_short_price REAL NOT NULL DEFAULT 0,
  long_volume_lots REAL NOT NULL DEFAULT 0,
  short_volume_lots REAL NOT NULL DEFAULT 0,
  source_slug TEXT NOT NULL DEFAULT 'dmx-statistics-table',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (pair, as_of, source_slug),
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS fx_retail_positioning (
  id INTEGER NOT NULL,
  pair TEXT NOT NULL,
  as_of TEXT NOT NULL,
  long_pct REAL NOT NULL,
  short_pct REAL NOT NULL,
  source_slug TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (pair, as_of, source_slug),
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS fx_seasonality_forecast (
  id INTEGER NOT NULL,
  pair TEXT NOT NULL,
  horizon INTEGER NOT NULL,
  forecast_date TEXT NOT NULL,
  probability REAL NOT NULL,
  bull REAL NOT NULL,
  bear REAL NOT NULL,
  base REAL NOT NULL,
  trend TEXT NOT NULL DEFAULT '',
  meta_start TEXT,
  meta_end TEXT,
  source_slug TEXT NOT NULL DEFAULT 'seasonality-forecast',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (pair, horizon, forecast_date),
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS fx_smart_bias (
  id INTEGER NOT NULL,
  currency TEXT NOT NULL,
  week_first_date TEXT NOT NULL,
  overall_sentiment TEXT NOT NULL DEFAULT '',
  fundamental_overview TEXT NOT NULL DEFAULT '',
  bank_overview TEXT NOT NULL DEFAULT '',
  indicators TEXT NOT NULL DEFAULT '[]' CHECK (indicators IS NULL OR json_valid(indicators)),
  bank_sentiment TEXT NOT NULL DEFAULT '[]' CHECK (bank_sentiment IS NULL OR json_valid(bank_sentiment)),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (currency, week_first_date),
  PRIMARY KEY (id)
);

-- ported from pg_dump table CHECK: ((timeframe IS NULL) OR (timeframe = ANY (ARRAY['short'::text, 'medium'::text, 'long'::text])))
CREATE TABLE IF NOT EXISTS fx_trade_ideas_snapshot (
  run_date TEXT NOT NULL,
  rank INTEGER NOT NULL,
  pair TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  thesis TEXT NOT NULL DEFAULT '',
  catalyst TEXT NOT NULL DEFAULT '',
  levels TEXT NOT NULL DEFAULT '[]' CHECK (levels IS NULL OR json_valid(levels)),
  citations TEXT NOT NULL DEFAULT '[]' CHECK (citations IS NULL OR json_valid(citations)),
  as_of TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  conviction_score INTEGER,
  consensus_alignment TEXT NOT NULL DEFAULT '',
  rationale TEXT NOT NULL DEFAULT '',
  trade_levels TEXT NOT NULL DEFAULT '[]' CHECK (trade_levels IS NULL OR json_valid(trade_levels)),
  evidence TEXT NOT NULL DEFAULT '[]' CHECK (evidence IS NULL OR json_valid(evidence)),
  authored_by TEXT NOT NULL DEFAULT '',
  idea_id TEXT,
  parent_idea_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  timeframe TEXT,
  PRIMARY KEY (run_date, rank),
  -- ported from the pg_dump CHECK comment above
  CHECK (((timeframe IS NULL) OR (timeframe IN ('short', 'medium', 'long'))))
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (filename)
);

CREATE INDEX IF NOT EXISTS idx_fx_events_snapshot_run_date ON fx_events_snapshot (run_date);
CREATE INDEX IF NOT EXISTS idx_fx_events_snapshot_event_date ON fx_events_snapshot (event_date);
CREATE UNIQUE INDEX IF NOT EXISTS fx_economic_calendar_external_id_key ON fx_economic_calendar (external_id);
CREATE INDEX IF NOT EXISTS idx_fx_economic_calendar_event_date ON fx_economic_calendar (event_date);
CREATE INDEX IF NOT EXISTS idx_fx_economic_calendar_country_date ON fx_economic_calendar (country, event_date);
CREATE UNIQUE INDEX IF NOT EXISTS fx_retail_positioning_pair_as_of_source_slug_key ON fx_retail_positioning (pair, as_of, source_slug);
CREATE INDEX IF NOT EXISTS fx_retail_positioning_pair_asof_idx ON fx_retail_positioning (pair, as_of DESC);
CREATE UNIQUE INDEX IF NOT EXISTS fx_smart_bias_currency_week_first_date_key ON fx_smart_bias (currency, week_first_date);
CREATE INDEX IF NOT EXISTS fx_smart_bias_week_idx ON fx_smart_bias (week_first_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS fx_relevance_ledger_uq ON fx_relevance_ledger (run_date, source_file, view_index);
CREATE INDEX IF NOT EXISTS fx_relevance_ledger_run_date ON fx_relevance_ledger (run_date);
CREATE INDEX IF NOT EXISTS fx_relevance_ledger_source_file ON fx_relevance_ledger (source_file, view_index);
CREATE UNIQUE INDEX IF NOT EXISTS fx_bank_trades_bank_trade_id_key ON fx_bank_trades (bank_trade_id);
CREATE INDEX IF NOT EXISTS fx_bank_trades_pair_date_idx ON fx_bank_trades (pair, trade_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS fx_calendar_pmt_event_date_currency_normalized_name_key ON fx_calendar_pmt (event_date, currency, normalized_name);
CREATE INDEX IF NOT EXISTS fx_calendar_pmt_date_currency_idx ON fx_calendar_pmt (event_date, currency);
CREATE UNIQUE INDEX IF NOT EXISTS fx_position_book_pair_captured_at_key ON fx_position_book (pair, captured_at);
CREATE INDEX IF NOT EXISTS fx_position_book_pair_captured_idx ON fx_position_book (pair, captured_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS fx_seasonality_forecast_pair_horizon_forecast_date_key ON fx_seasonality_forecast (pair, horizon, forecast_date);
CREATE INDEX IF NOT EXISTS fx_seasonality_forecast_pair_horizon_idx ON fx_seasonality_forecast (pair, horizon, forecast_date DESC);
CREATE INDEX IF NOT EXISTS idx_fx_trade_ideas_snapshot_run_date ON fx_trade_ideas_snapshot (run_date);
CREATE INDEX IF NOT EXISTS fx_trade_ideas_snapshot_idea_id_idx ON fx_trade_ideas_snapshot (idea_id);
CREATE INDEX IF NOT EXISTS idx_fx_confluence_snapshot_run_date ON fx_confluence_snapshot (run_date);
CREATE INDEX IF NOT EXISTS idx_fx_consensus_snapshot_run_date ON fx_consensus_snapshot (run_date);
CREATE UNIQUE INDEX IF NOT EXISTS fx_market_snapshots_source_slug_instrument_captured_at_key ON fx_market_snapshots (source_slug, instrument, captured_at);
CREATE INDEX IF NOT EXISTS fx_market_snapshots_slug_captured_idx ON fx_market_snapshots (source_slug, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_fx_bookkeeper_verdicts_run_date ON fx_bookkeeper_verdicts (run_date);
CREATE INDEX IF NOT EXISTS idx_fx_idea_eval_run_date ON fx_idea_eval (run_date);
CREATE INDEX IF NOT EXISTS idx_fx_idea_eval_status ON fx_idea_eval (status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fx_idea_eval_lifecycle_idea ON fx_idea_eval (run_date, rank) WHERE (horizon_days = 0);
CREATE INDEX IF NOT EXISTS fx_idea_eval_idea_id_idx ON fx_idea_eval (idea_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fx_research_history_file_run ON fx_research_history (file_id, run_date);
CREATE INDEX IF NOT EXISTS idx_fx_rh_v2_run_date ON fx_research_history (run_date DESC);
CREATE INDEX IF NOT EXISTS idx_fx_rh_v2_broker ON fx_research_history (broker_name);
CREATE INDEX IF NOT EXISTS idx_fx_rh_v2_relevance ON fx_research_history (trader_relevance);
-- NON-PORTABLE INDEX (resolved decision, was a silent TODO on review).
--   pg:  CREATE INDEX idx_fx_rh_v2_currency_views ON fx_research_history USING gin (currency_views);
--   Why it cannot be ported: SQLite has no GIN and cannot build an index over the
--   *elements* of a JSON array. `json_each()` is a table-valued function, so no
--   B-tree index over it is ever used by the planner.
--   Access pattern being served: "research rows whose currency_views array CONTAINS $1".
--   Equivalent query shape (no index required - full scan + element match):
--     SELECT h.* FROM fx_research_history h
--      WHERE EXISTS (SELECT 1 FROM json_each(h.currency_views) j WHERE j.value = ?);
--   Decision: NOT created here on purpose. Three indexable options, each a data change
--   and therefore gated on ticket 0 (Chris's snapshot) before it may be built:
--     a) normalised side table fx_research_history_currency_views(run_date, rank, currency)
--        with a btree on (currency, run_date)  <-- preferred, planner-visible;
--     b) a stored TEXT column holding the array's comma-joined currencies, indexed;
--     c) FTS5 over a flattened copy  <-- changes recall semantics, not just speed.
--   Until then the read path above is the supported way to answer the question.
--   Tracked on DIG-2890; this note is the resolution, not a dropped index.
CREATE INDEX IF NOT EXISTS idx_fx_consensus_eval_run_date ON fx_consensus_eval (run_date);
CREATE INDEX IF NOT EXISTS idx_fx_consensus_eval_accuracy ON fx_consensus_eval (accuracy_status);
CREATE UNIQUE INDEX IF NOT EXISTS fx_retail_book_stats_pair_as_of_source_slug_key ON fx_retail_book_stats (pair, as_of, source_slug);
CREATE INDEX IF NOT EXISTS fx_retail_book_stats_pair_asof_idx ON fx_retail_book_stats (pair, as_of DESC);
CREATE UNIQUE INDEX IF NOT EXISTS fx_archive_objects_r2_key_key ON fx_archive_objects (r2_key);
CREATE INDEX IF NOT EXISTS fx_archive_objects_source_idx ON fx_archive_objects (source_table, source_key_text);
CREATE INDEX IF NOT EXISTS fx_macro_history_series_date_idx ON fx_macro_history (series_id, obs_date DESC);
CREATE INDEX IF NOT EXISTS fx_digest_publish_attempts_run_idx ON fx_digest_publish_attempts (run_date, attempted_at DESC);

-- Triggers to port: null
-- Functions: ["fx_hub_has_access"]
-- RLS policies: 21 (-> Worker authz)
-- Views: null