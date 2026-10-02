import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";
import { curvePoints, pickStrategy, tearsheetCard } from "./strategies";

const ENV: Env = {
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};
const BRIEF: Env = { ...ENV, DASHBOARD_DEV_CALLER: "brief" };
const FREE: Env = { SUPABASE_URL: "https://core.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "core-key" };

function mockFetch(handler: (url: string) => unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (url: string) => Response.json(handler(String(url))));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("phase 4 strategies", () => {
  it("brief may read the catalog; free may not; desk is required to deploy", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/strategies"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/strategies"), BRIEF)).status).toBe(200);
    expect((await app.fetch(new Request("https://x/strategies/deploy-flow"), BRIEF)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/strategies/deploy-flow"), { ...ENV, DASHBOARD_DEV_CALLER: "desk" })).status).toBe(200);
  });

  it("catalog maps store rows and does not invent cadence, targets, or a deploy state", async () => {
    const fetchMock = mockFetch((url) => (url.includes("/strategies?")
      ? [{ id: "ema", label: "EMA cross", engine: "nautilus", symbol: "BTC", enabled: true, updated_at: "2026-09-01T00:00:00Z" }]
      : []));
    const res = await app.fetch(new Request("https://x/strategies"), ENV);
    const body = (await res.json()) as { data: { strategies: { cadence: null; targets: null; deploy: null; family: string }[] }; provenance: { source: string } };
    expect(body.provenance.source).toBe("core:strategies");
    expect(body.data.strategies[0]).toMatchObject({ id: "ema", family: "nautilus", universe: "BTC", cadence: null, targets: null, deploy: null });
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("strategy_calibrations"))).toBe(false);
  });

  it("summary counts rows and leaves deployment figures null", async () => {
    mockFetch((url) => {
      if (url.includes("/strategies?")) return [{ id: "a", enabled: true }, { id: "b", enabled: false }];
      if (url.includes("/strategy_signals")) return [{ last_signal_date: "2026-08-02" }];
      return [];
    });
    const res = await app.fetch(new Request("https://x/strategies/summary"), ENV);
    const body = (await res.json()) as { data: { catalog: number; deployable: number; deployments: null; paper_accounts: null; last_run: string; notice: { tag: string } } };
    expect(body.data.catalog).toBe(2);
    expect(body.data.deployable).toBe(1);
    expect(body.data.deployments).toBeNull();
    expect(body.data.paper_accounts).toBeNull();
    expect(body.data.last_run).toBe("2026-08-02");
    expect(body.data.notice.tag).toBe("soon");
  });

  it("performance passes a dated curve and refuses a bare number series", async () => {
    expect(curvePoints([1, 2, 3])).toBeNull();
    expect(curvePoints([{ date: "2026-01-02", value: 1 }])).toEqual([{ date: "2026-01-02", value: 1 }]);
    mockFetch((url) => {
      if (url.includes("/strategies?")) return [{ id: "ema", enabled: true, label: "EMA" }];
      if (url.includes("strategy_tearsheets")) return [{ strategy_id: "ema", as_of: "2026-01-02", equity_curve: [10, 11] }];
      return [];
    });
    const res = await app.fetch(new Request("https://x/strategies/default/performance"), ENV);
    const body = (await res.json()) as { data: { available: boolean; reason: string; points: unknown[] } };
    expect(body.data.available).toBe(false);
    expect(body.data.points).toEqual([]);
    expect(body.data.reason).toContain("no dated curve");
    expect(body.data).toHaveProperty("card");
  });

  it("projects stored tearsheet metrics and leaves missing figures null", () => {
    const card = tearsheetCard(
      { id: "btc_slapper", label: "BTC L/S", symbol: "BTC" },
      { net_profit_pct: 12.5, max_drawdown_pct: -8, win_rate_pct: null, dca: { vs_lump_pct: 1.2 } },
    );
    expect(card).toMatchObject({
      id: "btc_slapper",
      name: "BTC L/S",
      net_profit_pct: 12.5,
      max_drawdown_pct: -8,
      win_rate_pct: null,
      profit_factor: null,
      vs_lump_pct: 1.2,
    });
    expect(tearsheetCard(null, {})).toBeNull();
  });

  it("deploy flow is coming soon and does not touch the database", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await app.fetch(new Request("https://x/strategies/deploy-flow"), ENV);
    const body = (await res.json()) as { data: { steps: { state: string }[] } };
    expect(res.status).toBe(200);
    expect(body.data.steps.every((s) => s.state === "todo")).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    const deps = await app.fetch(new Request("https://x/strategies/deployments"), ENV);
    const depBody = (await deps.json()) as { data: { deployments: unknown[]; empty_reason: string } };
    expect(depBody.data.deployments).toEqual([]);
    expect(depBody.data.empty_reason).toContain("no deployment");
  });

  it("parameters keep an object value unparsed", async () => {
    mockFetch(() => [{ id: "ema", enabled: true, config: { fast: 12, nest: { a: 1 } } }]);
    const res = await app.fetch(new Request("https://x/strategies/default/parameters"), ENV);
    const body = (await res.json()) as { data: { parameters: { name: string; value: unknown; state: string | null }[] } };
    expect(body.data.parameters).toEqual([
      { name: "fast", value: 12, state: null },
      { name: "nest", value: null, state: "unparsed" },
    ]);
  });

  it("picks an explicit id, else the first enabled id", () => {
    const rows = [{ id: "b", enabled: false }, { id: "a", enabled: true }];
    expect(pickStrategy(rows, null)?.id).toBe("a");
    expect(pickStrategy(rows, "b")?.id).toBe("b");
    expect(pickStrategy(rows, "missing")).toBeNull();
  });

  it("unconfigured core fails closed", async () => {
    const res = await app.fetch(new Request("https://x/strategies"), { DASHBOARD_DEV_CALLER: "enterprise" });
    expect(res.status).toBe(502);
  });
});
