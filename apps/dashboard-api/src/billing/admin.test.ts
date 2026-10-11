import { afterEach, describe, expect, it, vi } from "vitest";
import { createPostgrestAdmin, supabaseBase } from "./admin";

// The PostgREST layer is where a silent contract drift would hide: the route
// tests inject an AdminDb stub and never touch it, so nothing else in the
// suite proves that this implementation returns the SHAPE the routes read.
// Every test here drives the real object against a stubbed fetch.

// The admin factory validates URL + service key + anon key TOGETHER
// (admin.ts:109), so a partial env is not a fixture, it is a thrown error.
const ENV = {
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "service-key",
  SUPABASE_ANON_KEY: "anon-key",
};

const WORKSPACE = {
  id: "ws_1",
  stripe_customer_id: "cus_1",
  stripe_subscription_id: "sub_1",
  subscription_status: "active",
  plan_tier: "desk",
  claim_sync_pending: false,
  last_stripe_event_created: 10,
};

function jsonResponse(status: number, data: unknown) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Records every request URL so a test can assert on the query it built. */
function stubFetch(handler: (url: string) => Response) {
  const seen: string[] = [];
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const url = String(input);
    seen.push(url);
    return handler(url);
  });
  return seen;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createPostgrestAdmin", () => {
  it("throws AdminNotConfiguredError when Supabase env is absent", () => {
    expect(() => createPostgrestAdmin({})).toThrowError(/not configured/i);
  });

  it("resolves the CORE_SUPABASE_* fallbacks the edge functions used", () => {
    const base = supabaseBase({
      CORE_SUPABASE_URL: "https://core.supabase.co/",
      CORE_SUPABASE_SERVICE_KEY: "service-key",
      CORE_SUPABASE_ANON_KEY: "anon-key",
    });
    expect(base.url).toBe("https://core.supabase.co");
    expect(base.anonKey).toBe("anon-key");
  });

  it("returns the membership WITH its role, not a bare workspace row", async () => {
    // The regression this pins: returning `existing.workspace` silently drops
    // `role`, which makes every owner look like a member and turns billing into
    // a 403 for the whole company. No route test can catch it, because they
    // inject an AdminDb stub.
    const seen = stubFetch((url) =>
      url.includes("workspace_members")
        ? jsonResponse(200, [{ role: "owner", workspaces: WORKSPACE }])
        : jsonResponse(500, {}),
    );
    const resolved = await createPostgrestAdmin(ENV).ensureCallerWorkspace("u1");
    expect(resolved).toEqual({ workspace: WORKSPACE, role: "owner" });
    // No RPC call: an existing membership must short-circuit the personal-workspace create.
    expect(seen.some((u) => u.includes("ensure_personal_workspace"))).toBe(false);
  });

  it("prefers an owner membership over another membership for the same user", async () => {
    stubFetch((url) =>
      url.includes("workspace_members")
        ? jsonResponse(200, [
            { role: "member", workspaces: { ...WORKSPACE, id: "ws_member" } },
            { role: "owner", workspaces: { ...WORKSPACE, id: "ws_owner" } },
          ])
        : jsonResponse(500, {}),
    );
    const resolved = await createPostgrestAdmin(ENV).ensureCallerWorkspace("u1");
    expect(resolved?.workspace.id).toBe("ws_owner");
    expect(resolved?.role).toBe("owner");
  });

  it("returns null and does NOT create a workspace when there is no membership", async () => {
    const seen = stubFetch((url) =>
      url.includes("workspace_members") ? jsonResponse(200, []) : jsonResponse(500, {}),
    );
    expect(await createPostgrestAdmin(ENV).ensureCallerWorkspace("u1")).toBeNull();
    // The RPC may run, but a failed RPC must not be reported as a membership.
    expect(seen.filter((u) => u.includes("ensure_personal_workspace")).length).toBe(1);
  });

  it("does not trust the body of a failed membership read as data", async () => {
    // The guard is `if (res.status >= 400) return null`. Without it the code
    // would fall through and parse whatever the error body happened to carry,
    // so a 500 with a populated `data` array would be read as a real membership.
    // That is fail-open on an authorisation input, so it is pinned here.
    const seen = stubFetch((url) =>
      url.includes("workspace_members")
        ? jsonResponse(500, [{ role: "owner", workspaces: WORKSPACE }])
        : jsonResponse(500, {}),
    );
    expect(await createPostgrestAdmin(ENV).ensureCallerWorkspace("u1")).toBeNull();
    // No membership meant: the personal-workspace create must still be attempted.
    expect(seen.some((u) => u.includes("ensure_personal_workspace"))).toBe(true);
  });

  it("logs the failing personal-workspace create code, then reports no membership", async () => {
    // The edge function logged this because the RPC failing silently is the
    // difference between "the user has no workspace" and "we could not create
    // one", and only the log distinguishes them in production.
    const errors: unknown[][] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      errors.push(args);
    });
    stubFetch((url) => (url.includes("workspace_members") ? jsonResponse(200, []) : jsonResponse(500, { code: "P0001" })));
    try {
      expect(await createPostgrestAdmin(ENV).ensureCallerWorkspace("u1")).toBeNull();
      expect(errors.length).toBeGreaterThan(0);
      expect(JSON.stringify(errors)).toContain("P0001");
    } finally {
      spy.mockRestore();
    }
  });

  it("splits a unique-violation insert into duplicate_applied when the row is applied", async () => {
    stubFetch((url) => {
      if (url.includes("stripe_events?select=") && url.includes("stripe_event_id=eq.")) {
        return jsonResponse(200, [{ ...WORKSPACE, stripe_event_id: "evt_1", applied_at: "2026-01-01" }]);
      }
      return jsonResponse(409, { code: "23505", message: "duplicate key value" });
    });
    expect(
      await createPostgrestAdmin(ENV).insertStripeEvent({
        stripeEventId: "evt_1",
        eventType: "t",
        workspaceId: "ws_1",
        payload: {},
      }),
    ).toEqual({ status: "duplicate_applied" });
  });

  it("splits a unique-violation insert into duplicate_pending when not yet applied", async () => {
    stubFetch((url) => {
      if (url.includes("stripe_events?select=") && url.includes("stripe_event_id=eq.")) {
        return jsonResponse(200, [{ stripe_event_id: "evt_1", applied_at: null }]);
      }
      return jsonResponse(409, { code: "23505", message: "duplicate key value" });
    });
    expect(
      await createPostgrestAdmin(ENV).insertStripeEvent({
        stripeEventId: "evt_1",
        eventType: "t",
        workspaceId: "ws_1",
        payload: {},
      }),
    ).toEqual({ status: "duplicate_pending" });
  });

  it("returns inserted on a clean insert", async () => {
    stubFetch(() => jsonResponse(201, {}));
    expect(
      await createPostgrestAdmin(ENV).insertStripeEvent({
        stripeEventId: "evt_1",
        eventType: "t",
        workspaceId: "ws_1",
        payload: {},
      }),
    ).toEqual({ status: "inserted" });
  });

  it("treats a non-violation insert error as error, not as a duplicate", async () => {
    // Reading a duplicate as any failure would make Stripe stop retrying a
    // genuinely failed event: the worst possible failure mode here.
    stubFetch(() => jsonResponse(400, { code: "42501", message: "permission denied" }));
    const result = await createPostgrestAdmin(ENV).insertStripeEvent({
      stripeEventId: "evt_1",
      eventType: "t",
      workspaceId: "ws_1",
      payload: {},
    });
    expect(result.status).toBe("error");
  });

  it("reports the CAS as lost when the out-of-order guard rejects the update", async () => {
    // Empty representation array == the `or(is.null,lt.<created>)` filter matched
    // nothing, i.e. a newer event already moved last_stripe_event_created.
    const seen = stubFetch(() => jsonResponse(200, []));
    expect(await createPostgrestAdmin(ENV).casUpdateWorkspaceBilling("ws_1", 5, { plan_tier: "free" })).toBe(false);
    expect(seen[0]).toContain("last_stripe_event_created=or.(is.null,lt.5)");
  });

  it("reports the CAS as won when the update matched a row", async () => {
    stubFetch(() => jsonResponse(200, [{ id: "ws_1" }]));
    expect(await createPostgrestAdmin(ENV).casUpdateWorkspaceBilling("ws_1", 5, { plan_tier: "free" })).toBe(true);
  });

  it("throws when the applied_at update fails, so Stripe's retry still re-enters", async () => {
    stubFetch(() => jsonResponse(400, { code: "42501", message: "permission denied" }));
    await expect(createPostgrestAdmin(ENV).markStripeEventApplied("evt_1")).rejects.toThrowError(
      /applied_at update failed/,
    );
  });

  it("syncPlanTierClaims reports false instead of throwing, so a webhook never 500s on it", async () => {
    // The edge function documented this explicitly: a claim-sync failure must
    // not become a 5xx to Stripe, because that makes Stripe retry the event.
    stubFetch(() => jsonResponse(500, { code: "X", message: "boom" }));
    expect(await createPostgrestAdmin(ENV).syncPlanTierClaims(["u1"], "desk")).toBe(false);
  });

  it("listWorkspaceMembers returns [] on error rather than throwing", async () => {
    stubFetch(() => jsonResponse(500, {}));
    expect(await createPostgrestAdmin(ENV).listWorkspaceMembers("ws_1")).toEqual([]);
  });
});

describe("unique-violation classification, through its only caller", () => {
  // `isUniqueViolation` is private, so it is exercised the way it is actually
  // used: a 23505 must be read as a replayed event, anything else must not.
  async function classify(status: number, code: string, message: string) {
    stubFetch((url) => {
      if (url.includes("stripe_events?select=") && url.includes("stripe_event_id=eq.")) {
        return jsonResponse(200, [{ stripe_event_id: "evt_1", applied_at: "2026-01-01" }]);
      }
      return jsonResponse(status, { code, message });
    });
    return createPostgrestAdmin(ENV).insertStripeEvent({
      stripeEventId: "evt_1",
      eventType: "t",
      workspaceId: "ws_1",
      payload: {},
    });
  }

  it("reads the Postgres unique-violation code as a replay", async () => {
    expect((await classify(409, "23505", "duplicate key")).status).toBe("duplicate_applied");
  });

  it("reads a 409 whose message mentions a duplicate as a replay", async () => {
    expect(
      (await classify(409, "", "Duplicate key value violates unique constraint")).status,
    ).toBe("duplicate_applied");
  });

  it("does not read a 400 that merely mentions uniqueness as a replay", async () => {
    expect((await classify(400, "42501", "column violates unique policy")).status).toBe("error");
  });

  it("does not read an unrelated 409 as a replay", async () => {
    expect((await classify(409, "", "too many requests")).status).toBe("error");
  });
});
