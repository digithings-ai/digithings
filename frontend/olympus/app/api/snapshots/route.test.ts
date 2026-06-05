import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { GET } from "./route";

describe("GET /api/snapshots", () => {
  const env = process.env;

  beforeEach(() => {
    process.env = { ...env };
  });

  afterEach(() => {
    process.env = env;
    vi.restoreAllMocks();
  });

  it("returns 404 when BFF flag is off", async () => {
    delete process.env.OLYMPUS_USE_BFF;
    const res = await GET();
    expect(res.status).toBe(404);
  });

  it("returns 503 when BFF enabled but service role key missing", async () => {
    process.env.OLYMPUS_USE_BFF = "1";
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    const res = await GET();
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toBe("bff_misconfigured");
  });
});
