/**
 * Supabase database types — handwritten from schema migrations.
 * Regenerate via: npx supabase gen types typescript --project-id rwagjbkvxkdwqmouagad --schema public
 * when Supabase CLI access token is available.
 */

export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export interface Database {
  public: {
    Tables: {
      daily_snapshots: {
        Row: {
          id: string;
          date: string;           // date (ISO string)
          run_type: 'baseline' | 'delta';
          baseline_date: string | null;
          snapshot?: Json | null;        // jsonb — full digest snapshot (single source of truth)
          digest_markdown?: string | null; // rendered digest for Library
          created_at: string | null;
        };
        Insert: Omit<Database['public']['Tables']['daily_snapshots']['Row'], 'id' | 'created_at'> & { id?: string; created_at?: string };
        Update: Partial<Database['public']['Tables']['daily_snapshots']['Insert']>;
      };
      positions: {
        Row: {
          id: string;
          /** T0 house/overlay book (migration 097). Dashboard reads filter house via houseBook(). */
          workspace_id?: string;
          date: string;
          ticker: string;
          name: string | null;
          category: string | null;
          weight_pct: number;
          thesis_id: string | null;
          rationale: string | null;
          current_price: number | null;
          entry_price: number | null;
          entry_date: string | null;
          pm_notes: string | null;
          unrealized_pnl_pct?: number | null;
          day_change_pct?: number | null;
          since_entry_return_pct?: number | null;
          metrics_as_of?: string | null;
          // Advisory per-position risk fields (migration 039, Pillar 2E). Optional: only
          // populated when OLYMPUS_POSITION_RISK_FIELDS is on; NULL on legacy/ungraded rows.
          stop_loss_pct?: number | null;
          target_pct_gain?: number | null;
          horizon_days?: number | null;
          conviction?: number | null;
          sector_bucket?: string | null;
        };
        Insert: Omit<Database['public']['Tables']['positions']['Row'], 'id'> & { id?: string };
        Update: Partial<Database['public']['Tables']['positions']['Insert']>;
      };
      instruments: {
        Row: {
          ticker: string;
          official_name: string;
          instrument_type: string | null;
          asset_class: string | null;
          category: string | null;
          sector: string | null;
          industry: string | null;
          exchange: string | null;
          currency: string | null;
          country: string | null;
          provider: string;
          provider_metadata: Json;
          source_updated_at: string;
          created_at: string;
          updated_at: string;
        };
        Insert: Omit<
          Database['public']['Tables']['instruments']['Row'],
          'created_at' | 'updated_at'
        > & { created_at?: string; updated_at?: string };
        Update: Partial<Database['public']['Tables']['instruments']['Insert']>;
      };
      theses: {
        Row: {
          id: string;
          date: string;
          thesis_id: string;
          topic_key?: string | null;
          name: string;
          vehicle: string | null;
          invalidation: string | null;
          status: string | null;
          notes: string | null;
          created_at?: string | null;
          updated_at?: string | null;
          // Widened (#redesign F1): live columns the old mapping dropped.
          confidence?: number | null;            // numeric 0.0–1.0
          horizon?: string | null;               // e.g. "3-6mo"
          thesis_kind?: string | null;           // 'market' | 'vehicle'
          validation_criteria?: Json | null;     // jsonb string[]
          invalidation_criteria?: Json | null;   // jsonb string[]
          linked_market_thesis_id?: string | null;
        };
        Insert: Omit<Database['public']['Tables']['theses']['Row'], 'id'> & { id?: string };
        Update: Partial<Database['public']['Tables']['theses']['Insert']>;
      };
      position_events: {
        Row: {
          id: string;
          /** T0 house/overlay book (migration 097). Dashboard reads filter house via houseBook(). */
          workspace_id?: string;
          date: string;
          ticker: string;
          event: 'OPEN' | 'EXIT' | 'TRIM' | 'ADD' | 'HOLD';
          weight_pct: number | null;
          prev_weight_pct: number | null;
          cumulative_return_since_event_pct?: number | null;
          price: number | null;
          thesis_id: string | null;
          reason: string | null;
          created_at: string | null;
          /** Compatibility label (#2422): legacy reconstruction vs ledger projection. */
          book_source?: 'legacy' | 'authoritative';
        };
        Insert: Omit<Database['public']['Tables']['position_events']['Row'], 'id' | 'created_at'> & { id?: string; created_at?: string };
        Update: Partial<Database['public']['Tables']['position_events']['Insert']>;
      };
      documents: {
        Row: {
          id: string;
          date: string;
          title: string;
          doc_type: string | null;
          phase: number | null;
          category: string | null;
          segment: string | null;
          sector: string | null;
          run_type: string | null;
          /** Logical key within the run date (e.g. digest, sectors/energy); not a repo path. */
          document_key: string;
          content: string | null;
          /** Digest snapshot JSON when document_key is digest (optional elsewhere). */
          payload: Json | null;
        };
        Insert: Omit<Database['public']['Tables']['documents']['Row'], 'id'> & { id?: string };
        Update: Partial<Database['public']['Tables']['documents']['Insert']>;
      };
      nav_history: {
        Row: {
          /** T0 house/overlay book (migration 097). */
          workspace_id?: string;
          date: string;
          nav: number;
          cash_pct: number | null;
          invested_pct: number | null;
          updated_at?: string | null;
        };
        Insert: Database['public']['Tables']['nav_history']['Row'];
        Update: Partial<Database['public']['Tables']['nav_history']['Row']>;
      };
      portfolio_metrics: {
        Row: {
          id: string;
          /** T0 house/overlay book (migration 097). Dashboard reads filter house via houseBook(). */
          workspace_id?: string;
          date: string;
          pnl_pct: number | null;
          sharpe: number | null;
          volatility: number | null;
          max_drawdown: number | null;
          alpha: number | null;
          net_return_pct: number | null;
          benchmark_return_pct: number | null;
          relative_return_pct: number | null;
          benchmark_ticker: string;
          invested_pct: number | null;
          generated_at: string | null;
          computed_from?: string | null;
          as_of_date?: string | null;
        };
        Insert: Omit<Database['public']['Tables']['portfolio_metrics']['Row'], 'id' | 'generated_at'> & { id?: string; generated_at?: string };
        Update: Partial<Database['public']['Tables']['portfolio_metrics']['Insert']>;
      };
      price_history: {
        Row: {
          date: string;
          ticker: string;
          open: number | null;
          high: number | null;
          low: number | null;
          close: number;
          volume: number | null;
        };
        Insert: Database['public']['Tables']['price_history']['Row'];
        Update: Partial<Database['public']['Tables']['price_history']['Row']>;
      };
      price_technicals: {
        Row: {
          date: string;
          ticker: string;
          sma_20: number | null; sma_50: number | null; sma_200: number | null;
          ema_12: number | null; ema_26: number | null; ema_50: number | null;
          pct_vs_sma20: number | null; pct_vs_sma50: number | null; pct_vs_sma200: number | null;
          adx_14: number | null; dmi_plus: number | null; dmi_minus: number | null;
          rsi_7: number | null; rsi_14: number | null; rsi_21: number | null;
          macd: number | null; macd_signal: number | null; macd_hist: number | null;
          roc_5: number | null; roc_10: number | null; roc_21: number | null;
          atr_14: number | null; atr_pct: number | null;
          bb_upper: number | null; bb_lower: number | null;
          bb_pct_b: number | null; bb_bandwidth: number | null;
          hist_vol_21: number | null;
          stoch_k: number | null; stoch_d: number | null;
          zscore_50: number | null; zscore_200: number | null;
        };
        Insert: Database['public']['Tables']['price_technicals']['Row'];
        Update: Partial<Database['public']['Tables']['price_technicals']['Row']>;
      };
      prices_live: {
        // Latest intraday quote per ticker (migration 063) — ONE row per symbol, upserted
        // every ~60s during extended US hours by the `prices-live` edge function. This is
        // the DISPLAY lane (#1833) and it is READ-ONLY from the browser: RLS is enabled
        // with exactly one `FOR SELECT` policy, and "the absent write policy IS the
        // security control" (063) — `service_role` is the only writer. `Insert`/`Update`
        // are declared for shape parity with the other tables here; no client code may
        // use them, and a live price must never be written back into
        // `positions.current_price`, which is the nightly CLOSE the performance batch
        // reads (that is the invariant #1833 exists to protect).
        //
        // Coverage is NOT guaranteed per held ticker: the publisher caps at 25 symbols
        // (a curated MAJORS list plus portfolio tickers), so a holding may be absent —
        // consumers fall back to the close. See lib/live-valuation.ts.
        Row: {
          ticker: string;
          /** Finnhub `c`. NOT NULL, but may legitimately be 0 for a halted symbol. */
          price: number;
          /** Finnhub `d` — absolute change vs prior close. Carried, unused by the UI. */
          change: number | null;
          /** Finnhub `dp` — percent POINTS vs prior close: 1.24 means +1.24%, not 0.0124. */
          change_pct: number | null;
          /** EXCHANGE tick time — the freshness a staleness check must read. */
          quoted_at: string;
          /** OUR write clock; advances even when the quote has not moved. Not "as of". */
          updated_at: string;
        };
        Insert: Omit<Database['public']['Tables']['prices_live']['Row'], 'updated_at'> & { updated_at?: string };
        Update: Partial<Database['public']['Tables']['prices_live']['Insert']>;
      };
      macro_series_observations: {
        Row: {
          source: string;
          series_id: string;
          obs_date: string;
          value: number | null;
          unit: string | null;
          meta: Json | null;
          ingested_at: string;
        };
        Insert: Omit<Database['public']['Tables']['macro_series_observations']['Row'], 'ingested_at'> & { ingested_at?: string };
        Update: Partial<Database['public']['Tables']['macro_series_observations']['Insert']>;
      };
      trading_calendar: {
        Row: {
          date: string;
          venue: string;       // 'NYSE' | 'NASDAQ' | 'CRYPTO' | 'FX'
          is_trading_day: boolean;
          reason: string | null; // 'weekend' | 'holiday:<name>' | 'early_close' | null
          created_at: string;
        };
        Insert: Omit<Database['public']['Tables']['trading_calendar']['Row'], 'created_at'> & { created_at?: string };
        Update: Partial<Database['public']['Tables']['trading_calendar']['Insert']>;
      };
      decision_log: {
        // Per-ticker analyst decisions, resolved against realized prices (migration 026).
        // Feeds the Observability Decision Scorecard: conviction vs realized alpha.
        Row: {
          id: string;
          run_id: string;
          run_date: string;
          ticker: string;
          stance: string;                 // 'buy' | 'hold' | 'sell' | 'trim' | ...
          conviction: number | null;      // 0..5 effective conviction
          thesis: string | null;
          benchmark: string;              // default 'SPY'
          holding_days: number;
          status: 'pending' | 'resolved';
          actual_return: number | null;   // ticker total return over the window
          alpha: number | null;           // actual_return − benchmark_return (NULL while pending)
          reflection: string | null;
          resolved_at: string | null;
          created_at: string | null;
        };
        Insert: Omit<Database['public']['Tables']['decision_log']['Row'], 'id' | 'created_at'> & { id?: string; created_at?: string };
        Update: Partial<Database['public']['Tables']['decision_log']['Insert']>;
      };
      thesis_vehicles: {
        // Analyst vehicle-selection map: ticker → MARKET thesis_id, with rationale +
        // candidate_rank (many-to-many). Written reliably by portfolio H3
        // (persist_thesis_vehicle_map). This is the RELIABLE ticker→market-thesis join
        // used by the Theses story spine (#1562) — `theses.linked_market_thesis_id` is
        // self-referential/dead. NB: `thesis_id` is co-generated per `date` with the
        // `theses` table (the slug churns daily), so the join is reliable within a date.
        Row: {
          date: string;
          thesis_id: string;          // MARKET thesis id (matches theses.thesis_id on the same date)
          ticker: string;
          rationale: string | null;
          exclusion_reasons: Json | null;
          candidate_rank: number | null;
          user_mandate_notes: Json | null;
          source_exploration_key: string | null;
          created_at: string;
        };
        Insert: Omit<Database['public']['Tables']['thesis_vehicles']['Row'], 'created_at'> & { created_at?: string };
        Update: Partial<Database['public']['Tables']['thesis_vehicles']['Insert']>;
      };
      position_attribution: {
        // Compatibility view over current_book_lookback (#2598 / migration 073).
        // Trailing-window diagnostic — NOT realized daily contribution.
        Row: {
          id: string;
          date: string;
          ticker: string;
          sector_bucket: string | null;
          weight_pct: number | null;
          position_return_pct: number | null;
          benchmark_return_pct: number | null;
          contribution_pct: number | null;       // weight × lookback return
          selection_effect_pct: number | null;   // weight × (position − benchmark)
          allocation_effect_pct: number | null;  // cash-drag effect (CASH row)
          total_attribution_pct: number | null;  // selection + allocation; sums to active return
          metrics_as_of: string | null;
          created_at: string | null;
          window_start_date?: string | null;
          window_end_date?: string | null;
          lookback_days?: number | null;
          contract?: string | null;              // always 'current_book_lookback'
        };
        Insert: Omit<Database['public']['Tables']['position_attribution']['Row'], 'id' | 'created_at'> & { id?: string; created_at?: string };
        Update: Partial<Database['public']['Tables']['position_attribution']['Insert']>;
      };
      current_book_lookback: {
        // Canonical 21-day current-book lookback diagnostic (#2598). Same columns as
        // the position_attribution compatibility view.
        Row: Database['public']['Tables']['position_attribution']['Row'];
        Insert: Database['public']['Tables']['position_attribution']['Insert'];
        Update: Database['public']['Tables']['position_attribution']['Update'];
      };
      atlas_run_diagnostics: {
        Row: {
          run_id: string;
          // Outer-retry attempt within one workflow run, 1-based; part of the primary key with
          // run_id since migration 065 (#1762). `0` means the row predates per-attempt keying
          // and may be a collapsed multi-attempt row — never read 0 as "first attempt".
          attempt: number;
          run_type: string | null;
          run_date: string | null;
          model: string | null;
          status: string | null;
          started_at: string | null;
          finished_at: string | null;
          duration_s: number | null;
          llm_calls: number | null;
          prompt_tokens: number | null;
          completion_tokens: number | null;
          total_tokens: number | null;
          search_calls: number | null;
          sources_used: number | null;
          grounding_ok: number | null;
          grounding_failed: number | null;
          est_cost_usd: number | null;
          segments_total: number | null;
          segments_ok: number | null;
          segments_carried: number | null;
          segments_failed: number | null;
          error_summary: string | null;
          breakdown: Json | null;
          created_at: string | null;
        };
        Insert: Database['public']['Tables']['atlas_run_diagnostics']['Row'];
        Update: Partial<Database['public']['Tables']['atlas_run_diagnostics']['Row']>;
      };
      analyst_coverage: {
        // Pointer/index row per (date, ticker): which market thesis_ids the coverage
        // touches and the live doc key to render (`current_recommendation_key`, e.g.
        // 'analyst/XLE'). `last_updated` tracks the POINTER refresh, NOT the underlying
        // analyst doc content — the frozen 06-26 analyst docs still get a fresh
        // `last_updated` on every run (#1562). Never derive "last analyzed" from this
        // column; use the `documents`/`decision_log` row dates instead.
        Row: {
          date: string;
          ticker: string;
          thesis_ids: Json | null;    // jsonb string[] of MARKET thesis ids; often []
          analyst_role: string | null;
          current_recommendation_key: string | null; // e.g. 'analyst/XLE'
          last_updated: string;
        };
        Insert: Database['public']['Tables']['analyst_coverage']['Row'];
        Update: Partial<Database['public']['Tables']['analyst_coverage']['Row']>;
      };
    };
    Views: {
      price_history_tickers: {
        Row: {
          ticker: string;
        };
      };
      // Curated, anon-readable run health (migration 041): status / segment counts / model /
      // timing / retry attempt ONLY — spend telemetry (cost, tokens, error_summary, breakdown)
      // is excluded. ONE ROW PER RETRY ATTEMPT since 065 (#1762): a date that took three
      // attempts has three rows, which is what groupRunEpisodes was built to read.
      atlas_run_health: {
        Row: {
          run_id: string;
          run_date: string | null;
          run_type: string | null;
          model: string | null;
          status: string | null;
          started_at: string | null;
          finished_at: string | null;
          duration_s: number | null;
          segments_total: number | null;
          segments_ok: number | null;
          segments_carried: number | null;
          segments_failed: number | null;
          created_at: string | null;
          // Last in the SELECT list, mirroring the view: CREATE OR REPLACE VIEW can only
          // append columns, so 065 could not slot `attempt` next to `run_id`.
          attempt: number;
        };
      };
      // Body-free Pipeline call trace (migration 066 + WP1 join keys in 086 / #2763).
      // The base table remains service-role-only; this view excludes token and cost
      // telemetry (067 is economics authority) as well as prompts, tool values/results,
      // document bodies, credentials, and reasoning. Soft-stamped call_id / attempt_id /
      // node_run_id enable Gate 3 reconciliation to dashboard_provider_*.
      olympus_run_event_trace: {
        Row: {
          run_id: string;
          attempt: number;
          run_date: string;
          run_type: string | null;
          sequence: number;
          event_kind: 'model_call' | 'search_call' | 'tool_call';
          phase: string | null;
          operation: string | null;
          document_key: string | null;
          name: string;
          status: 'ok' | 'error';
          duration_ms: number | null;
          retry_count: number;
          sources: number;
          input_summary: string;
          output_summary: string;
          created_at: string;
          call_id: string | null;
          attempt_id: string | null;
          node_run_id: string | null;
        };
      };
      // Curated accounting public surface (migration 074 / #2599). Prefer these over
      // raw nav_history for public/performance readers; rollback = LEGACY public_nav_history.
      public_accounting_nav_history: {
        Row: {
          date: string;
          nav: number;
          cash_pct: number | null;
          invested_pct: number | null;
          day_return_pct: number | null;
          /** finalized_accounting | legacy_nav_history — never unlabeled. */
          source: string;
          /** finalized_accounting | legacy_estimate */
          contract: string;
        };
      };
      public_finalized_nav: {
        Row: {
          date: string;
          nav: number;
          cash_pct: number | null;
          invested_pct: number | null;
          day_return_pct: number | null;
          source: string;
          contract: string;
        };
      };
      public_accounting_period_status: {
        Row: {
          date: string;
          status: string;
          quality_reasons: string[];
          opening_equity: number;
          closing_equity: number;
          day_return_pct: number | null;
          benchmark_symbol: string | null;
          benchmark_return_pct: number | null;
          contract: string;
        };
      };
      public_daily_realized_attribution: {
        Row: {
          date: string;
          ticker: string;
          contribution_pct: number | null;
          benchmark_return_pct: number | null;
          opening_equity: number;
          closing_equity: number;
          contract: string;
          period_status: string;
        };
      };
    };
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}

/** Helpers for table row types */
export type TableRow<T extends keyof Database['public']['Tables']> =
  Database['public']['Tables'][T]['Row'];

/** Helper for view row types */
export type ViewRow<T extends keyof Database['public']['Views']> =
  Database['public']['Views'][T]['Row'];
