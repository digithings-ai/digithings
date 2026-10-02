import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const ENV: Env = {
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};
const FREE: Env = { ...ENV, DASHBOARD_DEV_CALLER: undefined };

function mockFetch(handler: (url: string) => unknown | { status: number }): void {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const out = handler(String(url));
    if (out && typeof out === "object" && "status" in out && !Array.isArray(out)) {
      return Response.json({ message: "missing" }, { status: (out as { status: number }).status });
    }
    return Response.json(out);
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("phase 2 pipeline routes", () => {
  it("health maps run_health and leaves cost null", async () => {
    mockFetch((url) => (url.includes("run_health") ? [{ run_date: "2026-09-01", run_type: "daily", status: "ok", model: "m", segments_ok: 4, segments_carried: 1, segments_failed: 0, est_cost_usd: 12 }] : []));
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/health"), ENV);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { data: { cost_usd: null; tokens_in: null; nodes: { ok: number } }; provenance: { source: string } };
    expect(body.data.cost_usd).toBeNull();
    expect(body.data.tokens_in).toBeNull();
    expect(body.data.nodes.ok).toBe(4);
    expect(body.provenance.source).toBe("core:run_health");
  });

  it("free can read health and cannot read trace", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/pipeline/runs/latest/health"), FREE)).status).toBe(200);
    expect((await app.fetch(new Request("https://x/pipeline/runs/latest/trace"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/pipeline/runs/latest/trace", { headers: { "x-digi-tier": "brief" } }), FREE)).status).toBe(200);
  });

  it("graph stays the static stages when node_runs is missing", async () => {
    mockFetch((url) => (url.includes("node_runs") ? { status: 404 } : []));
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/graph", { headers: { "x-digi-tier": "brief" } }), FREE);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { data: { nodes: { id: string; state: null }[] }; provenance: { marks: string } };
    expect(body.data.nodes.map((n) => n.id)).toEqual(["ingest", "research", "decide", "publish"]);
    expect(body.data.nodes.every((n) => n.state === null)).toBe(true);
    expect(body.provenance.marks).toBe("unavailable");
  });

  it("rejects a bad date query", async () => {
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/health?date=yesterday"), ENV);
    expect(res.status).toBe(400);
  });
});
