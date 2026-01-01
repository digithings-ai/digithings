import { describe, expect, test } from "bun:test";
import { EMPTY_READ, type ReadResult } from "../read";
import { fxInk, fxPaneStatus, fxRunDate, fxTone } from "./fx";
import { tradingSessionsSince } from "./trading-calendar";
import { DANGER, INK, MUTE, WARN } from "../theme";

/** A `ok` read whose body has content, so tone is decided by age alone. */
const read = (asOf: string | null, lines: string[] = ["EURUSD  1.0842"]): ReadResult => ({
  status: "ok",
  lines: [...(asOf ? [`source  fx_daily_digest`] : []), ...lines],
  asOf,
});

describe("tradingSessionsSince", () => {
  test("counts the sessions a fresh run still covers as ok", () => {
    // Thursday's run, seen Thursday and Friday: inside one trading session.
    expect(tradingSessionsSince("2026-09-17", "2026-09-17")).toBe(0);
    expect(tradingSessionsSince("2026-09-17", "2026-09-18")).toBe(1);
  });

  test("a weekend costs nothing: Friday's run is still the last good one", () => {
    // Sat and Sun must not age the pane, or every weekend raises a false alarm.
    expect(tradingSessionsSince("2026-09-18", "2026-09-19")).toBe(0);
    expect(tradingSessionsSince("2026-09-18", "2026-09-20")).toBe(0);
    // Monday is the first session the pane should have been refreshed by.
    expect(tradingSessionsSince("2026-09-18", "2026-09-21")).toBe(1);
  });

  test("crosses month and year boundaries", () => {
    expect(tradingSessionsSince("2026-09-30", "2026-10-01")).toBe(1);
    // Thu 31 Dec -> Fri 1 Jan is one session, the weekend is none, Mon 4 Jan two.
    expect(tradingSessionsSince("2026-12-31", "2027-01-04")).toBe(2);
  });

  test("the incident window is far past any threshold", () => {
    // Run 2026-09-17 (Thu), read 2026-10-05 (Mon): 12 sessions elapsed.
    expect(tradingSessionsSince("2026-09-17", "2026-10-05")).toBe(12);
  });

  test("a future or same-day run date is not stale", () => {
    expect(tradingSessionsSince("2026-09-17", "2026-09-16")).toBe(0);
    // A run dated ahead of the clock is skew, not a staleness signal.
    expect(tradingSessionsSince("2027-01-01", "2026-09-17")).toBe(0);
  });

  test("refuses anything that is not a real calendar date", () => {
    expect(tradingSessionsSince("not-a-date", "2026-10-05")).toBeNull();
    expect(tradingSessionsSince("2026-09-17", "later")).toBeNull();
    expect(tradingSessionsSince("2026-13-01", "2026-10-05")).toBeNull();
    expect(tradingSessionsSince("2026-02-30", "2026-10-05")).toBeNull();
    expect(tradingSessionsSince("", "2026-10-05")).toBeNull();
  });

  test("reads a timestamp as its calendar day", () => {
    expect(tradingSessionsSince("2026-09-17T08:30:00Z", "2026-09-21")).toBe(2);
  });
});

describe("fxRunDate", () => {
  test("prefers the envelope as_of the backend threads as the run date", () => {
    expect(fxRunDate(read("2026-09-17"), { run_date: "2026-09-01" })).toBe("2026-09-17");
  });

  test("falls back to the payload run_date when the envelope is empty", () => {
    expect(fxRunDate(read(null), { run_date: "2026-09-17" })).toBe("2026-09-17");
  });

  test("falls back to a nested last run date", () => {
    expect(fxRunDate(read(null), { last_run: { date: "2026-09-17" } })).toBe("2026-09-17");
  });

  test("no date anywhere is null, not a guess", () => {
    expect(fxRunDate(read(null), {})).toBeNull();
    expect(fxRunDate(read(null), null)).toBeNull();
    expect(fxRunDate(null, null)).toBeNull();
  });
});

describe("fxTone ages the run", () => {
  test("fresh data stays ok", () => {
    expect(fxTone(read("2026-09-17"), read("2026-09-17").lines, { now: "2026-09-18" })).toBe("ok");
  });

  test("a Thursday run is ok through Friday, warn on Monday, stale on Tuesday", () => {
    // One trading session of grace, then the bands the issue asks for.
    const r = read("2026-09-17");
    expect(fxTone(r, r.lines, { now: "2026-09-17" })).toBe("ok");
    expect(fxTone(r, r.lines, { now: "2026-09-18" })).toBe("ok");
    expect(fxTone(r, r.lines, { now: "2026-09-21" })).toBe("warn");
    expect(fxTone(r, r.lines, { now: "2026-09-22" })).toBe("stale");
    expect(fxTone(r, r.lines, { now: "2026-09-23" })).toBe("stale");
  });

  test("the 2026-09 outage reads stale instead of healthy", () => {
    const r = read("2026-09-17");
    expect(fxTone(r, r.lines, { now: "2026-10-05" })).toBe("stale");
  });

  test("a weekend-old Friday run is not warned", () => {
    const r = read("2026-09-18");
    expect(fxTone(r, r.lines, { now: "2026-09-20" })).toBe("ok");
  });

  test("a pane with no run date keeps its old tone rather than crying stale", () => {
    // Static and draft tables have no run to age; a false stale there would train
    // the trader to ignore the tone.
    expect(fxTone(read(null), read(null, ["09:00 Asia/London"]).lines, { now: "2026-10-05" })).toBe("ok");
  });

  test("an empty read outranks age: no data is not old data", () => {
    const r = read("2026-09-17", [EMPTY_READ]);
    expect(fxTone(r, r.lines, { now: "2026-10-05" })).toBe("empty");
  });

  test("loading and failures still win", () => {
    expect(fxTone(null, [], { now: "2026-10-05" })).toBe("loading");
    expect(fxTone({ status: "error", lines: ["boom"], asOf: null }, ["boom"], { now: "2026-10-05" })).toBe("error");
    expect(fxTone({ status: "stub", lines: ["stub"], asOf: null }, ["stub"], { now: "2026-10-05" })).toBe("stub");
  });
});

describe("fxPaneStatus names the age", () => {
  test("says the age in trading days, not only in the tone", () => {
    expect(fxPaneStatus(read("2026-09-17"), null, "/fx/summary", "2026-10-05")).toBe(
      "as of 2026-09-17 · 12 trading days old · stale",
    );
  });

  test("warned and fresh panes read differently", () => {
    expect(fxPaneStatus(read("2026-09-17"), null, "/fx/summary", "2026-09-21")).toBe(
      "as of 2026-09-17 · 2 trading days old · warn",
    );
    expect(fxPaneStatus(read("2026-09-17"), null, "/fx/summary", "2026-09-18")).toBe(
      "as of 2026-09-17 · 1 trading day old",
    );
    expect(fxPaneStatus(read("2026-09-17"), null, "/fx/summary", "2026-09-17")).toBe(
      "as of 2026-09-17 · current session",
    );
    expect(fxPaneStatus(read("2026-09-17"), null, "/fx/summary", "2026-09-22")).toBe(
      "as of 2026-09-17 · 3 trading days old · stale",
    );
  });

  test("every aged pane names its state, so the footer never relies on colour", () => {
    // The footer renders in MUTE, so its words are the only channel that reaches
    // the reader without relying on body ink. That makes "stale named, warn not
    // named" an asymmetry worth removing: a warned pane must not be the one
    // aged state whose severity is only visible as a colour.
    const stateWord = (now: string) => {
      const parts = fxPaneStatus(read("2026-09-17"), null, "/fx/summary", now).split(" · ");
      return parts[parts.length - 1];
    };
    // ok stays quiet: "current session" is already the claim, and a `· ok` on a
    // healthy pane is noise the reader must learn to skip past.
    expect(stateWord("2026-09-17")).toBe("current session");
    expect(stateWord("2026-09-18")).toBe("1 trading day old");
    expect(stateWord("2026-09-21")).toBe("warn");
    expect(stateWord("2026-09-22")).toBe("stale");
  });

  test("falls back to the route when there is no date", () => {
    expect(fxPaneStatus(read(null), null, "/fx/sessions", "2026-10-05")).toBe("/fx/sessions");
    expect(fxPaneStatus(null, null, "/fx/summary", "2026-10-05")).toBe("/fx/summary");
  });

  test("a run dated ahead of the clock never claims the current session", () => {
    // Clock skew, or a run_date written wrong. The tone deliberately stays ok —
    // a future date is not proof of staleness — but the footer must not assert a
    // freshness it cannot support. "current session" on a 2027 run is the same
    // class of false claim as the healthy-looking pane this issue exists to kill.
    expect(fxPaneStatus(read("2027-01-01"), null, "/fx/summary", "2026-10-05")).toBe("as of 2027-01-01");
    expect(fxPaneStatus(read("2076-10-05"), null, "/fx/summary", "2026-10-05")).toBe("as of 2076-10-05");
    // One day ahead is still ahead: the same rule, at the boundary.
    expect(fxPaneStatus(read("2026-10-06"), null, "/fx/summary", "2026-10-05")).toBe("as of 2026-10-06");
  });
});

describe("warn and stale are visually distinct", () => {
  test("the warn token is the design package's dark --warn", () => {
    expect(WARN).toBe("#E0B341");
    expect(WARN).not.toBe(DANGER);
    expect(WARN).not.toBe(INK);
    expect(WARN).not.toBe(MUTE);
  });

  test("a stale pane never renders in the same ink as a healthy one", () => {
    // This is the defect: for 12 sessions the pane was indistinguishable from a
    // healthy Monday. Tone alone is not enough unless it reaches the pixel.
    expect(fxInk("stale")).toBe(DANGER);
    expect(fxInk("stale")).not.toBe(fxInk("ok"));
    expect(fxInk("warn")).toBe(WARN);
    expect(fxInk("warn")).not.toBe(fxInk("ok"));
    expect(fxInk("ok")).toBe(INK);
    expect(fxInk("empty")).toBe(MUTE);
    expect(fxInk("loading")).toBe(MUTE);
    expect(fxInk("error")).toBe(DANGER);
  });
});