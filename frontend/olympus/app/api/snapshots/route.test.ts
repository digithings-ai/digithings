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
});
