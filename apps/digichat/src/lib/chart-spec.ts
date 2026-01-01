/**
 * Chart-spec discriminator for research responses that
 * embed an ECharts option object inside a JSON code block.
 *
 * Agreed wire format: a fenced ```json code block whose content parses to
 *
 *   { "type": "chart", "spec": { ...ECharts option... } }
 *
 * The `spec` object is passed directly to ECharts as the `option` argument
 * after stripping untrusted `formatter` fields (see stripFormatters).
 * No adapter/translation is performed — callers must emit a valid ECharts
 * option object. This keeps the supported chart set in lockstep with what
 * ECharts itself supports (bar, line, scatter, pie, etc.).
 */

export type ChartEnvelope = {
  type: "chart";
  spec: Record<string, unknown>;
};

/**
 * Parse a raw code-block string. Returns the sanitized spec object on a
 * successful match, or `null` if the text is not a chart envelope.
 *
 * Never throws — invalid JSON and shape mismatches both return `null` so
 * callers can fall back to rendering the raw code block unchanged.
 */
export function parseChartEnvelope(raw: string): Record<string, unknown> | null {
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{")) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return null;
  }

  if (!isChartEnvelope(parsed)) return null;
  return stripFormatters(parsed.spec) as Record<string, unknown>;
}

function isChartEnvelope(value: unknown): value is ChartEnvelope {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  if (v.type !== "chart") return false;
  if (!v.spec || typeof v.spec !== "object" || Array.isArray(v.spec)) return false;
  return true;
}

/**
 * Recursively remove ECharts `formatter` keys from an untrusted option tree.
 *
 * String/function formatters can inject HTML into tooltips and labels
 * (ECharts does not sanitize them). Model- or tool-emitted chart specs must
 * not carry that surface into `chart.setOption`.
 */
export function stripFormatters(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stripFormatters);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  const out: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (key === "formatter") continue;
    out[key] = stripFormatters(child);
  }
  return out;
}
