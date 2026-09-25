/**
 * Slice 0007 validation: the Worker's live responses match the current
 * client-side derivations byte-for-value across all 8 route groups.
 *
 * Method: drive the REAL `src/index.ts` fetch handler (stub doubles, no
 * network, no secrets) and compare against the REAL client functions
 * imported from `apps/dashboard/lib/*` — never re-implemented expectations.
 * Fixture inputs that the stubs keep module-private (ledger marks, live
 * positions) are read back through the stubs' own builders where possible;
 * where the stub module does not export them, the test quotes the
 * `src/stubs.ts`-documented fixture rows as inputs (inputs, not expectations —
 * every expected value comes out of a real client function).
 *
 * Browser seam (explicit): `use-live-brief-kpis` (react hooks + `useLivePrices`
 * Supabase Realtime `postgres_changes` on `prices_live`) and the live lane in
 * `apps/dashboard/app/page.tsx` cannot run in the node vitest env. Their pure
 * decision surface — `isLiveMarksOverlay`, `persistedHeadlinesFromNav`,
 * `persistedInsightMetrics` — is what this suite pins; the subscription
 * plumbing stays client-side per CONTRACT §5.
 */
import { describe, expect, it } from "vitest";
import app, { type Env } from "./index";
import {
  STUB_NAV_ROWS,
  STUB_SNAPSHOT,
  STUB_SPY6,
  stubLiveDeps,
} from "./stubs";
// Server counterparts (parity peers, not expectations).
import { resolveInvestedPct as serverResolveInvestedPct } from "./invested";
import {
  chainNavContinuity as serverChainNavContinuity,
  crossesNavSeam as serverCrossesNavSeam,
  isNavSeriesSeam as serverIsNavSeriesSeam,
  navContinuityStepPct as serverNavContinuityStepPct,
} from "./nav-series";
import {
  averageEntryAsOf as serverAverageEntryAsOf,
  ledgerEventEconomics as serverLedgerEventEconomics,
  realizedReturnVsAverageEntry as serverRealizedReturn,
  soldWeightPct as serverSoldWeightPct,
} from "./ledger";
import { isLiveMarksOverlay as serverIsLiveMarksOverlay } from "./ssot";
// REAL client derivations.
import {
  chainNavContinuity as clientChainNavContinuity,
  isNavSeriesSeam as clientIsNavSeriesSeam,
  navContinuityStepPct as clientNavContinuityStepPct,
  navRowContractLabel as clientNavRowContractLabel,
} from "../../dashboard/lib/accounting-views";
import { reconcileBook as clientReconcileBook } from "../../dashboard/lib/book-reconciliation";
import { selectBriefLedgerDayEvents as clientSelectBriefDayEvents } from "../../dashboard/lib/brief-book-event";
import {
  crossesNavSeam as clientCrossesNavSeam,
  isLiveMarksOverlay as clientIsLiveMarksOverlay,
  navContractBadgeLabel as clientNavContractBadgeLabel,
  PERSISTED_KPI_TOLERANCE_PP as CLIENT_PERSISTED_TOLERANCE_PP,
  persistedHeadlinesFromNav as clientPersistedHeadlines,
  persistedInsightMetrics as clientPersistedInsights,
  resolveInvestedPct as clientResolveInvestedPct,
} from "../../dashboard/lib/performance-ssot";
import {
  averageEntryAsOf as clientAverageEntryAsOf,
  ledgerEventEconomics as clientLedgerEventEconomics,
  realizedReturnVsAverageEntry as clientRealizedReturn,
  soldWeightPct as clientSoldWeightPct,
} from "../../dashboard/lib/position-event-economics";
import type { Position as ClientPosition } from "../../dashboard/lib/types";
import {
  computeLiveVsMarkPct as clientComputeLiveVsMarkPct,
  MIN_OVERLAP_DAYS as CLIENT_MIN_OVERLAP_DAYS,
} from "@digithings/ui";
import { benchmarkOverlapMeetsFloor as serverOverlapMeetsFloor } from "./benchmarks";
import { sortTickerUniverse as clientSortTickerUniverse } from "../../dashboard/lib/benchmark-tickers";

const NO_ENV: Env = {};
const get = (path: string) => new Request(`https://worker${path}`);

async function dataOf(path: string): Promise<{ status: number; data: never; body: Record<string, unknown> }> {
  const res = await app.fetch(get(path), NO_ENV);
  const body = (await res.json()) as Record<string, unknown>;
  return { status: res.status, data: body["data"] as never, body };
}

function clientPosition(ticker: string, weightActual: number): ClientPosition {
  return {
    ticker,
    name: ticker,
    type: "LONG",
    weight_actual: weightActual,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: "",
    thesis_ids: [],
    category: "",
    pm_notes: "",
    stats: {},
  };
}

/** STUB_NAV_ROWS already match the client's snake_case row shape. */
const CLIENT_NAV_ROWS = STUB_NAV_ROWS.map((r) => ({
  date: r.date,
  nav: r.nav,
  day_return_pct: r.day_return_pct,
  source: r.source,
  series_seam: r.series_seam,
}));

/** STUB_SNAPSHOT tip rows mapped onto the client continuity shape. */
const CLIENT_SNAPSHOT_ROWS = STUB_SNAPSHOT.navRows.map((r) => ({
  date: r.date,
  nav: r.nav,
  day_return_pct: r.dayReturnPct ?? null,
  source: r.source,
  series_seam: r.seriesSeam ?? null,
}));

describe("investedPct precedence (tip > book > metrics)", () => {
  it("GET /portfolio invested matches client resolveInvestedPct + definition", async () => {
    const { status, data } = await dataOf("/portfolio?retrieval_pin=v-1");
    expect(status).toBe(200);
    const invested = (data as unknown as { invested: Record<string, unknown> })["invested"];
    const heldSum = 5.0031 + 30.1269;
    const client = clientResolveInvestedPct({
      tipInvestedPct: 35.13,
      bookWeightInvestedPct: heldSum,
      metricsInvestedPct: null,
    });
    expect(invested["kpi_pct"]).toBe(client.investedPct);
    expect(invested["definition"]).toBe(client.definition);
    expect(invested["definition"]).toBe("accounting_nav_tip");
    expect(invested["envelope_pct"]).toBe(35.13);
  });

  it("server and client resolveInvestedPct agree over the precedence matrix", () => {
    const cases = [
      { tip: 35.13, book: 10, metrics: 80 }, // tip wins
      { tip: null, book: 35.13, metrics: 80 }, // book wins
      { tip: null, book: null, metrics: 80 }, // metrics wins
      { tip: null, book: null, metrics: null }, // unavailable
      { tip: -1, book: 35.13, metrics: null }, // negative tip falls through
      { tip: undefined, book: undefined, metrics: undefined },
    ];
    for (const c of cases) {
      const args = {
        tipInvestedPct: c.tip ?? null,
        bookWeightInvestedPct: c.book ?? null,
        metricsInvestedPct: c.metrics ?? null,
      };
      expect(serverResolveInvestedPct(args)).toEqual(clientResolveInvestedPct(args));
    }
  });

  it("GET /allocations invested_pct + scaled rows match client reconcileBook", async () => {
    const { status, data } = await dataOf("/allocations");
    expect(status).toBe(200);
    const body = data as unknown as {
      invested_pct: number;
      rows: Array<{ ticker: string; scaled_weight_pct: number }>;
    };
    expect(body.invested_pct).toBeCloseTo(35.13, 8);
    const client = clientReconcileBook(
      [clientPosition("DBO", 5.0031), clientPosition("XLV", 30.1269)],
      { investedPct: 35.13 },
    );
    expect(client.investedPct).toBeCloseTo(body.invested_pct, 8);
    for (const row of body.rows) {
      const peer = client.rows.find((r) => r.ticker === row.ticker);
      expect(peer).toBeDefined();
      expect(row.scaled_weight_pct).toBeCloseTo(peer!.normalizedWeight, 8);
    }
  });
});

describe("seam chaining (seam guard, continuity, 25% cap)", () => {
  it("GET /nav-series point contracts match client navRowContractLabel", async () => {
    const { status, data } = await dataOf("/nav-series");
    expect(status).toBe(200);
    const body = data as unknown as {
      tip: { date: string; contract: string };
      points: Array<{ date: string; contract: string; index: number }>;
    };
    expect(body.points).toHaveLength(1);
    expect(body.points[0].contract).toBe(
      clientNavRowContractLabel({ source: "legacy_nav_history", contract: "legacy_estimate" }),
    );
    const chained = clientChainNavContinuity(CLIENT_SNAPSHOT_ROWS);
    expect(body.points[0].index).toBeCloseTo(chained[0].nav, 8);
  });

  it("server and client seam predicates agree (flag, flip, null-prior)", () => {
    const pairs: Array<{ serverTip: { source?: string | null; seriesSeam?: boolean | null }; serverPrior: { source?: string | null } | null; clientTip: { source?: string | null; series_seam?: boolean | null }; clientPrior: { source?: string | null } | null }> = [
      {
        serverTip: { source: "legacy_nav_history" },
        serverPrior: { source: "legacy_nav_history" },
        clientTip: { source: "legacy_nav_history" },
        clientPrior: { source: "legacy_nav_history" },
      },
      {
        serverTip: { source: "finalized_accounting", seriesSeam: true },
        serverPrior: { source: "legacy_nav_history" },
        clientTip: { source: "finalized_accounting", series_seam: true },
        clientPrior: { source: "legacy_nav_history" },
      },
      {
        serverTip: { source: "finalized_accounting" },
        serverPrior: { source: "legacy_nav_history" },
        clientTip: { source: "finalized_accounting" },
        clientPrior: { source: "legacy_nav_history" },
      },
      {
        serverTip: { source: "legacy_nav_history" },
        serverPrior: null,
        clientTip: { source: "legacy_nav_history" },
        clientPrior: null,
      },
    ];
    for (const p of pairs) {
      expect(serverCrossesNavSeam(p.serverTip, p.serverPrior)).toBe(
        clientCrossesNavSeam(p.clientTip as never, p.clientPrior as never),
      );
      expect(serverIsNavSeriesSeam(p.serverTip, p.serverPrior?.source ?? null)).toBe(
        clientIsNavSeriesSeam(p.clientTip, p.clientPrior?.source ?? null),
      );
    }
  });

  it("server and client continuity steps agree (stored, derived, seam-flat, 25% cap)", () => {
    const rows: Array<{ server: { date: string; nav: number; dayReturnPct?: number | null; source?: string | null; seriesSeam?: boolean | null }; client: { date: string; nav: number; day_return_pct?: number | null; source?: string | null; series_seam?: boolean | null } }> = [
      // Stored daily return wins on both sides.
      {
        server: { date: "2026-08-21", nav: 102, dayReturnPct: 2, source: "legacy_nav_history" },
        client: { date: "2026-08-21", nav: 102, day_return_pct: 2, source: "legacy_nav_history" },
      },
      // Derived from levels within a run.
      {
        server: { date: "2026-08-21", nav: 102, source: "legacy_nav_history" },
        client: { date: "2026-08-21", nav: 102, source: "legacy_nav_history" },
      },
      // Seam row with no day return carries flat.
      {
        server: { date: "2026-08-26", nav: 200, source: "finalized_accounting", seriesSeam: true },
        client: { date: "2026-08-26", nav: 200, source: "finalized_accounting", series_seam: true },
      },
      // Implausible step (basis/funding artifact) carries flat at the 25% cap.
      {
        server: { date: "2026-08-27", nav: 200, source: "legacy_nav_history" },
        client: { date: "2026-08-27", nav: 200, source: "legacy_nav_history" },
      },
    ];
    const prevServer = { date: "2026-08-20", nav: 100, source: "legacy_nav_history" as const };
    const prevClient = { date: "2026-08-20", nav: 100, source: "legacy_nav_history" as const };
    const capPrevServer = { date: "2026-08-26", nav: 100, source: "legacy_nav_history" as const };
    const capPrevClient = { date: "2026-08-26", nav: 100, source: "legacy_nav_history" as const };
    expect(serverNavContinuityStepPct(rows[0].server, prevServer)).toBe(
      clientNavContinuityStepPct(rows[0].client, prevClient),
    );
    expect(serverNavContinuityStepPct(rows[1].server, prevServer)).toBe(
      clientNavContinuityStepPct(rows[1].client, prevClient),
    );
    expect(serverNavContinuityStepPct(rows[2].server, prevServer)).toBe(0);
    expect(clientNavContinuityStepPct(rows[2].client, prevClient)).toBe(0);
    expect(serverNavContinuityStepPct(rows[3].server, capPrevServer)).toBe(0);
    expect(clientNavContinuityStepPct(rows[3].client, capPrevClient)).toBe(0);
  });

  it("GET /performance continuity index matches client chainNavContinuity", async () => {
    const { status, data } = await dataOf("/performance");
    expect(status).toBe(200);
    const body = data as unknown as {
      nav: { points: Array<{ date: string; index: number }> };
    };
    const chained = clientChainNavContinuity(CLIENT_NAV_ROWS);
    const chainByDate = new Map(chained.map((c) => [c.date, c.nav]));
    // The server forward-fills calendar gaps ≤ 4 days flat (contract §6.4):
    // every plotted point carries the client chain value at its date, or the
    // previous chain value on filled days — never an interpolated return.
    let lastChain = chained[0].nav;
    for (const p of body.nav.points) {
      const expected = chainByDate.get(p.date) ?? lastChain;
      // Precision 6: the route rounds plotted points to 6dp.
      expect(p.index).toBeCloseTo(expected, 6);
      lastChain = expected;
    }
    expect(body.nav.points.at(-1)!.index).toBeCloseTo(chained.at(-1)!.nav, 6);
    // The 08-22 → 08-26 seam basis change carries flat: no phantom jump.
    const byDate = new Map(body.nav.points.map((p) => [p.date, p.index]));
    expect(byDate.get("2026-08-26")).toBeCloseTo(byDate.get("2026-08-22")!, 8);
  });

  it("server and client chainNavContinuity agree outright", () => {
    const serverMapped = CLIENT_NAV_ROWS.map((r) => ({
      date: r.date,
      nav: r.nav,
      dayReturnPct: r.day_return_pct,
      source: r.source,
      seriesSeam: r.series_seam,
    }));
    const server = serverChainNavContinuity(serverMapped);
    const client = clientChainNavContinuity(CLIENT_NAV_ROWS);
    expect(server.map((p) => p.date)).toEqual(client.map((p) => p.date));
    for (const [i, p] of server.entries()) {
      expect(p.index).toBeCloseTo(client[i].nav, 10);
    }
  });
});

describe("persisted-vs-live split (overlay only when badged)", () => {
  it("GET /brief overlay-off matches client persisted headlines + badge", async () => {
    const { status, data } = await dataOf("/brief?overlay=off");
    expect(status).toBe(200);
    const body = data as unknown as {
      book_as_of: string;
      day_return_pct: number | null;
      since_inception_pct: number | null;
      invested_pct: number | null;
      overlay: { active: boolean; live_vs_mark_pct: number; badge: string };
    };
    const client = clientPersistedHeadlines(CLIENT_NAV_ROWS, {
      bookWeightInvestedPct: 35.13,
      metricsInvestedPct: 80,
    });
    expect(body.book_as_of).toBe("2026-08-28");
    expect(body.overlay.active).toBe(false);
    expect(body.overlay.badge).toBe(clientNavContractBadgeLabel("finalized_accounting"));
    expect(body.day_return_pct).toBeCloseTo(client.dayReturnPct!, 10);
    expect(body.since_inception_pct).toBeCloseTo(client.sinceInceptionPct!, 10);
    expect(body.invested_pct).toBe(client.investedPct);
  });

  it("overlay-off brief matches the tearsheet headline within 0.05pp", async () => {
    const brief = (await dataOf("/brief?overlay=off")).data as unknown as {
      since_inception_pct: number | null;
    };
    const perf = (await dataOf("/performance")).data as unknown as {
      metrics: { since_inception_pct: number | null };
    };
    expect(
      Math.abs(brief.since_inception_pct! - perf.metrics.since_inception_pct!),
    ).toBeLessThanOrEqual(CLIENT_PERSISTED_TOLERANCE_PP);
  });

  it("server and client isLiveMarksOverlay agree (overlay only when badged)", () => {
    for (const v of [-0.5, -1e-10, 0, 1e-10, 0.4, null, undefined]) {
      expect(serverIsLiveMarksOverlay(v)).toBe(clientIsLiveMarksOverlay(v));
    }
    expect(clientIsLiveMarksOverlay(0.4)).toBe(true);
    expect(clientIsLiveMarksOverlay(0)).toBe(false);
  });

  it("GET /brief session_events match client selectBriefLedgerDayEvents", async () => {
    const { status, data } = await dataOf("/brief?overlay=off");
    expect(status).toBe(200);
    const body = data as unknown as {
      book_as_of: string;
      session_events: Array<{ date: string; ticker: string; event: string }>;
    };
    const client = clientSelectBriefDayEvents(
      [
        {
          date: "2026-08-28",
          ticker: "XLV",
          event: "TRIM",
          weight_pct: 4.9,
          prev_weight_pct: 9.9,
          weight_change_pct: null,
          price: null,
          thesis_id: null,
          reason: null,
        },
      ],
      body.book_as_of,
    );
    expect(body.session_events).toHaveLength(client.length);
    expect(body.session_events[0].ticker).toBe(client[0].ticker);
    expect(body.session_events[0].date).toBe(client[0].date);
  });

  it("alpha/IR stay null below the overlap floor on both sides", async () => {
    const { data } = await dataOf("/performance");
    const body = data as unknown as {
      metrics: { alpha_pct: unknown; information_ratio: unknown; beta: unknown };
    };
    expect(body.metrics.alpha_pct).toBeNull();
    expect(body.metrics.information_ratio).toBeNull();
    expect(body.metrics.beta).toBeNull();
    const client = clientPersistedInsights(CLIENT_NAV_ROWS, STUB_SPY6);
    expect(client.alphaPct).toBeNull();
    expect(client.informationRatio).toBeNull();
  });
});

describe("ledger economics (avg_entry / sold_weight / realized_return)", () => {
  // Fixture inputs quoted from the stub module's documented doubles
  // (src/stubs.ts header); every expected value below comes from a client fn.
  const marks = [
    { date: "2026-08-01", ticker: "XLF", entry_price: 52.0 },
    { date: "2026-07-15", ticker: "GLD", entry_price: 190 },
  ];

  it("GET /ledger TRIM economics match client ledgerEventEconomics", async () => {
    const { status, data } = await dataOf("/ledger");
    expect(status).toBe(200);
    const body = data as unknown as {
      events: Array<{
        date: string;
        ticker: string;
        type: string;
        fill_price: number | null;
        avg_entry: number | null;
        realized_pct: number | null;
      }>;
    };
    const trim = body.events.find((e) => e.ticker === "XLF" && e.type === "TRIM")!;
    expect(trim).toBeDefined();
    const client = clientLedgerEventEconomics(
      {
        event: "TRIM",
        ticker: "XLF",
        date: "2026-09-03",
        weight_pct: 4.9,
        prev_weight_pct: 9.9,
        price: 54.1,
      },
      marks,
    );
    expect(trim.fill_price).toBe(client.fillPrice);
    expect(trim.avg_entry).toBe(client.avgEntryPrice);
    expect(trim.realized_pct).toBe(client.realizedReturnPct);
    expect(trim.avg_entry).toBe(52.0);
  });

  it("GET /ledger OPEN with a post-event mark fails closed to fill (client agrees)", async () => {
    const { data } = await dataOf("/ledger");
    const body = data as unknown as {
      events: Array<{ ticker: string; type: string; avg_entry: number | null }>;
    };
    const open = body.events.find((e) => e.ticker === "GLD" && e.type === "OPEN")!;
    const client = clientLedgerEventEconomics(
      {
        event: "OPEN",
        ticker: "GLD",
        date: "2026-06-01",
        weight_pct: 10,
        prev_weight_pct: 0,
        price: 180,
      },
      marks,
    );
    expect(open.avg_entry).toBe(client.avgEntryPrice);
    expect(open.avg_entry).toBe(180);
  });

  it("server and client economics helpers agree over the matrix", () => {
    expect(serverAverageEntryAsOf(marks, "XLF", "2026-09-03")).toBe(
      clientAverageEntryAsOf(marks, "XLF", "2026-09-03"),
    );
    expect(serverAverageEntryAsOf(marks, "GLD", "2026-06-01")).toBe(
      clientAverageEntryAsOf(marks, "GLD", "2026-06-01"),
    );
    expect(serverAverageEntryAsOf(marks, "xlf", "2026-09-03")).toBe(52.0);
    expect(serverSoldWeightPct({ event: "TRIM", weight_pct: 4.9, prev_weight_pct: 9.9 })).toBe(
      clientSoldWeightPct({ event: "TRIM", weight_pct: 4.9, prev_weight_pct: 9.9, price: 54.1 }),
    );
    expect(serverSoldWeightPct({ event: "EXIT", weight_pct: null, prev_weight_pct: 10 })).toBe(
      clientSoldWeightPct({ event: "EXIT", weight_pct: null, prev_weight_pct: 10, price: 50 }),
    );
    expect(serverSoldWeightPct({ event: "OPEN", weight_pct: 10, prev_weight_pct: 0 })).toBe(
      clientSoldWeightPct({ event: "OPEN", weight_pct: 10, prev_weight_pct: 0, price: 180 }),
    );
    expect(serverRealizedReturn(54.1, 52.0)).toBe(clientRealizedReturn(54.1, 52.0));
    expect(serverRealizedReturn(null, 52.0)).toBeNull();
    expect(clientRealizedReturn(54.1, null)).toBeNull();
    const economics = serverLedgerEventEconomics(
      {
        event: "TRIM",
        ticker: "XLF",
        date: "2026-09-03",
        weight_pct: 4.9,
        prev_weight_pct: 9.9,
        price: 54.1,
      },
      marks,
    );
    expect(economics.soldWeightPct).toBe(
      clientSoldWeightPct({ event: "TRIM", weight_pct: 4.9, prev_weight_pct: 9.9, price: 54.1 }),
    );
  });
});

describe("live snapshot + benchmarks + envelope invariants", () => {
  it("GET /kpis/live live_vs_mark_pct matches the real client move math", async () => {
    const { status, data } = await dataOf("/kpis/live");
    expect(status).toBe(200);
    const body = data as unknown as {
      live_vs_mark_pct: number;
      overlay_eligible: boolean;
      universe: string[];
      quote_date: string | null;
    };
    const book = await stubLiveDeps().loadLiveBook();
    const clientMove = clientComputeLiveVsMarkPct(book!.positions);
    expect(body.live_vs_mark_pct).toBe(clientMove);
    expect(body.live_vs_mark_pct).toBeCloseTo(0.2, 10);
    expect(body.overlay_eligible).toBe(
      clientIsLiveMarksOverlay(clientMove) &&
        book!.positions.some((p) => (p.markPrice ?? 0) > 0),
    );
    expect(body.universe).toEqual(["DBO", "XLV"]);
    expect(body.quote_date).toBe("2026-08-28");
  });

  it("GET /benchmarks universe/overlap match stub NAV dates + client floor", async () => {
    const { status, data } = await dataOf("/benchmarks?tickers=SPY");
    expect(status).toBe(200);
    const body = data as unknown as {
      universe: string[];
      aligned_start: string | null;
      overlap_days: number;
    };
    expect(body.universe).toEqual(clientSortTickerUniverse(["SPY"]));
    expect(body.aligned_start).toBe("2026-08-20");
    expect(body.overlap_days).toBe(6);
    expect(serverOverlapMeetsFloor(body.overlap_days)).toBe(
      body.overlap_days >= CLIENT_MIN_OVERLAP_DAYS,
    );
  });

  it("every route group carries the §1 envelope + pin echo", async () => {
    for (const path of [
      "/portfolio",
      "/allocations",
      "/nav-series",
      "/brief?overlay=off",
      "/performance",
      "/kpis/live",
      "/benchmarks?tickers=SPY",
      "/ledger",
    ]) {
      const res = await app.fetch(get(`${path}${path.includes("?") ? "&" : "?"}retrieval_pin=v-pin`), NO_ENV);
      expect(res.status).toBe(200);
      const body = (await res.json()) as Record<string, unknown>;
      expect(body).toHaveProperty("data");
      expect(body).toHaveProperty("as_of");
      expect(body["retrieval_pin"]).toBe("v-pin");
      expect(body).toHaveProperty("provenance");
    }
    const health = await app.fetch(get("/healthz"), NO_ENV);
    expect(health.status).toBe(200);
  });
});
