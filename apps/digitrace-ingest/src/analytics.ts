/**
 * Workers Analytics Engine rows.
 *
 * ADR-0036 §3: per-tenant and per-model token, cost and latency aggregates. AE
 * is fire-and-forget with no read-after-write guarantee and is sampled by
 * Cloudflare under load, so these numbers are an estimate, and the AI Gateway
 * logs are the fallback cross-check (DIG-2661).
 *
 * That contract is why a failure here never fails the message: the index and the
 * archive are the record, the aggregates are the estimate. A dropped metric
 * point must not send a stored batch back through the queue.
 */
import {
  attributesToObject,
  COST_KEYS,
  durationMs,
  INPUT_TOKEN_KEYS,
  kindName,
  MODEL_KEYS,
  OUTPUT_TOKEN_KEYS,
  pick,
  pickNumber,
  SERVICE_NAME_KEYS,
  statusName,
} from "./attributes";
import type { SpanRecord } from "./types";

export interface SpanMetrics {
  tenant: string;
  source: string;
  serviceName: string;
  model: string;
  status: string;
  kind: string;
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
  costUsd: number;
}

/** The metric row for one span. Values are read from the span, never invented. */
export function spanMetrics(record: SpanRecord, tenant: string, source: string): SpanMetrics {
  const resource = attributesToObject(record.resource.attributes);
  const span = attributesToObject(record.span.attributes);
  // The resource describes the service; the span's own attributes win for
  // model and usage, because that is where the gen_ai convention puts them.
  const merged = { ...resource, ...span };
  return {
    tenant,
    source,
    serviceName: pick(resource, SERVICE_NAME_KEYS) ?? "unknown",
    model: pick(merged, MODEL_KEYS) ?? "unknown",
    status: statusName(record.span),
    kind: kindName(record.span),
    inputTokens: pickNumber(merged, INPUT_TOKEN_KEYS) ?? 0,
    outputTokens: pickNumber(merged, OUTPUT_TOKEN_KEYS) ?? 0,
    durationMs: durationMs(record.span.startTimeUnixNano, record.span.endTimeUnixNano) ?? 0,
    // Cost is carried when the source computed it; this Worker does not price a
    // model, because a price table that drifts is a wrong number in a cost view.
    costUsd: pickNumber(merged, COST_KEYS) ?? 0,
  };
}

/**
 * Write one metric point. Never throws.
 *
 * Blobs are the dimensions the cost view groups by; doubles are the measures,
 * with a trailing count of 1 so a `sum` and a `count` come from one row.
 */
export function writeSpanMetric(
  dataset: AnalyticsEngineDataset | undefined,
  metrics: SpanMetrics,
): void {
  if (!dataset) return;
  try {
    dataset.writeDataPoint({
      indexes: [metrics.tenant],
      blobs: [
        metrics.tenant,
        metrics.source,
        metrics.serviceName,
        metrics.model,
        metrics.status,
        metrics.kind,
      ],
      doubles: [metrics.inputTokens, metrics.outputTokens, metrics.durationMs, metrics.costUsd, 1],
    });
  } catch {
    // Fire-and-forget, by contract (ADR-0036 §3).
  }
}
