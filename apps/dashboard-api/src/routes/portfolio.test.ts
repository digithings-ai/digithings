import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const ENV: Env = {
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};
const FREE: Env = { SUPABASE_URL: "https://core.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "core-key" };

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
      if (url.includes("/theses?")) return [{ id: "t1", name: "Gold", state: "active" }];
      if (url.includes("/thesis_vehicles")) return [{ thesis_id: "t1", ticker: "GLD" }];
      return [];
    });
    const res = await body("/theses");
    expect(res.status).toBe(200);
    const data = res.data as { theses: { id: string; vehicles: string[]; evidence: null }[]; counts: { active: number } };
    expect(data.theses[0]).toMatchObject({ id: "t1", vehicles: ["GLD"], evidence: null });
    expect(data.counts.active).toBe(1);
    expect(res.provenance).toMatchObject({ source: "core:theses" });
  });

  // The test above uses `id: "t1"`, which coincides with `thesis_id` and so
  // cannot tell a working join from a dead one. Live core rows carry a uuid in
  // `id` and the text business key in `thesis_id`, and the vehicles lookup must
  // key on the latter: joined on `id`, it matched 0 of 3256 live rows.
  it("theses vehicles join on thesis_id, not the uuid id", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) return [
        { id: "fd49f84b-114b-4e73-ab87-f16939664f97", thesis_id: "gold-bid", name: "Gold", status: "ACTIVE" },
      ];
      if (url.includes("/thesis_vehicles")) return [{ thesis_id: "gold-bid", ticker: "GLD" }];
      return [];
    });
    const res = await body("/theses");
    expect(res.status).toBe(200);
    const data = res.data as { theses: { id: string; vehicles: string[] }[] };
    expect(data.theses[0].id).toBe("fd49f84b-114b-4e73-ab87-f16939664f97");
    expect(data.theses[0].vehicles).toEqual(["GLD"]);
  });

  it("signals keeps only needs_resolution rows", async () => {
    mockFetch((url) => (url.includes("/theses?") ? [{ id: "a", needs_resolution: true, name: "A" }, { id: "b", needs_resolution: false, name: "B" }] : []));
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
