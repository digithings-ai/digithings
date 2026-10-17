import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const CORE: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1",
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
  TWELVEX_SUPABASE_URL: "https://tx.supabase.co",
  TWELVEX_SUPABASE_SERVICE_KEY: "tx-key",
};
const NO_GROUP: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", ...CORE, DASHBOARD_DEV_CALLER: "enterprise" };

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
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      // Served newest first, as the query orders it.
      return url.includes("fx_intraday_observations") ? [{ ts: "2026-09-02T11:00:00Z", close: null }, { ts: "2026-09-02T10:00:00Z", close: 1.1 }] : [];
    });
    const res = await app.fetch(new Request("https://x/fx/pairs/EURUSD/path"), CORE);
    const body = (await res.json()) as { data: { points: { t: string; v: number | null }[] }; provenance: { source: string }; as_of: string };
    expect(body.provenance.source).toBe("core:fx_intraday_observations");
    expect(body.data.points.map((p) => p.t)).toEqual(["2026-09-02T10:00:00Z", "2026-09-02T11:00:00Z"]);
    expect(body.data.points[1].v).toBeNull();
    const q = decodeURIComponent(urls.find((u) => u.includes("fx_intraday_observations")) ?? "");
    expect(q).toContain("order=ts.desc");
    expect(q).toContain("interval=eq.1h");
    expect(q).toContain("source=eq.yahoo");
    const unknown = await app.fetch(new Request("https://x/fx/pairs/ZZZZZZ/path"), CORE);
    const empty = (await unknown.json()) as { data: { points: unknown[]; note: string } };
    expect(empty.data.points).toEqual([]);
    expect(empty.data.note).toContain("no core series");
  });

  it("flags, paper, and directives are typed empty until the draft tables exist", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const flags = await app.fetch(new Request("https://x/fx/flags/USDJPY"), CORE);
    const flagBody = (await flags.json()) as { data: { flagged: boolean | null; scope_note: string } };
    expect(flagBody.data.flagged).toBeNull();
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

  it("pairs and levels age on the snapshot run_date instead of dropping it", async () => {
    mockFetch((url) =>
      url.includes("fx_trade_ideas_snapshot")
        ? [
            { pair: "USD/JPY", direction: "long", run_date: "2026-09-02T06:00:00Z" },
            { pair: "EUR/USD", direction: "short", run_date: "2026-09-01" },
          ]
        : [],
    );
    const pairsRes = await app.fetch(new Request("https://x/fx/pairs"), CORE);
    const pairsBody = (await pairsRes.json()) as { as_of: string | null; provenance: { tip_date: string | null; marks: string } };
    expect(pairsBody.as_of).toBe("2026-09-02");
    expect(pairsBody.provenance.tip_date).toBe("2026-09-02");

    const levelsRes = await app.fetch(new Request("https://x/fx/levels"), CORE);
    const levelsBody = (await levelsRes.json()) as { as_of: string | null; provenance: { tip_date: string | null; marks: string } };
    expect(levelsBody.as_of).toBe("2026-09-02");
    expect(levelsBody.provenance.tip_date).toBe("2026-09-02");
  });

  it("pairs and levels report marks unavailable, because none are fetched", async () => {
    mockFetch((url) =>
      url.includes("fx_trade_ideas_snapshot") ? [{ pair: "USD/JPY", direction: "long", run_date: "2026-09-02" }] : [],
    );
    const pairsRes = await app.fetch(new Request("https://x/fx/pairs"), CORE);
    const pairsBody = (await pairsRes.json()) as { provenance: { marks: string } };
    expect(pairsBody.provenance.marks).toBe("unavailable");

    const levelsRes = await app.fetch(new Request("https://x/fx/levels"), CORE);
    const levelsBody = (await levelsRes.json()) as { provenance: { marks: string } };
    expect(levelsBody.provenance.marks).toBe("unavailable");
  });

  it("pairs and levels send as_of null when the rows carry no run_date", async () => {
    mockFetch((url) =>
      url.includes("fx_trade_ideas_snapshot") ? [{ pair: "USD/JPY", direction: "long", run_date: null }] : [],
    );
    for (const path of ["/fx/pairs", "/fx/levels"]) {
      const body = (await (await app.fetch(new Request(`https://x${path}`), CORE)).json()) as { as_of: string | null };
      expect(body.as_of).toBeNull();
    }
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
});
