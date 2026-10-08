import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const ENV: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1",
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};
const FREE: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", SUPABASE_URL: "https://core.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "core-key" };

function mockFetch(handler: (url: string) => unknown): void {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => Response.json(handler(String(url)))));
}

afterEach(() => vi.unstubAllGlobals());

async function body(path: string, env: Env = ENV): Promise<Record<string, unknown>> {
  const res = await app.fetch(new Request(`https://x${path}`), env);
  return { status: res.status, ...(await res.json() as object) };
}

describe("phase 1 portfolio routes", () => {
  it("free caller is forbidden on brief routes; brief is not", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/attribution"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/theses/signals"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/ledger/cash"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/performance/drawdown"), FREE)).status).toBe(403);
    const brief = await app.fetch(new Request("https://x/attribution", { headers: { "x-digi-tier": "brief" } }), FREE);
    expect(brief.status).toBe(200);
  });

  it("theses envelope joins vehicles and does not invent evidence", async () => {
    mockFetch((url) => {
      // Real columns: uuid `id`, text `thesis_id`, daily `date` snapshots, upper-case `status`.
      if (url.includes("/theses?")) {
        return [
          { id: "00000000-0000-0000-0000-000000000001", thesis_id: "gold", date: "2026-09-02", name: "Gold", status: "ACTIVE", invalidation: "real yields up" },
          { id: "00000000-0000-0000-0000-000000000002", thesis_id: "rates", date: "2026-09-02", name: "Rates", status: "MONITORING" },
          { id: "00000000-0000-0000-0000-000000000003", thesis_id: "gold", date: "2026-09-01", name: "Gold", status: "ACTIVE" },
        ];
      }
      if (url.includes("/thesis_vehicles")) {
        return [
          { thesis_id: "gold", ticker: "GLD", date: "2026-09-02" },
          { thesis_id: "gold", ticker: "IAU", date: "2026-09-01" },
        ];
      }
      return [];
    });
    const res = await body("/theses");
    expect(res.status).toBe(200);
    const data = res.data as { theses: { id: string; vehicles: string[]; evidence: null; kill_condition: string | null }[]; counts: { active: number; watch: number } };
    expect(data.theses).toHaveLength(2);
    expect(data.theses[0]).toMatchObject({ id: "gold", vehicles: ["GLD"], evidence: null, kill_condition: "real yields up" });
    expect(data.counts).toMatchObject({ active: 1, watch: 1 });
    expect(res.provenance).toMatchObject({ source: "core:theses" });
  });

  it("signals keeps only challenged theses", async () => {
    mockFetch((url) => (url.includes("/theses?") ? [{ thesis_id: "a", date: "2026-09-02", status: "CHALLENGED", name: "A" }, { thesis_id: "b", date: "2026-09-02", status: "ACTIVE", name: "B" }] : []));
    const res = await body("/theses/signals", { ...ENV, DASHBOARD_DEV_CALLER: "brief" });
    const data = res.data as { theses: { id: string }[] };
    expect(data.theses.map((t) => t.id)).toEqual(["a"]);
  });

  it("drawdown is computed from NAV and stays null without a second point", async () => {
    mockFetch(() => [{ date: "2026-01-01", nav: 100 }, { date: "2026-01-03", nav: 80 }]);
    const res = await body("/performance/drawdown", { ...ENV, DASHBOARD_DEV_CALLER: "brief" });
    const data = res.data as { max_pct: number; current_pct: number; series: unknown[]; episodes: unknown[] };
    expect(data.max_pct).toBeCloseTo(-20);
    expect(data.current_pct).toBeCloseTo(-20);
    expect(data.series).toHaveLength(2);
    expect(data.episodes).toEqual([]);
  });

  it("enriched book joins a name and leaves an unknown sleeve null", async () => {
    mockFetch((url) => {
      if (url.includes("/positions?")) return [{ date: "2026-08-01", ticker: "GLD", weight_pct: 10, current_price: 2, shares: 3 }];
      if (url.includes("/instruments")) return [{ ticker: "GLD", name: "Gold", instrument_type: "nope" }];
      return [];
    });
    const res = await body("/allocations/enriched");
    const data = res.data as { rows: { name: string; sleeve: null; value: number }[]; book_value: number };
    expect(data.rows[0]).toMatchObject({ name: "Gold", sleeve: null, value: 6 });
    expect(data.book_value).toBe(6);
  });

  it("attribution serves the latest lookback date in basis points", async () => {
    mockFetch((url) => (url.includes("position_attribution")
      ? [
          { date: "2026-09-02", ticker: "GLD", sector_bucket: "Commodities", contribution_pct: 0.12, window_start_date: "2026-08-03", window_end_date: "2026-09-02", lookback_days: 21 },
          { date: "2026-09-02", ticker: "TLT", sector_bucket: "Rates", contribution_pct: -0.05, window_start_date: "2026-08-03", window_end_date: "2026-09-02", lookback_days: 21 },
          { date: "2026-09-01", ticker: "GLD", sector_bucket: "Commodities", contribution_pct: 9, window_start_date: "2026-08-02", window_end_date: "2026-09-01", lookback_days: 21 },
        ]
      : []));
    const res = await body("/attribution");
    const data = res.data as { window: { start: string; end: string }; basis: { lookback_days: number }; names: { contribution_bp: number }[]; sleeves: { sleeve: string; contribution_bp: number }[] };
    expect(data.window).toEqual({ start: "2026-08-03", end: "2026-09-02" });
    expect(data.basis.lookback_days).toBe(21);
    expect(data.names).toHaveLength(2);
    expect(data.sleeves.find((s) => s.sleeve === "Commodities")?.contribution_bp).toBeCloseTo(12);
  });

  it("ledger cash reads period_date and pins the house workspace", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      return url.includes("accounting_periods") ? [{ period_date: "2026-09-01", cash_contribution: 5, closing_cash: 100 }] : [];
    });
    const res = await body("/ledger/cash");
    const data = res.data as { entries: { date: string; amount: number; balance: number }[] };
    expect(data.entries[0]).toMatchObject({ date: "2026-09-01", amount: 5, balance: 100 });
    const q = urls.find((u) => u.includes("accounting_periods")) ?? "";
    expect(q).toContain("order=period_date.desc");
    expect(q).toContain("workspace_id=eq.");
  });

  it("brief decision reads stance, ticker, and thesis from decision_log", async () => {
    mockFetch((url) => (url.includes("decision_log") ? [{ run_date: "2026-09-02", ticker: "GLD", stance: "long", thesis: "Real yields roll over." }] : []));
    const res = await body("/brief/decision");
    const data = res.data as { decision: { lead: string; body: string; run_date: string } };
    expect(data.decision).toEqual({ lead: "long GLD", body: "Real yields roll over.", run_date: "2026-09-02" });
  });

  it("brief risks has no source and does not read documents", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await body("/brief/risks");
    expect(res.data).toEqual({ risks: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("dossier joins on thesis_id and scopes documents to the house", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      if (url.includes("/theses?")) return [{ id: "00000000-0000-0000-0000-000000000001", thesis_id: "gold", date: "2026-09-02", name: "Gold", status: "ACTIVE" }];
      if (url.includes("/thesis_vehicles")) return [{ thesis_id: "gold", ticker: "GLD", date: "2026-09-02" }];
      return [];
    });
    const res = await body("/dossier/gld");
    const data = res.data as { thesis: { id: string; state: string }; vehicles: string[] };
    expect(data.thesis).toMatchObject({ id: "gold", state: "active" });
    expect(data.vehicles).toEqual(["gold"]);
    expect(urls.find((u) => u.includes("/documents?")) ?? "").toContain("workspace_id=eq.");
  });

  it("dossier rejects a bad ticker and does not fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await app.fetch(new Request("https://x/dossier/.."), ENV);
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("unconfigured core fails closed", async () => {
    const res = await app.fetch(new Request("https://x/theses"), { DASHBOARD_DEV_CALLER: "enterprise+12x" });
    expect(res.status).toBe(502);
  });
});
