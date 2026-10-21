import { describe, expect, it } from "vitest";
import {
  EMPTY_TICKET_STATE,
  parseTicketState,
  readTicketState,
  ticketFreshness,
  ticketStateKey,
  TICKET_FRESHNESS_ALERT_AFTER_HOURS,
} from "./freshness";

const NOW = Date.parse("2026-10-19T03:30:00.000Z");

function hoursAgo(hours: number): string {
  return new Date(NOW - hours * 60 * 60 * 1000).toISOString();
}

const state = (lastSuccessAt: string | null) => ({
  ...EMPTY_TICKET_STATE,
  lastSuccessAt,
  newestTicketAt: "2026-10-18T09:00:00.000Z",
  tickets: 4,
  vectors: 4,
});

describe("ticketFreshness", () => {
  it("is fresh when the last successful sync is inside the threshold", () => {
    const verdict = ticketFreshness("occ", state(hoursAgo(3)), NOW);
    expect(verdict.alert).toBe(false);
    expect(verdict.reason).toBe("fresh");
    expect(verdict.ageHours).toBe(3);
    expect(verdict.job).toBe("occ");
  });

  it("alerts when nothing ever succeeded", () => {
    const verdict = ticketFreshness("occ", EMPTY_TICKET_STATE, NOW);
    expect(verdict.alert).toBe(true);
    expect(verdict.reason).toBe("never_succeeded");
    expect(verdict.ageHours).toBeNull();
  });

  it("alerts when the last success is older than the threshold", () => {
    const verdict = ticketFreshness(
      "occ",
      state(hoursAgo(TICKET_FRESHNESS_ALERT_AFTER_HOURS + 1)),
      NOW,
    );
    expect(verdict.alert).toBe(true);
    expect(verdict.reason).toBe("stale_last_success");
  });

  it("stays fresh exactly on the threshold boundary", () => {
    const verdict = ticketFreshness(
      "occ",
      state(hoursAgo(TICKET_FRESHNESS_ALERT_AFTER_HOURS)),
      NOW,
    );
    expect(verdict.alert).toBe(false);
  });

  it("alerts on an unparseable last success", () => {
    const verdict = ticketFreshness("occ", state("not-a-date"), NOW);
    expect(verdict.alert).toBe(true);
    expect(verdict.reason).toBe("unparseable_last_success");
  });
});

describe("parseTicketState", () => {
  it("returns the empty state for a missing or unreadable record", () => {
    expect(parseTicketState(null)).toEqual(EMPTY_TICKET_STATE);
    expect(parseTicketState("{not json")).toEqual(EMPTY_TICKET_STATE);
    expect(parseTicketState(JSON.stringify({ tickets: "x", deleted: null }))).toEqual(
      EMPTY_TICKET_STATE,
    );
  });

  it("keeps a written record", () => {
    const written = state(hoursAgo(1));
    expect(parseTicketState(JSON.stringify(written))).toEqual(written);
  });
});

describe("readTicketState", () => {
  it("reads the per-job ticket state key", async () => {
    const data = new Map<string, string>();
    const kv = { get: async (key: string) => data.get(key) ?? null };
    expect(await readTicketState(kv, "occ")).toEqual(EMPTY_TICKET_STATE);
    data.set(ticketStateKey("occ"), JSON.stringify(state(hoursAgo(1))));
    const read = await readTicketState(kv, "occ");
    expect(read.tickets).toBe(4);
    expect(read.lastSuccessAt).toBe(hoursAgo(1));
  });

  it("namespaces the key per job", () => {
    expect(ticketStateKey("occ")).toBe("corpus-index:state:occ:tickets");
    expect(ticketStateKey("occ")).not.toBe(ticketStateKey("other"));
  });
});
