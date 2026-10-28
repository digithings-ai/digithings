/**
 * Route payloads for the digitrace Traces tab (DIG-2661, ADR-0036 section 9).
 *
 * The tab reads dashboard-api's `/traces` family, which reads the Supabase
 * `digitrace_*` index through the application-layer `workspace_id` filter.
 * Every field the worker may not return is nullable and renders an em dash or
 * a withheld state; nothing here is estimated.
 */

export type TraceListItem = {
  trace_id: string;
  name: string | null;
  source: string | null;
  service_name: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  status: string | null;
  status_message: string | null;
  session_id: string | null;
  run_id: string | null;
  span_count: number | null;
};

/** GET /traces */
export type TracesList = {
  workspace_id: string;
  traces: TraceListItem[];
  count: number;
  window: { since: string | null; until: string | null };
  empty: boolean;
};

export type TracesSpan = {
  span_id: string;
  parent_span_id: string | null;
  name: string | null;
  kind: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  status: string | null;
  status_message: string | null;
  model: string | null;
  provider: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  /** The index holds a hash and a length, never the input/output text. */
  has_content: boolean;
  children: TracesSpan[];
};

export type TracesScore = {
  span_id: string;
  name: string;
  value: number | null;
  value_text: string | null;
  source: string | null;
  created_at: string | null;
};

/** GET /traces/{trace_id} */
export type TraceDetail = {
  workspace_id: string;
  trace: TraceListItem;
  /** True when the trace row exists but the spans have not been flushed yet. */
  spans_pending: boolean;
  span_count: number;
  spans: TracesSpan[];
  scores: TracesScore[];
  token_total: number;
  cost_total_usd: number;
};

export type TraceCostBucket = {
  model: string | null;
  provider: string | null;
  spans: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
};

/** GET /traces/cost */
export type TraceCost = {
  workspace_id: string;
  window: { since: string | null; until: string | null };
  totals: {
    spans: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
  };
  by_model: TraceCostBucket[];
  /** 'index' today; the Analytics Engine aggregate is the source of record. */
  cost_source: string;
  cost_caveat: string;
  truncated: boolean;
};
