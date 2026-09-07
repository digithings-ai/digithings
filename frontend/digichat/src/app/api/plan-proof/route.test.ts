import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { POST } from "./route";

vi.mock("@/lib/embed-chat-tenant", () => ({
  resolveVerifiedEmbedTenant: vi.fn(),
}));

import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";

const PLAN_PROOF_SECRET = "test-api-secret-3662";

function makeReq(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/plan-proof", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

describe("POST /api/plan-proof", () => {
  const env = process.env;

  beforeEach(() => {
    process.env = { ...env, DIGICHAT_PLAN_PROOF_SECRET: PLAN_PROOF_SECRET };
    vi.mocked(resolveVerifiedEmbedTenant).mockReturnValue({
      slug: "digiquant-dashboard",
      gateMode: "ungated",
      theme: "dark",
      attribution: false,
      token: "dash-secret",
      backend: { type: "digigraph" },
      activityDetail: "full",
    } as never);
  });

  afterEach(() => {
    process.env = env;
  });

  it("returns 401 when embed tenant is not verified", async () => {
    vi.mocked(resolveVerifiedEmbedTenant).mockReturnValue(null);
    const res = await POST(makeReq({ tier: "desk" }));
    expect(res.status).toBe(401);
  });

  it("returns 403 for non-digiquant-dashboard tenants", async () => {
    vi.mocked(resolveVerifiedEmbedTenant).mockReturnValue({
      slug: "other-tenant",
      gateMode: "ungated",
      theme: "dark",
      attribution: false,
      token: "tok",
      backend: { type: "digraph" },
      activityDetail: "full",
    } as never);
    const res = await POST(makeReq({ tier: "desk" }));
    expect(res.status).toBe(403);
  });

  it("returns 503 when DIGICHAT_PLAN_PROOF_SECRET is missing", async () => {
    delete process.env.DIGICHAT_PLAN_PROOF_SECRET;
    const res = await POST(makeReq({ tier: "desk" }));
    expect(res.status).toBe(503);
  });

  it("returns 400 for invalid JSON body", async () => {
    const req = new Request("http://localhost/api/plan-proof", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "not-json",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid tier", async () => {
    const res = await POST(makeReq({ tier: "premium" }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("invalid_tier");
  });

  it("returns 400 for missing tier", async () => {
    const res = await POST(makeReq({}));
    expect(res.status).toBe(400);
  });

  it("returns 400 for free/brief tier (not eligible for proof)", async () => {
    const res = await POST(makeReq({ tier: "free" }));
    expect(res.status).toBe(400);
  });

  it("mints a valid signed proof for desk", async () => {
    const res = await POST(makeReq({ tier: "desk" }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { proof: string; exp: number };
    expect(body.proof).toBeTruthy();
    expect(body.exp).toBeGreaterThan(Date.now());

    // Verify the proof is valid
    const { verifyPlanProof } = await import("@/lib/plan-proof");
    expect(verifyPlanProof(body.proof, PLAN_PROOF_SECRET)).toBe("desk");
  });

  it("mints proofs for studio and enterprise", async () => {
    for (const tier of ["studio", "enterprise"]) {
      const res = await POST(makeReq({ tier }));
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof: string };
      const { verifyPlanProof } = await import("@/lib/plan-proof");
      expect(verifyPlanProof(body.proof, PLAN_PROOF_SECRET)).toBe(tier);
    }
  });
});
