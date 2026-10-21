/**
 * Ticket-index freshness (DIG-3578, same pattern as the DIG-3576 help recrawl).
 *
 * The daily Workflow writes one state record per job after every successful
 * ticket pass, even when nothing changed. This module is the pure read side:
 * turn that record into a metric and a verdict so a stale daily rebuild shows
 * as an alert instead of a silent green day.
 */

/** The daily ticket clock runs at 03:00 UTC; one missed run is stale. */
export const TICKET_FRESHNESS_ALERT_AFTER_HOURS = 26;
export const TICKET_FRESHNESS_ALERT_AFTER_MS =
  TICKET_FRESHNESS_ALERT_AFTER_HOURS * 60 * 60 * 1000;

/** Last successful ticket pass for one job. */
export type TicketSyncState = {
  lastSuccessAt: string | null;
  newestTicketAt: string | null;
  tickets: number;
  vectors: number;
  deleted: number;
};

export type TicketFreshnessReason =
  | "fresh"
  | "never_succeeded"
  | "unparseable_last_success"
  | "stale_last_success";

export type TicketFreshness = TicketSyncState & {
  job: string;
  /** Hours since the last successful pass; null when there is none. */
  ageHours: number | null;
  alert: boolean;
  reason: TicketFreshnessReason;
};

/** Reads state from KV without importing the sync module (no cycle). */
export type StateStore = {
  get(key: string): Promise<string | null>;
};

export const EMPTY_TICKET_STATE: TicketSyncState = {
  lastSuccessAt: null,
  newestTicketAt: null,
  tickets: 0,
  vectors: 0,
  deleted: 0,
};

export function ticketStateKey(jobId: string): string {
  return `corpus-index:state:${jobId}:tickets`;
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stamp(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function parseTicketState(raw: string | null): TicketSyncState {
  if (!raw) return { ...EMPTY_TICKET_STATE };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...EMPTY_TICKET_STATE };
  }
  if (typeof parsed !== "object" || parsed === null) return { ...EMPTY_TICKET_STATE };
  const record = parsed as Record<string, unknown>;
  return {
    lastSuccessAt: stamp(record.lastSuccessAt),
    newestTicketAt: stamp(record.newestTicketAt),
    tickets: count(record.tickets),
    vectors: count(record.vectors),
    deleted: count(record.deleted),
  };
}

export async function readTicketState(kv: StateStore, jobId: string): Promise<TicketSyncState> {
  return parseTicketState(await kv.get(ticketStateKey(jobId)));
}

export function ticketFreshness(
  jobId: string,
  state: TicketSyncState,
  nowMs: number = Date.now(),
): TicketFreshness {
  const base = { job: jobId, ...state };
  if (state.lastSuccessAt === null) {
    return { ...base, ageHours: null, alert: true, reason: "never_succeeded" };
  }
  const ageMs = nowMs - Date.parse(state.lastSuccessAt);
  if (!Number.isFinite(ageMs)) {
    return { ...base, ageHours: null, alert: true, reason: "unparseable_last_success" };
  }
  const ageHours = ageMs / (60 * 60 * 1000);
  if (ageMs > TICKET_FRESHNESS_ALERT_AFTER_MS) {
    return { ...base, ageHours, alert: true, reason: "stale_last_success" };
  }
  return { ...base, ageHours, alert: false, reason: "fresh" };
}
