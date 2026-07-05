import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

  afterEach(() => {
    vi.unstubAllEnvs();
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

  it("skips digraph/digiquant/digismith checks and stays healthy when they're not in DIGICHAT_ENABLED_SERVICES (#external-relay-only deploy)", async () => {
    // "" falls back to the all-enabled default in capabilities.ts (raw || fallback),
    // so a non-matching placeholder is what actually disables every service.
    vi.stubEnv("DIGICHAT_ENABLED_SERVICES", "none");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connection refused"))
    );
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.checks.digraph).toBeUndefined();
    expect(body.checks.digiquant).toBeUndefined();
    expect(body.checks.digismith).toBeUndefined();
  });

  it("still requires digraph/digiquant/digismith when they are in DIGICHAT_ENABLED_SERVICES", async () => {
    vi.stubEnv("DIGICHAT_ENABLED_SERVICES", "digigraph,digiquant,digismith");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connection refused"))
    );
    const res = await GET();
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.ok).toBe(false);
    expect(body.checks.digraph).toBe("unreachable");
  });
});
