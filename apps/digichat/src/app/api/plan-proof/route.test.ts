import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { POST } from "./route";

vi.mock("@/lib/embed-chat-tenant", () => ({
  resolveVerifiedEmbedTenant: vi.fn(),
}));

import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";

const PLAN_PROOF_SECRET = "test-api-secret-3662";
const SUPABASE_URL = "https://example.supabase.co";
const ANON_KEY = "test-anon-key";

function makeReq(
  headers: Record<string, string> = {},
  body: unknown = {},
): Request {
  return new Request("http://localhost/api/plan-proof", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

function mockSupabaseUser(planTier: string | null | undefined, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 401,
    json: async () =>
      ok
        ? {
            app_metadata:
              planTier === undefined
                ? {}
                : planTier === null
                  ? { plan_tier: null }
                  : { plan_tier: planTier },
          }
        : { message: "invalid" },
  });
}

describe("POST /api/plan-proof", () => {
  const env = process.env;

  beforeEach(() => {
    process.env = {
      ...env,
      DIGICHAT_PLAN_PROOF_SECRET: PLAN_PROOF_SECRET,
      DIGICHAT_DASHBOARD_SUPABASE_URL: SUPABASE_URL,
      DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY: ANON_KEY,
    };
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
    vi.unstubAllGlobals();
  });

  it("returns 401 when embed tenant is not verified", async () => {
    vi.mocked(resolveVerifiedEmbedTenant).mockReturnValue(null);
    const res = await POST(
      makeReq({ authorization: "Bearer sess-token" }),
    );
    expect(res.status).toBe(401);
  });

  it("returns 403 for non-digiquant-dashboard tenants", async () => {
    vi.mocked(resolveVerifiedEmbedTenant).mockReturnValue({
      slug: "other-tenant",
      gateMode: "ungated",
      theme: "dark",
      attribution: false,
      token: "tok",
      backend: { type: "digigraph" },
      activityDetail: "full",
    } as never);
    const res = await POST(
      makeReq({ authorization: "Bearer sess-token" }),
    );
    expect(res.status).toBe(403);
  });

  it("returns 401 when Authorization Bearer is missing", async () => {
    const res = await POST(makeReq({}, { tier: "desk" }));
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toBe("unauthorized");
  });

  it("returns 503 when DIGICHAT_PLAN_PROOF_SECRET is missing", async () => {
    delete process.env.DIGICHAT_PLAN_PROOF_SECRET;
    const res = await POST(
      makeReq({ authorization: "Bearer sess-token" }),
    );
    expect(res.status).toBe(503);
  });

  it("returns 503 when dashboard supabase url/anon key missing", async () => {
    delete process.env.DIGICHAT_DASHBOARD_SUPABASE_URL;
    const res = await POST(
      makeReq({ authorization: "Bearer sess-token" }),
    );
    expect(res.status).toBe(503);
  });

  it("returns 403 when supabase user has free/brief claims", async () => {
    for (const tier of ["free", "brief"]) {
      vi.stubGlobal("fetch", mockSupabaseUser(tier));
      const res = await POST(
        makeReq({ authorization: "Bearer sess-token" }, { tier: "desk" }),
      );
      expect(res.status).toBe(403);
      const body = await res.json();
      expect(body.error).toBe("plan_tier_required");
    }
  });

  it("returns 403 when body.tier spoofs desk but claims are brief", async () => {
    vi.stubGlobal("fetch", mockSupabaseUser("brief"));
    const res = await POST(
      makeReq({ authorization: "Bearer sess-token" }, { tier: "desk" }),
    );
    expect(res.status).toBe(403);
  });

  it("returns 403 when supabase auth rejects the token", async () => {
    vi.stubGlobal("fetch", mockSupabaseUser("desk", false));
    const res = await POST(
      makeReq({ authorization: "Bearer bad-token" }),
    );
    expect(res.status).toBe(403);
  });

  it("returns 403 when app_metadata.plan_tier is missing", async () => {
    vi.stubGlobal("fetch", mockSupabaseUser(undefined));
    const res = await POST(
      makeReq({ authorization: "Bearer sess-token" }, { tier: "desk" }),
    );
    expect(res.status).toBe(403);
  });

  it("mints a valid signed proof from desk claims (ignores body.tier)", async () => {
    const fetchMock = mockSupabaseUser("desk");
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(
      makeReq(
        { authorization: "Bearer sess-token" },
        { tier: "enterprise" }, // client spoof — must be ignored
      ),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      proof: string;
      exp: number;
      tier: string;
    };
    expect(body.tier).toBe("desk");
    expect(body.proof).toBeTruthy();
    expect(body.exp).toBeGreaterThan(Date.now());

    const { verifyPlanProof } = await import("@/lib/plan-proof");
    expect(verifyPlanProof(body.proof, PLAN_PROOF_SECRET)).toBe("desk");

    expect(fetchMock).toHaveBeenCalledWith(
      `${SUPABASE_URL}/auth/v1/user`,
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer sess-token",
          apikey: ANON_KEY,
        }),
      }),
    );
  });

  it("mints proofs for studio and enterprise claims", async () => {
    for (const tier of ["studio", "enterprise"]) {
      vi.stubGlobal("fetch", mockSupabaseUser(tier));
      const res = await POST(
        makeReq({ authorization: "Bearer sess-token" }),
      );
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof: string; tier: string };
      expect(body.tier).toBe(tier);
      const { verifyPlanProof } = await import("@/lib/plan-proof");
      expect(verifyPlanProof(body.proof, PLAN_PROOF_SECRET)).toBe(tier);
    }
  });

  it("returns 403 plan_tier_required for a free fx_hub grant with no desk floor (#4305)", async () => {
    const jsonResponse = (payload: unknown, status = 200) =>
      ({
        ok: status >= 200 && status < 300,
        status,
        json: async () => payload,
      }) as unknown as Response;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/v1/user")) {
        return jsonResponse({ app_metadata: { plan_tier: "free" } });
      }
      if (url.includes("/rest/v1/rpc/my_access")) {
        return jsonResponse({ products: ["fx_hub"], effective_plan_tier: "free" });
      }
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(makeReq({ authorization: "Bearer sess-token" }));
    expect(res.status).toBe(403);
    const body = (await res.json()) as { error: string; proof?: string };
    expect(body.error).toBe("plan_tier_required");
    expect(body.proof).toBeUndefined();

    // The fallback consults my_access for the effective tier, but free is not
    // proof-eligible, so an fx_hub-only grant still cannot mint a proof.
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/rest/v1/rpc/my_access"),
      ),
    ).toBe(true);
  });

  it("mints a desk proof for a desk-floor invitee whose claims say free (#4305)", async () => {
    const jsonResponse = (payload: unknown, status = 200) =>
      ({
        ok: status >= 200 && status < 300,
        status,
        json: async () => payload,
      }) as unknown as Response;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/v1/user")) {
        return jsonResponse({ app_metadata: { plan_tier: "free" } });
      }
      if (url.includes("/rest/v1/rpc/my_access")) {
        return jsonResponse({ products: ["fx_hub"], effective_plan_tier: "desk" });
      }
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(makeReq({ authorization: "Bearer sess-token" }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { proof: string; tier: string };
    expect(body.tier).toBe("desk");
    const { verifyPlanProof } = await import("@/lib/plan-proof");
    expect(verifyPlanProof(body.proof, PLAN_PROOF_SECRET)).toBe("desk");
  });

  it("still returns 403 when free claims lack the fx_hub product grant", async () => {
    const jsonResponse = (payload: unknown, status = 200) =>
      ({
        ok: status >= 200 && status < 300,
        status,
        json: async () => payload,
      }) as unknown as Response;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/v1/user")) {
        return jsonResponse({ app_metadata: { plan_tier: "free" } });
      }
      if (url.includes("/rest/v1/rpc/my_access")) {
        return jsonResponse({ products: [], effective_plan_tier: "free" });
      }
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(makeReq({ authorization: "Bearer sess-token" }));
    expect(res.status).toBe(403);
  });
});
