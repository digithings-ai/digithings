/**
 * Pure request validation for POST /backfill — the Cloudflare-native dispatch
 * surface for dated snapshot backfills (DIG-55 rework, DIG-753).
 *
 * This module holds no Workers plumbing on purpose. The whole guard ladder runs
 * before a single request leaves the Worker, so it is cheaper to prove it here
 * than through the Durable Object and the GitHub token.
 *
 * ## Why exact dates only
 *
 * Twelve-x `maintenance.yml` accepts `backfill_snapshots`, `since`, `until` and
 * `dates` (DIG-52, twelve-x PR #254). This endpoint deliberately accepts
 * `dates` alone and refuses `since` / `until`.
 *
 * A range cannot be made idempotent per date from here: this Worker does not
 * read the snapshot store, so it cannot enumerate which `run_dates` a range
 * resolves to, and therefore cannot record per-date state for them. A range is
 * also the unbounded shape the 2026-09-28 surplus came from — `--since` alone
 * re-stamps every date from the bound forward. The sanctioned production
 * surface takes a named date list, which is both exactly what the remediation
 * needs and the only form whose idempotence is provable rather than asserted.
 *
 * `run_date` is not an input to `maintenance.yml` at all (it belongs to
 * `daily_run.yml`). Sending it yields a GitHub 422 while the caller logs 200
 * and starts zero runs — the 2026-09-28 outage shape — so it is refused here
 * by the same allowlist that refuses every other unexpected key.
 */

/** The only keys POST /backfill accepts. Anything else is refused unbuilt. */
export const BACKFILL_INPUT_KEYS = ["dates", "force_dates"] as const;

export type BackfillInputKey = (typeof BACKFILL_INPUT_KEYS)[number];

/**
 * Cap on distinct dates in one dispatch. The remediation list is ten dates;
 * this is generous headroom, not a target. A caller wanting more than this is
 * asking for a range, which this endpoint does not do on purpose.
 */
export const MAX_BACKFILL_DATES = 32;

export type BackfillRefusalCode =
  | "invalid_json"
  | "invalid_args"
  | "unexpected_arg"
  | "missing_required_arg"
  | "invalid_dates"
  | "too_many_dates";

export type BackfillPlan =
  | { ok: true; dates: string[]; force_dates: boolean }
  | { ok: false; code: BackfillRefusalCode; detail: string };

/**
 * True only for a real `YYYY-MM-DD` calendar date.
 *
 * The `Date.UTC` round-trip is what rejects `2026-02-30` and `2026-13-01`:
 * those parse as strings but normalize to a different day/month, and a bad date
 * passed to twelve-x selects the wrong run dates or none at all.
 */
export function isIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

/**
 * Date list to trimmed, non-empty parts.
 *
 * Separators are commas, newlines and runs of spaces, because the list this
 * endpoint exists for is a remediation list pasted out of an incident record,
 * and those arrive newline-separated about as often as comma-separated. A
 * `YYYY-MM-DD` token contains no whitespace, so treating any whitespace run as
 * a separator cannot split a valid date in half.
 */
export function splitDateList(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

/**
 * Validate a raw request body and return the dates it asks for.
 *
 * Takes the body as a string so `invalid_json` is reachable from a unit test
 * without constructing a `Request`. Every refusal here happens before the
 * caller touches the ledger or builds an upstream request.
 */
export function buildPlan(rawBody: string): BackfillPlan {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    return { ok: false, code: "invalid_json", detail: "body is not valid JSON" };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { ok: false, code: "invalid_args", detail: "body must be a JSON object" };
  }

  const entries = Object.entries(parsed as Record<string, unknown>);

  // Unknown keys first: a refused key is refused whether or not its value is
  // well-formed, and naming the key is the useful part of the 400.
  for (const [key] of entries) {
    if (!(BACKFILL_INPUT_KEYS as readonly string[]).includes(key)) {
      return {
        ok: false,
        code: "unexpected_arg",
        detail: `${key} is not accepted; send only ${BACKFILL_INPUT_KEYS.join(", ")}`,
      };
    }
  }

  const args: Record<string, string> = {};
  for (const [key, value] of entries) {
    if (typeof value !== "string") {
      return { ok: false, code: "invalid_args", detail: `${key} must be a string` };
    }
    args[key] = value;
  }

  const forceRaw = args.force_dates;
  if (forceRaw !== undefined && forceRaw !== "true") {
    return {
      ok: false,
      code: "invalid_args",
      detail: 'force_dates, when present, must be the string "true"',
    };
  }

  const rawDates = args.dates;
  if (rawDates === undefined || rawDates.trim() === "") {
    return {
      ok: false,
      code: "missing_required_arg",
      detail: "dates is required; a bare dispatch is refused before any upstream request",
    };
  }

  const parts = splitDateList(rawDates);
  if (parts.length === 0) {
    return { ok: false, code: "invalid_dates", detail: "dates carries no date" };
  }
  for (const part of parts) {
    if (!isIsoDate(part)) {
      return {
        ok: false,
        code: "invalid_dates",
        detail: `${part} is not a YYYY-MM-DD calendar date`,
      };
    }
  }

  // Collapse duplicates before the cap: a repeated date is the same unit of
  // work, so ten dates sent twice is ten dates, not twenty.
  const dates = [...new Set(parts)].sort();
  if (dates.length > MAX_BACKFILL_DATES) {
    return {
      ok: false,
      code: "too_many_dates",
      detail: `${dates.length} dates exceeds the ${MAX_BACKFILL_DATES} date cap`,
    };
  }

  return { ok: true, dates, force_dates: forceRaw === "true" };
}
