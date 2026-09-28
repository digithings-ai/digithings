import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";
import { mockAuthCtx } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/db", () => ({
  getDb: vi.fn(),
}));

vi.mock("@/lib/conversations-repo", () => ({
  tenantIdBySlug: vi.fn(),
  listQuantRuns: vi.fn(),
  insertQuantRun: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { getDb } from "@/db";
import { insertQuantRun, listQuantRuns, tenantIdBySlug } from "@/lib/conversations-repo";

const routeCtx = { params: Promise.resolve({ id: "conv-1" }) };
const db = {};

describe("/api/conversations/[id]/quant-runs", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
  });

  it("GET returns runs list", async () => {
    vi.mocked(listQuantRuns).mockResolvedValue([]);
    const res = await GET(
      new Request("http://localhost/api/conversations/conv-1/quant-runs"),
      routeCtx
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.runs).toEqual([]);
  });

  it("POST returns 400 for invalid body", async () => {
    const res = await POST(
      new Request("http://localhost/api/conversations/conv-1/quant-runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ strategyName: "sma" }),
      }),
      routeCtx
    );
    expect(res.status).toBe(400);
  });

  it("POST creates quant run", async () => {
    vi.mocked(insertQuantRun).mockResolvedValue("run-1");
    const res = await POST(
      new Request("http://localhost/api/conversations/conv-1/quant-runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          strategyName: "sma",
          symbols: ["AAPL"],
          backtestResult: { run_id: "r1", sharpe_ratio: 1.2 },
        }),
      }),
      routeCtx
    );
    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.id).toBe("run-1");
  });
});
