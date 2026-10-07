import { describe, expect, test } from "bun:test";
import { DASH, type ReadResult } from "../read";
import { fxBlockLines, fxInk, fxPaneStatus, fxTone } from "./fx";
import { shapeLines } from "./shape";

/**
 * Criterion 2 of DIG-183: ageing one FX block and leaving the rest green "looks
 * fixed and is worse than not ageing". So these tests drive every named block
 * through the same two calls `FxBlock` makes — `fxBlockLines` then `fxTone` — so
 * a block that stops carrying a run date fails on its own row rather than
 * hiding behind a sibling that still works.
 */

/** Envelope as the route returns it, carrying the run date it does thread. */
const envelope = (asOf: string | null, source: string): ReadResult => ({
  status: "ok",
  lines: [`source  ${source}`, "marks  unavailable"],
  asOf,
});

/** Payloads shaped as `apps/dashboard-api/src/routes/fx.ts` actually returns them. */
const payload = {
  "fx-summary": {
    desk: "fx",
    run_date: "2026-09-17",
    posture: "patient",
    pairs: { count: 7 },
    ideas: { count: 3 },
    paper_exposure: { gross_usd: 0 },
    session: { name: "London" },
    research_flags: { count: 0 },
    read: { lead: "Dollar strength is fading.", body: "Two pairs sit at support." },
  },
  "fx-pairs": {
    pairs: [{ pair: "EURUSD", bid: 1.0842, offer: 1.0844, day_pct: -0.21, bias: "long", status: "open" }],
  },
  "fx-levels": {
    levels: [{ pair: "EURUSD", mark: 1.0842, level: 1.08, role: "support", pips: 42, flag: "held" }],
  },
  // The static session skeleton: three rows, every state null, no run behind it.
  "fx-sessions": {
    sessions: [
      { session: "Asia", state: null, note: null },
      { session: "London", state: null, note: null },
      { session: "New York", state: null, note: null },
    ],
  },
  "fx-ideas": {
    ideas: [{ rank: 1, pair: "EURUSD", bias: "long", horizon: "2d", status: "open", thread: "t-1" }],
  },
} as const;

type BlockId = keyof typeof payload;

/** The four blocks whose route threads a run date, and where it comes from. */
const DATED: readonly { id: BlockId; source: string }[] = [
  { id: "fx-summary", source: "fx_daily_digest" },
  { id: "fx-pairs", source: "fx_pair_quote_snapshots" },
  { id: "fx-levels", source: "fx_level_snapshots" },
  { id: "fx-ideas", source: "fx_trade_ideas_snapshot" },
];

/** Tone for one block, through exactly the path FxBlock uses. */
const tone = (id: BlockId, asOf: string | null, source: string, now: string) => {
  const result = envelope(asOf, source);
  return fxTone(result, fxBlockLines(id, result, payload[id]), { now, data: payload[id] });
};

describe("every dated FX block ages on its own account", () => {
  // A run from Thu 2026-09-17, read across the week. Thu/Fri is the one session
  // of grace; Mon is the first day the desk owes a refresh; Tue is the second
  // missed run and goes red. The bands are the ones the board accepted.
  for (const { id, source } of DATED) {
    test(`${id} walks ok -> warn -> stale as its own run falls behind`, () => {
      expect(tone(id, "2026-09-17", source, "2026-09-17")).toBe("ok");
      expect(tone(id, "2026-09-17", source, "2026-09-18")).toBe("ok");
      expect(tone(id, "2026-09-17", source, "2026-09-21")).toBe("warn");
      expect(tone(id, "2026-09-17", source, "2026-09-22")).toBe("stale");
      expect(tone(id, "2026-09-17", source, "2026-10-05")).toBe("stale");
    });
  }

  test("a mutant that hardcodes stale for everything cannot pass this suite", () => {
    // Four blocks each assert `ok` on a fresh run. The moment one stops ageing,
    // or starts ageing regardless of date, this list is where it dies.
    for (const { id, source } of DATED) {
      expect(tone(id, "2026-09-17", source, "2026-09-17")).toBe("ok");
      expect(tone(id, "2026-09-17", source, "2026-09-18")).toBe("ok");
    }
  });

  test("each block names its own age, so no block borrows a sibling's date", () => {
    for (const { id, source } of DATED) {
      const status = fxPaneStatus(envelope("2026-09-17", source), payload[id], id, "2026-10-05");
      expect(status).toBe("as of 2026-09-17 · 12 trading days old · stale");
    }
  });

  test("a weekend costs no age: Friday's run read Monday morning is still ok", () => {
    // The false-alarm guard. Wall-clock ageing would warn every Monday, and an
    // alarm people learn to ignore is how the 2026-09 outage went unnoticed.
    for (const { id, source } of DATED) {
      expect(tone(id, "2026-09-18", source, "2026-09-19")).toBe("ok");
      expect(tone(id, "2026-09-18", source, "2026-09-20")).toBe("ok");
      // Monday is still age 1 — the weekend is not a missed session — so the
      // Monday-morning read stays ok. Warn arrives with Tuesday's missed run.
      expect(tone(id, "2026-09-18", source, "2026-09-21")).toBe("ok");
      expect(tone(id, "2026-09-18", source, "2026-09-22")).toBe("warn");
    }
  });

  test("the age counts trading days across a weekend, not calendar days", () => {
    // Thu 17 -> Wed 23 is six calendar days and four sessions. Naming "6" would
    // be a number the trader cannot check against the trading calendar.
    for (const { id, source } of DATED) {
      const status = fxPaneStatus(envelope("2026-09-17", source), payload[id], id, "2026-09-23");
      expect(status).toBe("as of 2026-09-17 · 4 trading days old · stale");
      expect(status).not.toContain("6 trading days");
    }
  });
});

describe("fx-sessions cannot read healthy", () => {
  // `/fx/sessions` is a static skeleton: `sessions()` in dashboard-api takes no
  // database and returns three hardcoded rows with null state. There is no run to
  // age and no value to show. Rendering three rows of dashes in green ink is the
  // same false claim DIG-183 exists to kill, just with less content behind it.
  const sessionsTone = (now: string, rows = payload["fx-sessions"].sessions) => {
    const result = envelope(null, "static-sessions");
    return fxTone(result, fxBlockLines("fx-sessions", result, { sessions: rows }), { now, data: null });
  };

  test("an empty skeleton is muted, never green, however long it sits there", () => {
    expect(sessionsTone("2026-09-17")).toBe("empty");
    expect(sessionsTone("2026-10-05")).toBe("empty");
    expect(fxInk(sessionsTone("2026-10-05"))).not.toBe(fxInk("ok"));
  });

  test("a populated session row ages like any other block", () => {
    // Proves the block is not simply hard-wired to empty: when the route starts
    // returning real states and a run date, this pane ages with everything else.
    const result = envelope("2026-09-17", "fx_session_states");
    const rows = [{ session: "London", state: "open", note: null }];
    const lines = fxBlockLines("fx-sessions", result, { sessions: rows });
    expect(fxTone(result, lines, { now: "2026-09-17", data: { sessions: rows } })).toBe("ok");
    expect(fxTone(result, lines, { now: "2026-09-22", data: { sessions: rows } })).toBe("stale");
    expect(fxPaneStatus(result, { sessions: rows }, "fx-sessions", "2026-09-22")).toBe(
      "as of 2026-09-17 · 3 trading days old · stale",
    );
  });
});

// ---------------------------------------------------------------------------
// QA follow-ups on the fx-sessions change (DIG-2104, verdict on DIG-2071).
// ---------------------------------------------------------------------------

type SessionRow = { session: string; state: string | null; note: string | null };

/** The three rows `/fx/sessions` answers with today: named sessions, no state. */
const SKELETON: SessionRow[] = [
  { session: "Asia", state: null, note: null },
  { session: "London", state: null, note: null },
  { session: "New York", state: null, note: null },
];

/** One session provisioned, two not. The partial rollout the route will do. */
const MIXED: SessionRow[] = [
  { session: "London", state: "open", note: null },
  { session: "Asia", state: null, note: null },
  { session: "New York", state: null, note: null },
];

/** The pane body without the provenance head `fxBlockLines` keeps above it. */
const body = (lines: string[]) => lines.filter((line) => !line.startsWith("source  ") && !line.startsWith("marks  "));

/** The fx-sessions block as the pane builds it, for a given row list. */
const sessionsBlock = (rows: SessionRow[], asOf: string | null = null) => {
  const result = envelope(asOf, asOf === null ? "static-sessions" : "fx_session_states");
  const data = { sessions: rows };
  return { result, data, lines: fxBlockLines("fx-sessions", result, data) };
};

describe("fx-sessions names the cause, not the absence", () => {
  test("an unprovisioned block reads `sessions not provisioned`", () => {
    // `sessions()` in dashboard-api has no table behind it, the same as the flags,
    // paper and directives blocks. Those all surface the client's existing
    // sentence for a draft migration, so this block said a different thing for the
    // same situation -- and `no session state` sat one line from `no sessions`, the
    // empty-list case, on the same muted ink. Cause, not absence, and no new rule.
    const { lines } = sessionsBlock(SKELETON);
    expect(body(lines)).toEqual(["sessions not provisioned"]);
  });

  test("both quiet rules already know that sentence, so neither was edited", () => {
    // `isQuiet()` in fx.tsx matches `not provisioned`; `isSentence()` in shape.ts
    // matches it too. The pane tone proves the first, the block shape the second.
    // Both read the sentence this block actually renders, so a string that needed a
    // new branch in either file fails here instead of quietly going bright.
    const { result, data, lines } = sessionsBlock(SKELETON);
    const tone = fxTone(result, lines, { now: "2026-10-05", data });
    expect(tone).toBe("empty");
    expect(fxInk(tone)).not.toBe(fxInk("ok"));
    expect(shapeLines(body(lines))).toEqual({
      blocks: [{ kind: "sentence", text: "sessions not provisioned" }],
    });
  });

  test("`no sessions` and `sessions not provisioned` stay two different situations", () => {
    // Empty array: the desk has no sessions to report. Populated array, nothing
    // filled in: the sessions exist and their state is not provisioned. Same ink,
    // two sentences, and the reader can tell which one they are looking at.
    const empty = body(sessionsBlock([]).lines);
    const unprovisioned = body(sessionsBlock(SKELETON).lines);
    expect(empty).toEqual(["no sessions"]);
    expect(unprovisioned).toEqual(["sessions not provisioned"]);
  });
});

describe("fx-sessions filters rows per-row, not per-list", () => {
  test("one populated row does not switch the guard off for the others", () => {
    // The defect QA reproduced: `every` over the whole list meant a single
    // provisioned session put `session Asia  state —` back on healthy ink beside
    // it. The rows are judged one at a time, so only London paints.
    const { lines } = sessionsBlock(MIXED);
    expect(body(lines)).toEqual(["session London  state open"]);
  });

  test("a row that drops out leaves no dash and no name behind", () => {
    const { lines } = sessionsBlock(MIXED);
    const painted = body(lines).join("\n");
    expect(painted).not.toContain("Asia");
    expect(painted).not.toContain("New York");
    expect(painted).not.toContain(DASH);
  });

  test("a mixed list still ages on its run date once one row carries state", () => {
    // Filtering the rows must not cost the block its ageing: it is the populated
    // row that gives the pane something to be stale about.
    const { result, data, lines } = sessionsBlock(MIXED, "2026-09-17");
    expect(fxTone(result, lines, { now: "2026-09-17", data })).toBe("ok");
    expect(fxTone(result, lines, { now: "2026-09-22", data })).toBe("stale");
  });

  test("a row carrying only a note counts as provisioned", () => {
    // A half day or a holiday is provisioned data. Dropping it would hide the
    // one thing the desk did manage to say.
    const { lines } = sessionsBlock([{ session: "London", state: null, note: "half day" }]);
    expect(body(lines)).toEqual([`session London  state ${DASH}  half day`]);
  });

  test("a fully populated list renders every row", () => {
    const rows: SessionRow[] = [
      { session: "Asia", state: "closed", note: null },
      { session: "London", state: "open", note: "quiet" },
      { session: "New York", state: "pre", note: null },
    ];
    expect(body(sessionsBlock(rows).lines)).toEqual([
      "session Asia  state closed",
      "session London  state open  quiet",
      "session New York  state pre",
    ]);
  });
});
