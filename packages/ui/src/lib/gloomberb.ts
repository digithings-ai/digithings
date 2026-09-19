/**
 * Gloomberb attribution + deep-link conventions shared by the frontend
 * surfaces (#4098).
 *
 * The constants mirror
 * `digiquant/src/digiquant/data/gloomberb/attribution.py` — keep the strings
 * and the `?ticker=` deep-link form in sync (spec §7).
 */

export const GLOOMBERB_ATTRIBUTION = "Sourced from Gloomberb";
export const GLOOMBERB_DELAY_NOTICE = "Data delayed up to 15 minutes";
export const GLOOMBERB_TERMINAL_URL = "https://term.gloom.sh/";

export type GloomberbAttribution = {
  attribution: string;
  delayNotice?: string;
  sourceUrl?: string;
};

/** Deep link to the Gloomberb terminal page for *symbol*. */
export function gloomberbTickerUrl(symbol: string): string {
  return `${GLOOMBERB_TERMINAL_URL}?ticker=${encodeURIComponent(symbol.trim())}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed.startsWith("{")) return value;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

/**
 * Reads the §7 attribution block off a tool result. Unwraps the `result`
 * envelope (digifetch payloads) and JSON-string results, then requires a
 * non-blank `attribution` string: payloads that do not carry one (Yahoo-backed
 * tools) return null so no surface credits Gloomberb for data it did not
 * source. `source_url` is surfaced only when it is a `term.gloom.sh` link, so
 * an off-terminal URL never wears the branded link.
 */
export function readGloomberbAttribution(result: unknown): GloomberbAttribution | null {
  let payload = asRecord(parseMaybeJson(result));
  if (payload && "result" in payload) {
    payload = asRecord(parseMaybeJson(payload.result));
  }
  if (
    !payload ||
    typeof payload.attribution !== "string" ||
    payload.attribution.trim() === ""
  ) {
    return null;
  }
  const attribution = payload.attribution;
  const sourceUrl = payload.source_url;
  return {
    attribution,
    delayNotice:
      typeof payload.delay_notice === "string" ? payload.delay_notice : undefined,
    sourceUrl:
      typeof sourceUrl === "string" && sourceUrl.startsWith(GLOOMBERB_TERMINAL_URL)
        ? sourceUrl
        : undefined,
  };
}
