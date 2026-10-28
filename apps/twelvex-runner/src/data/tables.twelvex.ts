/** Generated from the twelve-x D1 schema draft (DIG-2890). Allowlist: only these tables/columns are reachable. */
import type { TableSpec } from "./types";

export const TWELVEX_TABLES: Record<string, TableSpec> = {
  "fx_archive_objects": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "source_table",
      "source_key",
      "source_key_text",
      "r2_key",
      "sha256",
      "size_bytes",
      "owner",
      "archived_at",
      "status"
    ]
  },
  "fx_bank_trades": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "bank_trade_id",
      "pair",
      "bank_name",
      "trade_date",
      "trade_entry",
      "trade_stop_loss",
      "trade_take_profit",
      "trade_status",
      "order_type",
      "direction",
      "source_slug",
      "created_at"
    ]
  },
  "fx_bookkeeper_verdicts": {
    "pk": [
      "run_date",
      "idea_run_date",
      "idea_rank"
    ],
    "columns": [
      "run_date",
      "axis",
      "idea_rank",
      "idea_run_date",
      "verdict",
      "verdict_reason",
      "bookkeeper_ok",
      "as_of",
      "idea_id",
      "timeframe"
    ]
  },
  "fx_calendar_pmt": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "event_date",
      "currency",
      "normalized_name",
      "event_name",
      "country",
      "impact",
      "event_time",
      "actual",
      "forecast",
      "prior",
      "pmt_event_id",
      "updated_on",
      "source_slug",
      "created_at"
    ]
  },
  "fx_confluence_snapshot": {
    "pk": [
      "run_date",
      "rank"
    ],
    "columns": [
      "run_date",
      "rank",
      "title",
      "currency",
      "direction",
      "score",
      "components",
      "brief_keys",
      "as_of"
    ]
  },
  "fx_consensus_eval": {
    "pk": [
      "run_date",
      "currency",
      "timeframe",
      "weighted"
    ],
    "columns": [
      "run_date",
      "currency",
      "timeframe",
      "weighted",
      "score",
      "tilt",
      "agreement",
      "n_brokers",
      "n_brokers_prev",
      "delta_score",
      "delta_tilt",
      "delta_agreement",
      "delta_score_pred",
      "clip_flag",
      "sign_flip",
      "abs_delta_score",
      "accuracy_status",
      "currency_ret_5d",
      "sigma_entry",
      "hit_5d",
      "significant_hit_5d",
      "as_of"
    ]
  },
  "fx_consensus_snapshot": {
    "pk": [
      "run_date",
      "currency",
      "timeframe",
      "weighted"
    ],
    "columns": [
      "run_date",
      "currency",
      "weighted",
      "score",
      "confidence",
      "agreement",
      "tilt",
      "n_eff",
      "n_brokers",
      "n_views",
      "bullish_pct",
      "bearish_pct",
      "neutral_pct",
      "watch_pct",
      "as_of",
      "timeframe",
      "horizon_weeks"
    ]
  },
  "fx_daily_digest": {
    "pk": [
      "run_date"
    ],
    "columns": [
      "run_date",
      "summary",
      "key_themes",
      "doc_count",
      "broker_count",
      "created_at"
    ]
  },
  "fx_digest_publish_attempts": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "run_date",
      "attempted_at",
      "outcome",
      "row_written",
      "error"
    ]
  },
  "fx_economic_calendar": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "event_date",
      "event_time",
      "country",
      "event_name",
      "category",
      "impact",
      "actual",
      "forecast",
      "prior",
      "source",
      "external_id",
      "scraped_at",
      "created_at",
      "updated_at",
      "event_datetime_utc"
    ]
  },
  "fx_events_snapshot": {
    "pk": [
      "run_date",
      "event_key"
    ],
    "columns": [
      "run_date",
      "event_key",
      "event_name",
      "event_date",
      "calendar_external_id",
      "release_at",
      "category",
      "currencies",
      "mentions",
      "brokers",
      "citations",
      "as_of"
    ]
  },
  "fx_hub_grants": {
    "pk": [
      "email"
    ],
    "columns": [
      "email",
      "granted_at",
      "note"
    ]
  },
  "fx_idea_eval": {
    "pk": [
      "run_date",
      "rank",
      "horizon_days"
    ],
    "columns": [
      "run_date",
      "rank",
      "horizon_days",
      "pair",
      "direction",
      "status",
      "entry_date",
      "exit_date",
      "entry_fix",
      "exit_fix",
      "ret",
      "sigma_entry",
      "hit",
      "significant_hit",
      "as_of",
      "hold_return",
      "directional_win",
      "n_sessions",
      "bias_verdict",
      "max_favorable",
      "max_adverse",
      "decisive_session",
      "entry_fill_session",
      "stop_price",
      "target_prices",
      "level_outcome",
      "verdict_reason",
      "outcome",
      "grade_basis",
      "closed_by",
      "idea_id",
      "timeframe"
    ]
  },
  "fx_macro_history": {
    "pk": [
      "series_id",
      "obs_date"
    ],
    "columns": [
      "series_id",
      "obs_date",
      "value"
    ]
  },
  "fx_macro_snapshot": {
    "pk": [
      "country",
      "indicator"
    ],
    "columns": [
      "country",
      "indicator",
      "label",
      "last_value",
      "previous_value",
      "highest_value",
      "lowest_value",
      "unit",
      "frequency",
      "higher_is_better",
      "last_obs_date",
      "previous_obs_date",
      "as_of"
    ]
  },
  "fx_market_snapshots": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "source_slug",
      "instrument",
      "captured_at",
      "pmt_as_of",
      "payload",
      "created_at"
    ]
  },
  "fx_position_book": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "pair",
      "close_price",
      "levels",
      "source_slug",
      "captured_at",
      "avg_long",
      "avg_short"
    ]
  },
  "fx_relevance_ledger": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "run_date",
      "source_file",
      "view_index",
      "broker_name",
      "currency",
      "direction",
      "conviction",
      "report_date",
      "calendar_external_id",
      "w_time",
      "w_event",
      "w_review",
      "relevance",
      "classification",
      "reason",
      "as_of"
    ]
  },
  "fx_relevance_llm_cache": {
    "pk": [
      "cache_key"
    ],
    "columns": [
      "cache_key",
      "currency",
      "reviews",
      "created_at"
    ]
  },
  "fx_research_history": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "file_id",
      "run_date",
      "broker_name",
      "analyst_names",
      "report_date",
      "source_file",
      "source_url",
      "trader_relevance",
      "trader_relevance_note",
      "central_thesis",
      "brief_markdown",
      "currency_views",
      "macro_themes",
      "risk_events",
      "positioning_signals",
      "vault_path",
      "created_at",
      "document_title",
      "pdf_url",
      "summary",
      "summary_points",
      "source_spans",
      "extraction_method",
      "chunk_count",
      "quality",
      "release_date"
    ]
  },
  "fx_retail_book_stats": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "pair",
      "as_of",
      "long_positions",
      "short_positions",
      "total_positions",
      "avg_long_price",
      "avg_short_price",
      "long_volume_lots",
      "short_volume_lots",
      "source_slug",
      "created_at"
    ]
  },
  "fx_retail_positioning": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "pair",
      "as_of",
      "long_pct",
      "short_pct",
      "source_slug",
      "created_at"
    ]
  },
  "fx_seasonality_forecast": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "pair",
      "horizon",
      "forecast_date",
      "probability",
      "bull",
      "bear",
      "base",
      "trend",
      "meta_start",
      "meta_end",
      "source_slug",
      "created_at"
    ]
  },
  "fx_smart_bias": {
    "pk": [
      "id"
    ],
    "columns": [
      "id",
      "currency",
      "week_first_date",
      "overall_sentiment",
      "fundamental_overview",
      "bank_overview",
      "indicators",
      "bank_sentiment",
      "created_at"
    ]
  },
  "fx_trade_ideas_snapshot": {
    "pk": [
      "run_date",
      "rank"
    ],
    "columns": [
      "run_date",
      "rank",
      "pair",
      "direction",
      "title",
      "thesis",
      "catalyst",
      "levels",
      "citations",
      "as_of",
      "conviction_score",
      "consensus_alignment",
      "rationale",
      "trade_levels",
      "evidence",
      "authored_by",
      "idea_id",
      "parent_idea_id",
      "revision",
      "timeframe"
    ]
  },
  "schema_migrations": {
    "pk": [
      "filename"
    ],
    "columns": [
      "filename",
      "applied_at"
    ]
  }
};
