/**
 * Attribute access for the index and the metrics.
 *
 * Attribute keys are read, never invented: a span carries what the source sent
 * (ADR-0036 §7 keeps the allowlist at the instrumentation layer, not here). This
 * module only answers "what did this span say about X", in the spelling the
 * OpenTelemetry gen_ai and OpenInference conventions use, so the index and the
 * Analytics Engine rows agree with what the emitters emit.
 */
import type { OtlpAnyValue, OtlpKeyValue, OtlpSpan } from "./types";

/** A value as a string, or undefined when it is absent or not scalar. */
export function stringValue(value: OtlpAnyValue | undefined): string | undefined {
  if (!value) return undefined;
  if (typeof value.stringValue === "string") return value.stringValue;
  if (typeof value.boolValue === "boolean") return String(value.boolValue);
  if (value.intValue !== undefined) return String(value.intValue);
  if (typeof value.doubleValue === "number") return String(value.doubleValue);
  return undefined;
}

/** A value as a finite number, or undefined. int64 arrives as a decimal string. */
export function numberValue(value: OtlpAnyValue | undefined): number | undefined {
  if (!value) return undefined;
  if (typeof value.intValue === "string" || typeof value.intValue === "number") {
    const n = Number(value.intValue);
    return Number.isFinite(n) ? n : undefined;
  }
  if (typeof value.doubleValue === "number" && Number.isFinite(value.doubleValue)) {
    return value.doubleValue;
  }
  if (typeof value.stringValue === "string" && value.stringValue.trim() !== "") {
    const n = Number(value.stringValue);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

/** The plain object form of an attribute list, first key wins. */
export function attributesToObject(attributes: OtlpKeyValue[] | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const pair of attributes ?? []) {
    if (!pair || typeof pair.key !== "string" || pair.key === "") continue;
    if (pair.key in out) continue;
    const value = stringValue(pair.value);
    if (value !== undefined) out[pair.key] = value;
  }
  return out;
}

/** First attribute present from an ordered list of candidate keys. */
export function pick(attributes: Record<string, string>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = attributes[key];
    if (value !== undefined && value !== "") return value;
  }
  return undefined;
}

/** First numeric attribute present from an ordered list of candidate keys. */
export function pickNumber(attributes: Record<string, string>, keys: string[]): number | undefined {
  for (const key of keys) {
    const raw = attributes[key];
    if (raw === undefined || raw === "") continue;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

export const SERVICE_NAME_KEYS = ["service.name", "service_name"];
export const MODEL_KEYS = [
  "gen_ai.response.model",
  "gen_ai.request.model",
  "llm.model_name",
  "ai.model.id",
];
export const INPUT_TOKEN_KEYS = [
  "gen_ai.usage.input_tokens",
  "llm.token_count.prompt",
  "llm.usage.prompt_tokens",
];
export const OUTPUT_TOKEN_KEYS = [
  "gen_ai.usage.output_tokens",
  "llm.token_count.completion",
  "llm.usage.completion_tokens",
];
export const COST_KEYS = ["digitrace.cost_usd", "llm.cost.total", "gen_ai.usage.cost"];
export const SESSION_KEYS = ["session.id", "gen_ai.conversation.id", "llm.session_id"];
export const ENVIRONMENT_KEYS = ["deployment.environment", "deployment.environment.name"];

/** Nanoseconds since the epoch from an OTLP timestamp, or undefined. */
export function nanos(value: string | number | undefined): bigint | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  try {
    const n = BigInt(typeof value === "number" ? Math.trunc(value) : value);
    return n >= 0n ? n : undefined;
  } catch {
    return undefined;
  }
}

/** Whole milliseconds between two nanosecond timestamps, never negative. */
export function durationMs(
  start: string | number | undefined,
  end: string | number | undefined,
): number | undefined {
  const from = nanos(start);
  const to = nanos(end);
  if (from === undefined || to === undefined || to < from) return undefined;
  return Number((to - from) / 1_000_000n);
}

/** The status code as the JSON mapping's enum name, or `UNSET`. */
export function statusName(span: OtlpSpan): string {
  const code = span.status?.code;
  if (code === undefined || code === null) return "STATUS_CODE_UNSET";
  if (typeof code === "string") {
    const upper = code.toUpperCase();
    if (upper === "OK" || upper === "STATUS_CODE_OK") return "STATUS_CODE_OK";
    if (upper === "ERROR" || upper === "STATUS_CODE_ERROR") return "STATUS_CODE_ERROR";
    return "STATUS_CODE_UNSET";
  }
  if (code === 1) return "STATUS_CODE_OK";
  if (code === 2) return "STATUS_CODE_ERROR";
  return "STATUS_CODE_UNSET";
}

const SPAN_KINDS = [
  "SPAN_KIND_UNSPECIFIED",
  "SPAN_KIND_INTERNAL",
  "SPAN_KIND_SERVER",
  "SPAN_KIND_CLIENT",
  "SPAN_KIND_PRODUCER",
  "SPAN_KIND_CONSUMER",
];

/** The span kind as the JSON mapping's enum name, or `SPAN_KIND_UNSPECIFIED`. */
export function kindName(span: OtlpSpan): string {
  const kind = span.kind;
  if (kind === undefined || kind === null) return "SPAN_KIND_UNSPECIFIED";
  if (typeof kind === "string") {
    const upper = kind.toUpperCase();
    return SPAN_KINDS.includes(upper) ? upper : "SPAN_KIND_UNSPECIFIED";
  }
  return SPAN_KINDS[kind] ?? "SPAN_KIND_UNSPECIFIED";
}

/** True when the span carries an error status or an `error` event's attribute. */
export function isErrorSpan(span: OtlpSpan): boolean {
  if (statusName(span) === "STATUS_CODE_ERROR") return true;
  return (span.events ?? []).some((event) => {
    const attributes = attributesToObject(event?.attributes);
    return attributes["exception.type"] !== undefined;
  });
}
