import { describe, expect, it } from "vitest";
import {
  classifyOfficialRead,
  houseBookFromPayloads,
  isStubPayload,
  runFromDocuments,
  stageForDocumentKey,
  tapeFromBenchmarks,
} from "./official-api";

const STUB_PORTFOLIO = {
  data: {
    book_as_of: "2026-09-24",
    nav_tip: { date: "2026-09-24", nav: 99.909, contract: "legacy_estimate" },
    positions: [{ ticker: "DBO", weight_pct: 5.0031, is_cash: false }],
  },
  provenance: { contract: "legacy_estimate" },
};

const STUB_BRIEF = {
  data: {
    nav_tip: { date: "2026-08-28", nav: 204.04, contract: "finalized_accounting" },
    since_inception_pct: 3.040191838399986,
  },
};

const WITHHELD = {
  error: { code: "upstream_empty", message: "dashboard API has no Supabase env configured", details: {} },
};

describe("official API reads", () => {
  it("treats stub NAV figures and legacy_estimate as empty", () => {
    expect(isStubPayload(STUB_PORTFOLIO)).toBe(true);
    expect(isStubPayload(STUB_BRIEF)).toBe(true);
    expect(classifyOfficialRead(200, STUB_PORTFOLIO).ok).toBe(false);
    if (!classifyOfficialRead(200, STUB_PORTFOLIO).ok) {
      expect(classifyOfficialRead(200, STUB_PORTFOLIO).reason).toContain("stub");
    }
  });

  it("treats 502 withheld envelopes as empty", () => {
    const read = classifyOfficialRead(502, WITHHELD);
    expect(read.ok).toBe(false);
    if (!read.ok) expect(read.reason).toContain("withheld");
  });

  it("keeps a real book that is not the stub double", () => {
    const portfolio = {
      data: {
        book_as_of: "2026-10-01",
        positions: [{ ticker: "SPY", weight_pct: 10, is_cash: false }],
      },
    };
    const brief = { data: { since_inception_pct: 4.2, day_return_pct: 0.1, nav_tip: { date: "2026-10-01" } } };
    const nav = { data: { points: [{ date: "2026-10-01", nav: 110.5, day_return_pct: 0.1, contract: "finalized_accounting" }] } };
    const allocations = { data: { rows: [{ ticker: "SPY", current_price: 450.25, entry_price: 400, unrealized_pct: 12.5 }] } };
    const performance = { data: { metrics: { excess_return_pct: 1.1 }, benchmark: { ticker: "QQQ" } } };
    for (const body of [portfolio, brief, nav, allocations, performance]) {
      expect(classifyOfficialRead(200, body).ok).toBe(true);
    }
    const book = houseBookFromPayloads({ portfolio, brief, nav, allocations, performance });
    expect(book?.positions[0]?.ticker).toBe("SPY");
    expect(book?.positions[0]?.currentPrice).toBe(450.25);
    expect(book?.nav[0]?.nav).toBe(110.5);
    expect(book?.excessReturnPct).toBe(1.1);
    expect(book?.benchmarkTicker).toBe("QQQ");
  });

  it("drops the stub SPY tape and keeps a real close series", () => {
    const stub = {
      data: {
        series: {
          SPY: [
            { date: "2026-08-20", close: 500 },
            { date: "2026-08-28", close: 515 },
          ],
        },
      },
    };
    expect(tapeFromBenchmarks(stub)).toBeNull();
    const real = { data: { series: { "BTC-USD": [{ date: "2026-10-01", close: 60000 }] } } };
    expect(tapeFromBenchmarks(real)).toEqual([{ symbol: "BTC-USD", points: [{ date: "2026-10-01", price: 60000 }] }]);
  });

  it("builds a run only from real document rows", () => {
    expect(stageForDocumentKey("attention-plan")).toBe("Inputs");
    expect(stageForDocumentKey("beliefs")).toBe("Learning");
    expect(runFromDocuments([])).toBeNull();
    const snap = runFromDocuments([
      { document_key: "attention-plan", title: "Attention plan", date: "2026-10-01", run_type: "house" },
      { document_key: "beliefs", title: "Beliefs", date: "2026-10-01", run_type: "house" },
    ]);
    expect(snap?.runDate).toBe("2026-10-01");
    expect(snap?.stages.find((s) => s.name === "Inputs")?.status).toBe("recorded");
    expect(snap?.stages.find((s) => s.name === "Decision")?.status).toBe("not-recorded");
    expect(snap?.stages.find((s) => s.name === "Inputs")?.titles).toEqual(["Attention plan"]);
  });
});
