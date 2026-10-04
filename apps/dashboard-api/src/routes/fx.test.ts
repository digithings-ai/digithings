import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const CORE: Env = {
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
  TWELVEX_SUPABASE_URL: "https://tx.supabase.co",
  TWELVEX_SUPABASE_SERVICE_KEY: "tx-key",
};
const NO_GROUP: Env = { ...CORE, DASHBOARD_DEV_CALLER: "enterprise" };

function mockFetch(handler: (url: string) => unknown): void {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => Response.json(handler(String(url)))));
}

afterEach(() => vi.unstubAllGlobals());

describe("phase 3 fx and rates", () => {
  it("fx routes require the 12x group", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/fx/summary"), NO_GROUP)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/fx/summary", { headers: { "x-digi-tier": "free", "x-digi-groups": "12x" } }), NO_GROUP)).status).toBe(200);
  });

  it("summary counts ideas from rows and leaves paper exposure null", async () => {
    mockFetch((url) => {
      if (url.includes("fx_daily_digest")) return [{ run_date: "2026-09-02", summary: "Quiet", key_themes: ["USD"] }];
      if (url.includes("fx_trade_ideas_snapshot")) return [{ pair: "USD/JPY", run_date: "2026-09-02" }, { pair: "EUR/USD", run_date: "2026-09-02" }];
      return [];
    });
    const res = await app.fetch(new Request("https://x/fx/summary"), CORE);
    const body = (await res.json()) as { data: { ideas: { count: number }; paper_exposure: { gross_usd: null }; read: { lead: string } } };
    expect(body.data.ideas.count).toBe(2);
    expect(body.data.paper_exposure.gross_usd).toBeNull();
    expect(body.data.read.lead).toBe("Quiet");
  });

  it("pair path uses the core series id and does not invent a quote", async () => {
    mockFetch((url) => (url.includes("fx_intraday_observations") ? [{ ts: "2026-09-02T10:00:00Z", close: 1.1 }, { ts: "2026-09-02T11:00:00Z", close: null }] : []));
    const res = await app.fetch(new Request("https://x/fx/pairs/EURUSD/path"), CORE);
    const body = (await res.json()) as { data: { points: { v: number | null }[] }; provenance: { source: string } };
    expect(body.provenance.source).toBe("core:fx_intraday_observations");
    expect(body.data.points[1].v).toBeNull();
    const unknown = await app.fetch(new Request("https://x/fx/pairs/ZZZZZZ/path"), CORE);
    const empty = (await unknown.json()) as { data: { points: unknown[]; note: string } };
    expect(empty.data.points).toEqual([]);
    expect(empty.data.note).toContain("no core series");
  });

  it("flags, paper, and directives are typed empty until the draft tables exist", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const flags = await app.fetch(new Request("https://x/fx/flags/USDJPY"), CORE);
    const flagBody = (await flags.json()) as { data: { flagged: boolean; scope_note: string } };
    expect(flagBody.data.flagged).toBe(false);
    expect(flagBody.data.scope_note).toContain("not provisioned");
    const paper = await app.fetch(new Request("https://x/fx/paper-exposure"), CORE);
    const paperBody = (await paper.json()) as { data: { gross_usd: null; lines: unknown[] } };
    expect(paperBody.data.gross_usd).toBeNull();
    expect(paperBody.data.lines).toEqual([]);
    const put = await app.fetch(new Request("https://x/fx/directives", { method: "PUT", headers: { "x-digi-user": "u1" }, body: "{}" }), CORE);
    expect(put.status).toBe(503);
    expect(((await put.json()) as { error: { code: string } }).error.code).toBe("not_provisioned");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("curve reads FRED tenors and leaves a missing yield null", async () => {
    mockFetch((url) => (url.includes("macro_series_observations")
      ? [{ series_id: "DGS10", obs_date: "2026-09-02", value: "4.2", unit: "Percent" }, { series_id: "DGS10", obs_date: "2026-09-01", value: "4.1", unit: "Percent" }]
      : []));
    const res = await app.fetch(new Request("https://x/rates/curve"), CORE);
    const body = (await res.json()) as { data: { curve: { tenor: string; yield_pct: number | null; day_change: number | null }[] } };
    const ten = body.data.curve.find((c) => c.tenor === "10Y");
    const two = body.data.curve.find((c) => c.tenor === "2Y");
    expect(ten).toMatchObject({ yield_pct: 4.2 });
    expect(ten?.day_change).toBeCloseTo(0.1);
    expect(two?.yield_pct).toBeNull();
  });

  it("twelve-x missing fails closed on ideas", async () => {
    const res = await app.fetch(new Request("https://x/fx/ideas"), { ...CORE, TWELVEX_SUPABASE_URL: undefined, TWELVEX_SUPABASE_SERVICE_KEY: undefined });
    expect(res.status).toBe(502);
  });

  // DIG-354: the thesis book is core `theses`, dated by the business `date`.
  it("rates theses ages by date and keeps only the newest date", async () => {
    mockFetch((url) => {
      // `thesis_vehicles` must be matched first: it does not contain "theses".
      if (url.includes("thesis_vehicles")) return [
        { thesis_id: "t1", ticker: "EUR/USD", date: "2026-09-28" },
        { thesis_id: "t1", ticker: "GBP/USD", date: "2026-09-27" },
        { thesis_id: "t2", ticker: "USD/JPY", date: "2026-09-28" },
      ];
      if (url.includes("theses")) return [
        { id: "uuid-t1", thesis_id: "t1", name: "Front-end easing", status: "ACTIVE", date: "2026-09-28" },
        { id: "uuid-t1-old", thesis_id: "t1", name: "Front-end easing", status: "ACTIVE", date: "2026-09-27" },
        { id: "uuid-t2", thesis_id: "t2", name: "Carry", status: "CHALLENGED", date: "2026-09-28" },
        { id: "uuid-t3", thesis_id: "t3", name: "Older only", status: "ACTIVE", date: "2026-09-20" },
      ];
      return [];
    });
    const res = await app.fetch(new Request("https://x/rates/theses"), CORE);
    const body = (await res.json()) as {
      data: { theses: { id: string; state: string; vehicles: string[] }[]; counts: { active: number; watch: number; exited: number } };
      as_of: string | null;
      provenance: { source: string; tip_date: string | null };
    };
    expect(res.status).toBe(200);
    // `date` is the run; provenance names the core table it came from.
    expect(body.as_of).toBe("2026-09-28");
    expect(body.provenance.tip_date).toBe("2026-09-28");
    expect(body.provenance.source).toBe("core:theses");
    // One row per thesis per date: t1's older row and the tip-stale t3 are out.
    expect(body.data.theses.map((t) => t.id)).toEqual(["uuid-t1", "uuid-t2"]);
    // Vehicles join on thesis_id, never on the uuid — and only at the tip date.
    expect(body.data.theses[0].vehicles).toEqual(["EUR/USD"]);
    expect(body.data.theses[1].vehicles).toEqual(["USD/JPY"]);
    expect(body.data.counts).toEqual({ active: 1, watch: 0, exited: 0 });
    // Core uses CHALLENGED/MONITORING, which are not watch/exited and pass through.
    expect(body.data.theses[1].state).toBe("challenged");
  });

  // `updated_at` is a write timestamp, not a run, so it may never be the as_of
  // even though core `theses` carries the column.
  it("rates theses does not age by updated_at", async () => {
    mockFetch((url) => (url.includes("theses") && !url.includes("thesis_vehicles")
      ? [{ thesis_id: "t1", name: "Front-end easing", status: "ACTIVE", date: "2026-09-28", updated_at: "2026-10-03T04:05:06Z" }]
      : []));
    const res = await app.fetch(new Request("https://x/rates/theses"), CORE);
    const body = (await res.json()) as { as_of: string | null };
    expect(res.status).toBe(200);
    expect(body.as_of).toBe("2026-09-28");
  });

  // The house book has no `desk` column. A desk gate would either be dead code
  // or would label every house thesis as a rates thesis.
  it("rates theses has no desk gate and keeps unrecognised statuses", async () => {
    mockFetch((url) => (url.includes("theses") && !url.includes("thesis_vehicles")
      ? [{ thesis_id: "t1", name: "A", status: "MONITORING", date: "2026-09-28" }]
      : []));
    const res = await app.fetch(new Request("https://x/rates/theses"), CORE);
    const body = (await res.json()) as { data: { theses: { name: string; state: string }[]; counts: { watch: number } } };
    expect(res.status).toBe(200);
    expect(body.data.theses).toHaveLength(1);
    expect(body.data.theses[0].name).toBe("A");
    expect(body.data.counts.watch).toBe(0);
  });
});
