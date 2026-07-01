import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

vi.mock("@/db", () => ({
  getDb: vi.fn(),
}));

vi.mock("@/lib/ecosystem", () => ({
  getEcosystemEndpoints: vi.fn(),
}));

import { getDb } from "@/db";
import { getEcosystemEndpoints } from "@/lib/ecosystem";

describe("GET /api/health", () => {
  beforeEach(() => {
    vi.mocked(getEcosystemEndpoints).mockResolvedValue({
      digigraphUrl: "http://127.0.0.1:8000",
      digiquantUrl: "http://127.0.0.1:8001",
      digismithUrl: "http://127.0.0.1:8003",
      digisearchUrl: "",
    });
    vi.mocked(getDb).mockReturnValue(null);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200 })
    );
  });

  it("returns 200 when upstream health checks pass", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.checks.service).toBe("ok");
  });

  it("returns 503 when an upstream is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connection refused"))
    );
    const res = await GET();
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.ok).toBe(false);
  });
});
