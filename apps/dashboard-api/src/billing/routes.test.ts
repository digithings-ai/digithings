import { describe, expect, it, vi } from "vitest";
import {
  handleCreateCheckoutSession,
  handleCustomerPortal,
  handleStripeWebhook,
  type BillingDeps,
} from "./routes";
import type {
  AdminDb,
  CallerWorkspace,
  InsertStripeEventResult,
  StripeEventRow,
  WorkspaceRow,
} from "./admin";
import type { AuthUser } from "./billing-auth";

// Contract parity for the Workers port of three Supabase edge functions.
//
// Every expectation below is a (status, code, message) triple copied from the
// edge function the port replaces. The port's whole contract is "same wire
// shape", so the assertions are on the exact triple, never on `res.ok`.

const WORKSPACE: WorkspaceRow = {
  id: "ws_1",
  stripe_customer_id: "cus_1",
  stripe_subscription_id: "sub_1",
  subscription_status: "active",
  plan_tier: "desk",
  claim_sync_pending: false,
  last_stripe_event_created: 100,
};

function adminStub(overrides: Partial<AdminDb> = {}): AdminDb {
  const caller: CallerWorkspace = { workspace: WORKSPACE, role: "owner" };
  return {
    resolveCallerWorkspace: vi.fn(async () => caller),
    ensureCallerWorkspace: vi.fn(async () => caller),
    getWorkspaceBy: vi.fn(async () => WORKSPACE),
    listWorkspaceMembers: vi.fn(async () => [{ user_id: "u1", role: "owner" }]),
    syncPlanTierClaims: vi.fn(async () => true),
    insertStripeEvent: vi.fn(
      async (): Promise<InsertStripeEventResult> => ({ status: "inserted" }),
    ),
    getStripeEvent: vi.fn(async (): Promise<StripeEventRow | null> => null),
    markStripeEventApplied: vi.fn(async () => undefined),
    casUpdateWorkspaceBilling: vi.fn(async () => true),
    setClaimSyncPending: vi.fn(async () => undefined),
    ...overrides,
  } as AdminDb;
}

const OWNER: AuthUser = { id: "u1", email: "owner@example.com" };

function deps(admin: AdminDb = adminStub(), user: AuthUser | null = OWNER): BillingDeps {
  return { createAdmin: () => admin, resolveUser: async () => user };
}

/** Fully configured env: every lookup the routes make resolves. */
const FULL_ENV = {
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_ANON_KEY: "anon-key",
  SUPABASE_SERVICE_ROLE_KEY: "service-key",
  STRIPE_SECRET_KEY: "sk_test_1",
  NEXT_PUBLIC_APP_URL: "https://digithings.ai",
  STRIPE_PRICE_DESK_MONTHLY: "price_desk_m",
  STRIPE_PRICE_DESK_ANNUAL: "price_desk_a",
  STRIPE_WEBHOOK_SECRET: "whsec_test",
};

/** A real Stripe signature over `body`, so the webhook arms reach their own code. */
async function signedHeader(body: string, secret: string, t: number): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${t}.${body}`));
  const hex = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `t=${t},v1=${hex}`;
}

const EVENT_BODY = JSON.stringify({
  id: "evt_1",
  type: "customer.subscription.updated",
  created: 1_760_000_000,
  data: { object: { id: "sub_1", customer: "cus_1", status: "active" } },
});

/** The verifier's clock: signature tolerance is 300s, so fixtures must be fresh. */
const NOW = () => Math.floor(Date.now() / 1000);

async function signedWebhookRequest(secret = "whsec_test"): Promise<Request> {
  const header = await signedHeader(EVENT_BODY, secret, NOW());
  return new Request("https://x/stripe-webhook", {
    method: "POST",
    headers: { "stripe-signature": header },
    body: EVENT_BODY,
  });
}

async function body(res: Response): Promise<{ code?: string; message?: string }> {
  return (await res.json()) as { code?: string; message?: string };
}

describe("stripe-webhook contract", () => {
  it("rejects a non-POST with 405 METHOD_NOT_ALLOWED / POST only", async () => {
    const res = await handleStripeWebhook(new Request("https://x/stripe-webhook"), FULL_ENV, deps());
    expect(res.status).toBe(405);
    expect(await body(res)).toEqual({ code: "METHOD_NOT_ALLOWED", message: "POST only" });
  });

  it("answers 500 STRIPE_NOT_CONFIGURED when the webhook secret is unset", async () => {
    const env = { ...FULL_ENV };
    delete (env as Record<string, unknown>).STRIPE_WEBHOOK_SECRET;
    const req = new Request("https://x/stripe-webhook", {
      method: "POST",
      headers: { "stripe-signature": `t=${NOW()},v1=deadbeef` },
      body: "{}",
    });
    const res = await handleStripeWebhook(req, env, deps());
    // The edge function verified the signature and the secret in one try, so a
    // missing secret surfaces as its own 500 rather than a 400 signature error.
    expect(res.status).toBe(500);
    expect(await body(res)).toEqual({
      code: "STRIPE_NOT_CONFIGURED",
      message: "Stripe webhook is not configured",
    });
  });

  it("answers 400 INVALID_SIGNATURE / Signature verification failed on a bad signature", async () => {
    const req = new Request("https://x/stripe-webhook", {
      method: "POST",
      headers: { "stripe-signature": `t=${NOW()},v1=deadbeef` },
      body: "{}",
    });
    const res = await handleStripeWebhook(req, FULL_ENV, deps());
    expect(res.status).toBe(400);
    expect(await body(res)).toEqual({
      code: "INVALID_SIGNATURE",
      message: "Signature verification failed",
    });
  });

  it("answers 500 ADMIN_NOT_CONFIGURED when the Supabase env is absent", async () => {
    // Signed for real, and the webhook secret is PRESENT: the edge functions
    // checked the secret and the signature before touching the admin client, so
    // an env missing the secret too would answer STRIPE_NOT_CONFIGURED and pin
    // the wrong arm.
    const req = await signedWebhookRequest();
    // No deps on purpose: `deps()` injects an admin stub, which would make this
    // arm unreachable — the stub never throws, so the real `createPostgrestAdmin`
    // must be the one that rejects the missing Supabase env.
    const res = await handleStripeWebhook(req, { STRIPE_WEBHOOK_SECRET: "whsec_test" }, {});
    expect(res.status).toBe(500);
    expect(await body(res)).toEqual({
      code: "ADMIN_NOT_CONFIGURED",
      message: "Billing backend not configured",
    });
  });

  it("returns 200 with the handler result for a correctly signed event", async () => {
    const admin = adminStub();
    const res = await handleStripeWebhook(await signedWebhookRequest(), FULL_ENV, {
      createAdmin: () => admin,
    });
    expect(res.status).toBe(200);
    expect(await body(res)).toMatchObject({ ok: true, status: "applied" });
    expect(admin.insertStripeEvent).toHaveBeenCalledTimes(1);
    expect(admin.markStripeEventApplied).toHaveBeenCalledWith("evt_1");
  });

  it("answers 400 INVALID_SIGNATURE when the body was tampered with", async () => {
    const req = new Request("https://x/stripe-webhook", {
      method: "POST",
      headers: { "stripe-signature": await signedHeader(EVENT_BODY, "whsec_test", NOW()) },
      body: EVENT_BODY.replace("evt_1", "evt_2"),
    });
    const res = await handleStripeWebhook(req, FULL_ENV, deps());
    expect(res.status).toBe(400);
    expect(await body(res)).toEqual({
      code: "INVALID_SIGNATURE",
      message: "Signature verification failed",
    });
  });

  it("answers 200 duplicate and does not re-apply an already applied event", async () => {
    const admin = adminStub({
      insertStripeEvent: vi.fn(async () => ({ status: "duplicate_applied" as const })),
    });
    const res = await handleStripeWebhook(await signedWebhookRequest(), FULL_ENV, {
      createAdmin: () => admin,
    });
    expect(res.status).toBe(200);
    expect(await body(res)).toMatchObject({ status: "duplicate" });
    // A duplicate must be a no-op: re-applying would double-write billing state.
    expect(admin.casUpdateWorkspaceBilling).not.toHaveBeenCalled();
    expect(admin.markStripeEventApplied).not.toHaveBeenCalled();
  });

  it("answers 401 UNAUTHENTICATED / Invalid session when the session does not resolve", async () => {
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "POST", headers: { Authorization: "Bearer t" } }),
      FULL_ENV,
      deps(adminStub(), null),
    );
    expect(res.status).toBe(401);
    expect(await body(res)).toEqual({ code: "UNAUTHENTICATED", message: "Invalid session" });
  });
});

describe("customer-portal contract", () => {
  it("answers 204 with CORS headers on OPTIONS", async () => {
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "OPTIONS" }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("*");
  });

  it("rejects a PUT with 405 METHOD_NOT_ALLOWED / GET or POST only", async () => {
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "PUT" }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(405);
    expect(await body(res)).toEqual({
      code: "METHOD_NOT_ALLOWED",
      message: "GET or POST only",
    });
  });

  it("rejects a missing bearer with 401 UNAUTHENTICATED / Missing bearer token", async () => {
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "POST" }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(401);
    expect(await body(res)).toEqual({
      code: "UNAUTHENTICATED",
      message: "Missing bearer token",
    });
  });

  it("answers 500 ADMIN_NOT_CONFIGURED when SUPABASE_URL is missing", async () => {
    const env = { ...FULL_ENV, STRIPE_SECRET_KEY: "sk" };
    delete (env as Record<string, unknown>).SUPABASE_URL;
    delete (env as Record<string, unknown>).CORE_SUPABASE_URL;
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "POST", headers: { Authorization: "Bearer t" } }),
      env,
      deps(),
    );
    expect(res.status).toBe(500);
    expect(await body(res)).toEqual({
      code: "ADMIN_NOT_CONFIGURED",
      message: "Billing backend not configured",
    });
  });

  it("answers 409 NO_STRIPE_CUSTOMER when the workspace has no Stripe customer", async () => {
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "POST", headers: { Authorization: "Bearer t" } }),
      FULL_ENV,
      deps(
        adminStub({
          ensureCallerWorkspace: vi.fn(async () => ({
            workspace: { ...WORKSPACE, stripe_customer_id: null },
            role: "owner" as const,
          })),
        }),
      ),
    );
    expect(res.status).toBe(409);
    expect(await body(res)).toEqual({
      code: "NO_STRIPE_CUSTOMER",
      message: "No Stripe customer on workspace",
    });
  });

  it("answers 500 APP_URL_NOT_CONFIGURED when the app URL is unset", async () => {
    const env: Record<string, unknown> = { ...FULL_ENV };
    delete env.NEXT_PUBLIC_APP_URL;
    delete env.APP_URL;
    const res = await handleCustomerPortal(
      new Request("https://x/customer-portal", { method: "POST", headers: { Authorization: "Bearer t" } }),
      env,
      deps(),
    );
    expect(res.status).toBe(500);
    expect(await body(res)).toEqual({
      code: "APP_URL_NOT_CONFIGURED",
      message: "App URL not configured",
    });
  });
});

describe("create-checkout-session contract", () => {
  it("answers 204 with CORS headers on OPTIONS", async () => {
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", { method: "OPTIONS" }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("*");
  });

  it("rejects a GET with 405 METHOD_NOT_ALLOWED / POST only", async () => {
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", { method: "GET" }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(405);
    expect(await body(res)).toEqual({ code: "METHOD_NOT_ALLOWED", message: "POST only" });
  });

  it("rejects a missing bearer with 401 UNAUTHENTICATED / Missing bearer token", async () => {
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", { method: "POST", body: "{}" }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(401);
    expect(await body(res)).toEqual({
      code: "UNAUTHENTICATED",
      message: "Missing bearer token",
    });
  });

  it("answers 400 INVALID_TIER for an unknown tier", async () => {
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", {
        method: "POST",
        headers: { Authorization: "Bearer t", "Content-Type": "application/json" },
        body: JSON.stringify({ tier: "platinum" }),
      }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(400);
    expect(await body(res)).toEqual({
      code: "INVALID_TIER",
      message: "tier must be brief, desk, or studio",
    });
  });

  it("answers 400 INVALID_INTERVAL for an unknown interval", async () => {
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", {
        method: "POST",
        headers: { Authorization: "Bearer t", "Content-Type": "application/json" },
        body: JSON.stringify({ tier: "desk", interval: "weekly" }),
      }),
      FULL_ENV,
      deps(),
    );
    expect(res.status).toBe(400);
    expect(await body(res)).toEqual({
      code: "INVALID_INTERVAL",
      message: "interval must be monthly or annual",
    });
  });

  it("answers 500 PRICE_NOT_CONFIGURED naming the exact env var", async () => {
    const env: Record<string, unknown> = { ...FULL_ENV };
    delete env.STRIPE_PRICE_DESK_ANNUAL;
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", {
        method: "POST",
        headers: { Authorization: "Bearer t", "Content-Type": "application/json" },
        body: JSON.stringify({ tier: "desk", interval: "annual" }),
      }),
      env,
      deps(),
    );
    expect(res.status).toBe(500);
    expect(await body(res)).toEqual({
      code: "PRICE_NOT_CONFIGURED",
      message: "STRIPE_PRICE_DESK_ANNUAL is not set on Edge Function secrets",
    });
  });

  it("answers 403 WORKSPACE_FORBIDDEN when the caller is not an owner", async () => {
    const res = await handleCreateCheckoutSession(
      new Request("https://x/create-checkout-session", {
        method: "POST",
        headers: { Authorization: "Bearer t", "Content-Type": "application/json" },
        body: JSON.stringify({ tier: "desk" }),
      }),
      FULL_ENV,
      deps(
        adminStub({
          ensureCallerWorkspace: vi.fn(async () => ({ workspace: WORKSPACE, role: "member" as const })),
        }),
      ),
    );
    expect(res.status).toBe(403);
    expect(await body(res)).toEqual({
      code: "WORKSPACE_FORBIDDEN",
      message: "Owner role required",
    });
  });
});