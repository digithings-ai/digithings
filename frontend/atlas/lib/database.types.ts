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
          regime: Json;           // jsonb — RegimeJson at runtime
          market_data: Json;      // jsonb
          segment_biases: Json | null;
          actionable: string[] | null;
          risks: string[] | null;
          snapshot?: Json | null;        // jsonb — full digest snapshot (DB-first)
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
          contribution_pct?: number | null;
          metrics_as_of?: string | null;
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
          weight_change_pct?: number | null;
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
          cash_pct: number | null;
          total_invested: number | null;
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
          bb_upper: number | null; bb_middle: number | null; bb_lower: number | null;
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
    };
    Views: {
      price_history_tickers: {
        Row: {
          ticker: string;
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
