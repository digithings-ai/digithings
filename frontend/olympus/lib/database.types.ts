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
      theses: {
        Row: {
          id: string;
          date: string;
          thesis_id: string;
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
        // candidate_rank (many-to-many). Written reliably by Hermes H3
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
        // Single-benchmark active-return decomposition per (date, ticker) (migration 040).
        Row: {
          id: string;
          date: string;
          ticker: string;
          sector_bucket: string | null;
          weight_pct: number | null;
          position_return_pct: number | null;
          benchmark_return_pct: number | null;
          contribution_pct: number | null;       // weight × position return
          selection_effect_pct: number | null;   // weight × (position − benchmark)
          allocation_effect_pct: number | null;  // cash-drag effect (CASH row)
          total_attribution_pct: number | null;  // selection + allocation; sums to active return
          metrics_as_of: string | null;
          created_at: string | null;
        };
        Insert: Omit<Database['public']['Tables']['position_attribution']['Row'], 'id' | 'created_at'> & { id?: string; created_at?: string };
        Update: Partial<Database['public']['Tables']['position_attribution']['Insert']>;
      };
      atlas_run_diagnostics: {
        Row: {
          run_id: string;
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
      // timing ONLY — spend telemetry (cost, tokens, error_summary, breakdown) is excluded.
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
