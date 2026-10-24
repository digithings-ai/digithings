import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { STUB_READ, type ReadResult } from "digiquant-tui/read";
import { FxPaneBlock, FX_BLOCK_IDS, isFxBlock } from "./fx-panes";

const OK: ReadResult = { status: "ok", lines: [], asOf: "2026-09-24" };

const render = (id: string, read: ReadResult | undefined, data?: unknown) =>
  renderToStaticMarkup(<FxPaneBlock id={id} read={read} data={data} />);

/** `/fx/summary` as the API serves it, including the fields it leaves null. */
const SUMMARY = {
  desk: "fx",
  run_date: "2026-09-24",
  posture: null,
  pairs: { count: 7, note: null },
  ideas: { count: 9, note: null },
  paper_exposure: { gross_usd: null, venue: null },
  session: { name: null, note: null },
  research_flags: { count: null },
  read: { lead: "Dollar softer into the fix.", body: null },
  changes: ["carry unwound", "vol bid"],
};

const PAIRS = {
  pairs: [
    { pair: "EURUSD", bid: null, offer: null, day_pct: null, bias: "long", status: null },
    { pair: "USDJPY", bid: 151.2, offer: 151.24, day_pct: 0.31, bias: "short", status: "open" },
  ],
};

const IDEAS = {
  ideas: [
    {
      rank: 1,
      pair: "USDJPY",
      bias: "long",
      horizon: "1w",
      invalidation: 151.2,
      status: "open",
      levels: null,
      thread: "Carry still pays.",
    },
  ],
};

const CURVE = {
  curve: [
    { tenor: "2Y", yield_pct: 4.1, day_change: 0.03 },
    { tenor: "10Y", yield_pct: 4.35, day_change: -0.02 },
  ],
  spreads: [{ label: "10Y-2Y", bp: 25, day_bp: -5 }],
};

describe("fx panes", () => {
  it("knows the panes it paints and leaves the rest alone", () => {
    for (const id of FX_BLOCK_IDS) expect(isFxBlock(id)).toBe(true);
    expect(isFxBlock("ledger")).toBe(false);
    expect(isFxBlock("live")).toBe(false);
    expect(isFxBlock("rt-unknown")).toBe(false);
  });

  it("paints the FX summary as figures, the digest lead and the changes", () => {
    const html = render("fx-summary", OK, SUMMARY);
    expect(html).toContain("Run");
    expect(html).toContain("2026-09-24");
    expect(html).toContain("Pairs");
    expect(html).toContain("Ideas");
    expect(html).toContain("Paper gross");
    expect(html).toContain("not in payload");
    expect(html).toContain("Dollar softer into the fix.");
    expect(html).toContain("carry unwound");
    // A null posture says so rather than guessing a stance.
    expect(html).toContain("Posture");
    expect(html).not.toContain(">long<");
  });

  it("marks an empty marks column instead of printing zeros", () => {
    const html = render("fx-pairs", OK, PAIRS);
    expect(html).toContain("EURUSD");
    expect(html).toContain("USDJPY");
    expect(html).toContain("151.2000");
    expect(html).toContain("+0.31%");
    expect(html).toContain("Marks");

    // The API leaves bid/offer null: the cell is — and the KPI says why.
    const unmarked = render("fx-pairs", OK, {
      pairs: [{ pair: "EURUSD", bid: null, offer: null, day_pct: null, bias: null, status: null }],
    });
    expect(unmarked).toContain("no bid, offer or mark in this payload");
    expect(unmarked).not.toMatch(/0\.0000/);
  });

  it("sorts the FX pairs table by its numeric columns", () => {
    const html = render("fx-pairs", OK, PAIRS);
    // Each sortable header is a real button with aria-sort on the th.
    expect(html).toContain('aria-sort="none"');
    expect(html).toContain(">bid<span");
    expect(html).toContain(">day<span");
  });

  it("paints the levels and sessions tables", () => {
    const levels = render("fx-levels", OK, {
      levels: [{ pair: "USDJPY", mark: null, level: null, role: null, pips: null }],
    });
    expect(levels).toContain("USDJPY");
    expect(levels).toContain("Levels");

    const sessions = render("fx-sessions", OK, {
      sessions: [{ session: "Asia", state: null, note: null }],
    });
    expect(sessions).toContain("Asia");
    expect(sessions).toContain("no session state in this payload");
  });

  it("paints the ideas table with the invalidation the payload carried", () => {
    const html = render("fx-ideas", OK, IDEAS);
    expect(html).toContain("USDJPY");
    expect(html).toContain("Carry still pays.");
    expect(html).toContain("151.20");
    expect(html).toContain("Invalidations");
  });

  it("paints one idea as figures and prose, naming every field it lacks", () => {
    const html = render("fx-idea-detail", OK, {
      pair: "USDJPY",
      rank: 1,
      headline: "Yen carry",
      rationale: "Rate differential still pays.",
      bias: "long",
      horizon: "1w",
      status: "open",
      invalidation: null,
      entry: null,
      target: null,
      catalyst: "BoJ",
      evidence_note: null,
    });
    expect(html).toContain("Yen carry");
    expect(html).toContain("catalyst · BoJ");
    expect(html).toContain("Invalidation");
    expect(html).toContain("not in payload");
    expect(html).not.toContain(">$");
  });

  it("draws the session path as a sparkline and names the missing series", () => {
    const drawn = render("fx-pair-path", OK, {
      pair: "USDJPY",
      session: null,
      points: [
        { t: "2026-09-24T01:00:00Z", v: 151.2 },
        { t: "2026-09-24T02:00:00Z", v: 151.4 },
      ],
      note: null,
    });
    expect(drawn).toContain("<svg");
    expect(drawn).toContain("USDJPY session path over 2 points");
    expect(drawn).toContain("Points");

    const empty = render("fx-pair-path", OK, {
      pair: "GBPUSD",
      session: null,
      points: [],
      note: "no core series id for this pair",
    });
    expect(empty).toContain('data-state="empty"');
    expect(empty).toContain("no core series id for this pair");
  });

  it("withholds a research flag that was never provisioned, with the API's own reason", () => {
    const scope = "not provisioned — migration drafted, not applied";
    const html = render("fx-flags", OK, {
      pair: "USDJPY",
      flagged: null,
      level: null,
      text: null,
      scope_note: scope,
    });
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("No research flag for USDJPY.");
    expect(html).toContain(scope);
    expect(html).not.toContain("Flagged");
  });

  it("withholds paper exposure when there is no gross, and names the note", () => {
    const scope = "not provisioned — migration drafted, not applied";
    const html = render("fx-paper-exposure", OK, {
      venue: null,
      gross_usd: null,
      note: scope,
      lines: [],
    });
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("Paper exposure not reported.");
    expect(html).toContain(scope);
  });

  it("paints the rates summary from the curve's mark count", () => {
    const html = render("rt-summary", OK, {
      desk: "rates",
      run_date: "2026-09-24",
      posture: null,
      watchlist: { names: null, marks_available: 4 },
      theses: null,
      last_run: { date: "2026-09-24", note: null },
      budget: { spent_usd: null, cap_usd: null },
      read: null,
      signals: [],
      risks: [],
    });
    expect(html).toContain("Marks");
    expect(html).toContain("4");
    expect(html).toContain("curve points with a yield");
    expect(html).toContain("not in payload cap");
    expect(html).toContain("Spent");
  });

  it("paints the rates curve as a sortable table with the spread", () => {
    const html = render("rt-curve", OK, CURVE);
    expect(html).toContain("2Y");
    expect(html).toContain("10Y");
    expect(html).toContain("4.10%");
    expect(html).toContain("4.35%");
    expect(html).toContain("+0.03%");
    expect(html).toContain("-0.02%");
    expect(html).toContain("+25.0");
    expect(html).toContain("-5.0");
    expect(html).toContain(">tenor<span");
    expect(html).toContain('aria-sort="none"');
  });

  it("says an empty watchlist is empty rather than drawing a blank pane", () => {
    const html = render("rt-watchlist", OK, { names: [] });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("No watchlist names in this read.");
    expect(html).toContain("names is an empty list in this payload.");
  });

  it("paints the rates theses with the counts the payload carried", () => {
    const html = render("rt-theses", OK, {
      theses: [
        {
          id: "rates",
          name: "Higher for longer",
          state: "active",
          vehicles: ["TLT"],
          evidence: "CPI prints",
          kill_condition: null,
          note: null,
        },
      ],
      counts: { active: 1, watch: 0, exited: 0 },
    });
    expect(html).toContain("Higher for longer");
    expect(html).toContain("TLT");
    expect(html).toContain("CPI prints");
    expect(html).toContain("active");
  });

  it("reads as loading, error and withheld before it paints anything", () => {
    const loading = render("fx-pairs", undefined, undefined);
    expect(loading).toContain('data-state="loading"');
    expect(loading).toContain("reading /fx/pairs");

    const error = render("fx-pairs", { status: "error", lines: ["/fx/pairs failed (403): forbidden"], asOf: null }, null);
    expect(error).toContain('role="alert"');
    expect(error).toContain("/fx/pairs failed (403): forbidden");

    const stub = render("fx-pairs", { status: "stub", lines: [STUB_READ], asOf: null }, PAIRS);
    expect(stub).toContain('data-state="withheld"');
    expect(stub).toContain(STUB_READ);
    expect(stub).not.toContain("EURUSD");
  });

  it("withholds a payload that is not an object and names a pane it cannot paint", () => {
    const list = render("fx-pairs", OK, [1, 2, 3]);
    expect(list).toContain('data-state="withheld"');
    expect(list).toContain("a list, not an object");

    const unknown = render("fx-unknown", OK, { pairs: [] });
    expect(unknown).toContain("No block for this pane.");
    expect(unknown).toContain("fx-unknown has no FX block (fx-unknown).");
  });
});
