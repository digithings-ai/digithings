import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const ENV: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1",
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};
const FREE: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", ...ENV, DASHBOARD_DEV_CALLER: undefined };

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

  it("graph reads the latest node_runs run by started_at", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      return url.includes("node_runs")
        ? [
            { run_id: "r2", node_name: "research", outcome: "succeeded", started_at: "2026-09-02T09:00:00Z" },
            { run_id: "r2", node_name: "ingest", outcome: "succeeded", started_at: "2026-09-02T08:00:00Z" },
            { run_id: "r1", node_name: "decide", outcome: "failed", started_at: "2026-09-01T08:00:00Z" },
          ]
        : [];
    });
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/graph"), ENV);
    const body = (await res.json()) as { data: { run_date: string; nodes: { id: string; state: string | null }[] } };
    expect(urls.find((u) => u.includes("node_runs")) ?? "").toContain("order=started_at.desc");
    expect(body.data.run_date).toBe("2026-09-02");
    expect(Object.fromEntries(body.data.nodes.map((n) => [n.id, n.state]))).toEqual({ ingest: "succeeded", research: "succeeded", decide: null, publish: null });
  });

  it("trace maps run_event_trace columns for the latest run", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      return url.includes("run_event_trace")
        ? [
            { run_id: "r2", run_date: "2026-09-02", name: "atlas.publish", status: "ok", duration_ms: 1500, created_at: "2026-09-02T09:00:00Z" },
            { run_id: "r1", run_date: "2026-09-01", name: "old", status: "ok", duration_ms: 10, created_at: "2026-09-01T09:00:00Z" },
          ]
        : [];
    });
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/trace"), ENV);
    const body = (await res.json()) as { data: { rows: { node: string; duration_s: number; calls: null; state: string }[] }; as_of: string };
    expect(body.data.rows).toEqual([{ node: "atlas.publish", calls: null, duration_s: 1.5, state: "ok" }]);
    expect(body.as_of).toBe("2026-09-02");
    expect(urls.find((u) => u.includes("run_event_trace")) ?? "").toContain("order=created_at.desc");
  });

  it("trace picks the latest run by created_at, not by per-run sequence, when two runs share a run_date", async () => {
    mockFetch((url) => (url.includes("run_event_trace")
      ? [
          // Rows arrive as the API's own order=created_at.desc would return them: r_new
          // (later created_at) first, even though r_old has the higher per-run sequence.
          // Ordering by sequence instead of created_at would wrongly surface r_old as "latest".
          { run_id: "r_new", run_date: "2026-09-02", name: "new.step1", status: "ok", duration_ms: 20, sequence: 1, created_at: "2026-09-02T10:00:00Z" },
          { run_id: "r_old", run_date: "2026-09-02", name: "old.step1", status: "ok", duration_ms: 10, sequence: 5, created_at: "2026-09-02T01:00:00Z" },
        ]
      : []));
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/trace"), ENV);
    const body = (await res.json()) as { data: { rows: { node: string }[] } };
    expect(body.data.rows).toEqual([{ node: "new.step1", calls: null, duration_s: 0.02, state: "ok" }]);
  });

  it("trace does not mix a retry's rows into the latest attempt of the same run_id", async () => {
    mockFetch((url) => (url.includes("run_event_trace")
      ? [
          // Same run_id, two attempts (a retry): rows must be pinned to attempt 2, not
          // just run_id, or attempt 1's rows would leak into the trace.
          { run_id: "r1", attempt: 2, run_date: "2026-09-02", name: "retry.step1", status: "ok", duration_ms: 20, created_at: "2026-09-02T10:00:00Z" },
          { run_id: "r1", attempt: 1, run_date: "2026-09-02", name: "first.step1", status: "failed", duration_ms: 10, created_at: "2026-09-02T09:00:00Z" },
        ]
      : []));
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/trace"), ENV);
    const body = (await res.json()) as { data: { rows: { node: string }[] } };
    expect(body.data.rows).toEqual([{ node: "retry.step1", calls: null, duration_s: 0.02, state: "ok" }]);
  });

  it("narrative is the house Daily Digest split into paragraphs", async () => {
    const urls: string[] = [];
    mockFetch((url) => {
      urls.push(url);
      return url.includes("/documents?") ? [{ date: "2026-09-02", title: "Digest", content: "One.\n\nTwo." }] : [];
    });
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/narrative"), ENV);
    const body = (await res.json()) as { data: { heading: string; paragraphs: string[]; run_date: string } };
    expect(body.data).toEqual({ run_date: "2026-09-02", heading: "Digest", paragraphs: ["One.", "Two."] });
    const q = decodeURIComponent(urls[0] ?? "");
    expect(q).toContain("workspace_id=eq.");
    expect(q).toContain("doc_type=eq.Daily Digest");
  });

  it("rejects a bad date query", async () => {
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest/health?date=yesterday"), ENV);
    expect(res.status).toBe(400);
  });
});
