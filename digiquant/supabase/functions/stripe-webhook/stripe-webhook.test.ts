/**
 * Deno tests for T2 Stripe webhook + billing auth gates.
 *
 * Run from digiquant/supabase/functions:
 *   deno test --allow-env _shared/tiers.test.ts stripe-webhook/stripe-webhook.test.ts
 *
 * No live Stripe or Supabase — mocked admin client + HMAC fixtures.
 */

import {
  assertEquals,
  assertRejects,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  requireBearerHeader,
  requireWorkspaceOwner,
} from "../_shared/billing-auth.ts";
import {
  parseStripeEvent,
  StripeHttpError,
  verifyStripeSignature,
} from "../_shared/stripe.ts";
import { handleStripeEvent } from "../_shared/webhook-handler.ts";
import {
  mapStripeStatus,
  planTierForSubscriptionStatus,
  planTierFromPriceId,
  type PriceTierEnv,
} from "../_shared/tiers.ts";
import type { AdminClient, WorkspaceRow } from "../_shared/supabase-admin.ts";
import type { StripeEvent } from "../_shared/stripe.ts";

const PRICES: PriceTierEnv = {
  baselineMonthly: "price_baseline_m",
  baselineAnnual: "price_baseline_a",
  customMonthly: "price_custom_m",
  customAnnual: "price_custom_a",
};

const WS_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "22222222-2222-2222-2222-222222222222";
const MEMBER_ID = "33333333-3333-3333-3333-333333333333";

// ---------------------------------------------------------------------------
// In-memory admin mock
// ---------------------------------------------------------------------------

interface Store {
  workspaces: Map<string, WorkspaceRow>;
  members: Array<{ workspace_id: string; user_id: string; role: string }>;
  stripeEvents: Array<{
    stripe_event_id: string;
    event_type: string;
    workspace_id: string | null;
    payload: Record<string, unknown>;
    processed_at: string;
    applied_at: string | null;
  }>;
  claims: Map<string, string>;
  claimSyncShouldFail: boolean;
  /** Throw on the next non-CAS claim_sync_pending-only update path, or CAS fail. */
  failNextWorkspaceUpdate: boolean;
  failNextCasUpdate: boolean;
}

function freshStore(overrides?: Partial<WorkspaceRow>): Store {
  const ws: WorkspaceRow = {
    id: WS_ID,
    stripe_customer_id: null,
    stripe_subscription_id: null,
    subscription_status: "none",
    plan_tier: "free",
    claim_sync_pending: false,
    last_stripe_event_created: null,
    ...overrides,
  };
  return {
    workspaces: new Map([[WS_ID, { ...ws }]]),
    members: [{ workspace_id: WS_ID, user_id: USER_ID, role: "owner" }],
    stripeEvents: [],
    claims: new Map([[USER_ID, "free"]]),
    claimSyncShouldFail: false,
    failNextWorkspaceUpdate: false,
    failNextCasUpdate: false,
  };
}

type Filter = {
  col: string;
  op: "eq" | "neq" | "is" | "lt" | "or";
  val: unknown;
};

function matchesFilters(
  row: Record<string, unknown>,
  filters: Filter[],
): boolean {
  for (const f of filters) {
    if (f.op === "or") {
      // PostgREST or: "last_stripe_event_created.is.null,last_stripe_event_created.lt.N"
      const expr = String(f.val);
      const parts = expr.split(",");
      let any = false;
      for (const part of parts) {
        if (part.endsWith(".is.null")) {
          const col = part.replace(/\.is\.null$/, "");
          if (row[col] == null) any = true;
        } else {
          const m = part.match(/^(.+)\.lt\.(\d+)$/);
          if (m) {
            const col = m[1]!;
            const n = Number(m[2]);
            const cur = row[col];
            if (typeof cur === "number" && cur < n) any = true;
          }
        }
      }
      if (!any) return false;
      continue;
    }
    const cur = row[f.col];
    if (f.op === "eq" && cur !== f.val) return false;
    if (f.op === "neq" && cur === f.val) return false;
    if (f.op === "is") {
      if (f.val === null) {
        if (cur != null) return false;
      } else if (cur !== f.val) {
        return false;
      }
    }
    if (f.op === "lt") {
      if (!(typeof cur === "number" && cur < Number(f.val))) return false;
    }
  }
  return true;
}

function createMockAdmin(store: Store): AdminClient {
  const makeBuilder = (table: string) => {
    let filters: Filter[] = [];
    let pendingInsert: Record<string, unknown> | null = null;
    let pendingUpdate: Record<string, unknown> | null = null;
    let limitN: number | null = null;
    let returnSelect = false;

    const api = {
      select(_cols?: string) {
        if (pendingUpdate) returnSelect = true;
        return api;
      },
      insert(row: Record<string, unknown>) {
        pendingInsert = row;
        return api;
      },
      update(row: Record<string, unknown>) {
        pendingUpdate = row;
        return api;
      },
      eq(col: string, val: unknown) {
        filters.push({ col, op: "eq", val });
        return api;
      },
      neq(col: string, val: unknown) {
        filters.push({ col, op: "neq", val });
        return api;
      },
      is(col: string, val: unknown) {
        filters.push({ col, op: "is", val });
        return api;
      },
      lt(col: string, val: unknown) {
        filters.push({ col, op: "lt", val });
        return api;
      },
      or(expr: string) {
        filters.push({ col: "", op: "or", val: expr });
        return api;
      },
      order(_col: string, _opts?: { ascending?: boolean }) {
        return api;
      },
      limit(n: number) {
        limitN = n;
        return api;
      },
      async maybeSingle() {
        const rows = await api.thenResolve();
        return { data: rows[0] ?? null, error: null };
      },
      then(resolve: (v: { data: unknown; error: unknown }) => void) {
        api.thenResolve()
          .then((data) => resolve({ data, error: null }))
          .catch((e) => resolve({ data: null, error: e }));
      },
      async thenResolve(): Promise<unknown[]> {
        if (table === "stripe_events" && pendingInsert) {
          const id = String(pendingInsert.stripe_event_id);
          if (store.stripeEvents.some((e) => e.stripe_event_id === id)) {
            throw { message: "duplicate key", code: "23505" };
          }
          store.stripeEvents.push({
            stripe_event_id: id,
            event_type: String(pendingInsert.event_type),
            workspace_id: (pendingInsert.workspace_id as string | null) ?? null,
            payload: (pendingInsert.payload as Record<string, unknown>) ?? {},
            processed_at: new Date().toISOString(),
            applied_at: (pendingInsert.applied_at as string | null) ?? null,
          });
          pendingInsert = null;
          return [];
        }

        if (table === "stripe_events" && pendingUpdate) {
          const updated: unknown[] = [];
          for (const row of store.stripeEvents) {
            if (!matchesFilters(row as unknown as Record<string, unknown>, filters)) {
              continue;
            }
            Object.assign(row, pendingUpdate);
            updated.push({ ...row });
          }
          pendingUpdate = null;
          return returnSelect ? updated : [];
        }

        if (table === "workspaces" && pendingUpdate) {
          if (store.failNextCasUpdate && filters.some((f) => f.op === "or")) {
            store.failNextCasUpdate = false;
            throw { message: "cas failed", code: "PGRST000" };
          }
          if (store.failNextWorkspaceUpdate && !filters.some((f) => f.op === "or")) {
            store.failNextWorkspaceUpdate = false;
            throw { message: "update failed", code: "PGRST000" };
          }
          const updated: unknown[] = [];
          for (const [id, row] of store.workspaces) {
            if (!matchesFilters(row as unknown as Record<string, unknown>, filters)) {
              continue;
            }
            const next = { ...row, ...pendingUpdate } as WorkspaceRow;
            store.workspaces.set(id, next);
            updated.push({ id });
          }
          pendingUpdate = null;
          return returnSelect ? updated : [];
        }

        if (table === "workspaces") {
          let rows = [...store.workspaces.values()];
          rows = rows.filter((r) =>
            matchesFilters(r as unknown as Record<string, unknown>, filters)
          );
          return rows;
        }

        if (table === "workspace_members") {
          let rows = [...store.members];
          rows = rows.filter((r) =>
            matchesFilters(r as unknown as Record<string, unknown>, filters)
          );
          // Join shape for resolveCallerWorkspace
          if (rows.length && filters.some((f) => f.col === "user_id")) {
            return rows.map((r) => ({
              role: r.role,
              workspace_id: r.workspace_id,
              workspaces: store.workspaces.get(r.workspace_id)!,
            }));
          }
          return rows;
        }

        if (table === "stripe_events") {
          let rows = [...store.stripeEvents];
          rows = rows.filter((r) =>
            matchesFilters(r as unknown as Record<string, unknown>, filters)
          );
          if (limitN != null) rows = rows.slice(0, limitN);
          return rows;
        }

        return [];
      },
    };
    return api;
  };

  const client = {
    from(table: string) {
      return makeBuilder(table);
    },
    auth: {
      admin: {
        async getUserById(userId: string) {
          if (!store.claims.has(userId)) {
            return { data: { user: null }, error: { message: "not found" } };
          }
          return {
            data: {
              user: {
                id: userId,
                app_metadata: { plan_tier: store.claims.get(userId) },
              },
            },
            error: null,
          };
        },
        async updateUserById(
          userId: string,
          attrs: { app_metadata?: Record<string, unknown> },
        ) {
          if (store.claimSyncShouldFail) {
            return { data: { user: null }, error: { message: "auth update failed" } };
          }
          const tier = attrs.app_metadata?.plan_tier;
          if (typeof tier === "string") store.claims.set(userId, tier);
          return { data: { user: { id: userId } }, error: null };
        },
      },
    },
  };

  return client as unknown as AdminClient;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function setPriceEnv() {
  Deno.env.set("STRIPE_PRICE_BASELINE_MONTHLY", PRICES.baselineMonthly);
  Deno.env.set("STRIPE_PRICE_BASELINE_ANNUAL", PRICES.baselineAnnual);
  Deno.env.set("STRIPE_PRICE_CUSTOM_MONTHLY", PRICES.customMonthly);
  Deno.env.set("STRIPE_PRICE_CUSTOM_ANNUAL", PRICES.customAnnual);
}

function subEvent(
  opts: {
    id: string;
    type: string;
    created: number;
    status: string;
    priceId: string;
    customer?: string;
  },
): StripeEvent {
  return {
    id: opts.id,
    type: opts.type,
    created: opts.created,
    data: {
      object: {
        id: "sub_1",
        customer: opts.customer ?? "cus_1",
        status: opts.status,
        metadata: { workspace_id: WS_ID },
        items: { data: [{ price: { id: opts.priceId } }] },
      },
    },
  };
}

function checkoutEvent(created: number): StripeEvent {
  return {
    id: "evt_checkout_1",
    type: "checkout.session.completed",
    created,
    data: {
      object: {
        id: "cs_1",
        customer: "cus_1",
        subscription: "sub_1",
        metadata: { workspace_id: WS_ID },
      },
    },
  };
}

async function sign(body: string, secret: string, ts: number): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`${ts}.${body}`),
  );
  const hex = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `t=${ts},v1=${hex}`;
}

// ---------------------------------------------------------------------------
// Signature + tier unit tests
// ---------------------------------------------------------------------------

Deno.test("verifyStripeSignature rejects missing / bad signatures", async () => {
  const secret = "test_webhook_signing_key";
  const body = '{"id":"evt_1"}';
  await assertRejects(
    () => verifyStripeSignature(body, null, secret),
    StripeHttpError,
  );
  await assertRejects(
    () => verifyStripeSignature(body, "t=1,v1=deadbeef", secret, 300, 1),
    StripeHttpError,
  );
});

Deno.test("verifyStripeSignature accepts a valid HMAC", async () => {
  const secret = "test_webhook_signing_key";
  const body = '{"id":"evt_ok","type":"ping","created":1}';
  const ts = 1_700_000_000;
  const header = await sign(body, secret, ts);
  await verifyStripeSignature(body, header, secret, 300, ts);
});

Deno.test("verifyStripeSignature tolerance boundary: exactly 300s ok, 301s reject", async () => {
  const secret = "test_webhook_signing_key";
  const body = '{"id":"evt_tol","type":"ping","created":1}';
  const ts = 1_700_000_000;
  const header = await sign(body, secret, ts);
  await verifyStripeSignature(body, header, secret, 300, ts + 300);
  await assertRejects(
    () => verifyStripeSignature(body, header, secret, 300, ts + 301),
    StripeHttpError,
  );
});

Deno.test("verifyStripeSignature rejects re-serialized body", async () => {
  const secret = "test_webhook_signing_key";
  const raw = '{"id":"evt_raw","type":"ping","created":1}';
  const ts = 1_700_000_000;
  const header = await sign(raw, secret, ts);
  const reserialized = JSON.stringify(JSON.parse(raw), null, 2);
  await assertRejects(
    () => verifyStripeSignature(reserialized, header, secret, 300, ts),
    StripeHttpError,
  );
});

Deno.test("parseStripeEvent rejects garbage", () => {
  let threw = false;
  try {
    parseStripeEvent("not-json");
  } catch (e) {
    threw = e instanceof StripeHttpError;
  }
  assertEquals(threw, true);
});

Deno.test("planTierFromPriceId maps baseline/custom/unknown", () => {
  assertEquals(planTierFromPriceId("price_baseline_m", PRICES), "baseline");
  assertEquals(planTierFromPriceId("price_custom_a", PRICES), "custom");
  assertEquals(planTierFromPriceId("price_other", PRICES), "free");
  assertEquals(planTierFromPriceId(null, PRICES), "free");
});

Deno.test("incomplete status forces free claim (not paid tier from price)", () => {
  assertEquals(mapStripeStatus("incomplete"), "none");
  assertEquals(
    planTierForSubscriptionStatus("none", PRICES.baselineMonthly, PRICES),
    "free",
  );
  assertEquals(
    planTierForSubscriptionStatus("active", PRICES.baselineMonthly, PRICES),
    "baseline",
  );
  assertEquals(
    planTierForSubscriptionStatus("past_due", PRICES.customMonthly, PRICES),
    "custom",
  );
});

// ---------------------------------------------------------------------------
// Webhook handler scenarios
// ---------------------------------------------------------------------------

Deno.test("duplicate applied event is a 200 no-op", async () => {
  setPriceEnv();
  const store = freshStore();
  const admin = createMockAdmin(store);
  const evt = subEvent({
    id: "evt_dup",
    type: "customer.subscription.created",
    created: 100,
    status: "active",
    priceId: PRICES.baselineMonthly,
  });
  const first = await handleStripeEvent(admin, evt);
  assertEquals(first.status, "applied");
  assertEquals(store.stripeEvents[0]!.applied_at != null, true);

  const second = await handleStripeEvent(admin, evt);
  assertEquals(second.status, "duplicate");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "baseline");
});

Deno.test("CAS stale event is out_of_order no-op and marks applied", async () => {
  setPriceEnv();
  const store = freshStore({ last_stripe_event_created: 200, plan_tier: "custom" });
  store.claims.set(USER_ID, "custom");
  const admin = createMockAdmin(store);

  const older = subEvent({
    id: "evt_stale",
    type: "customer.subscription.updated",
    created: 100,
    status: "active",
    priceId: PRICES.baselineMonthly,
  });
  const result = await handleStripeEvent(admin, older);
  assertEquals(result.status, "out_of_order");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "custom");
  assertEquals(store.stripeEvents[0]!.applied_at != null, true);
});

Deno.test("checkout → active → cancel yields free→baseline→free on both stores", async () => {
  setPriceEnv();
  const store = freshStore();
  const admin = createMockAdmin(store);

  const co = await handleStripeEvent(admin, checkoutEvent(10));
  assertEquals(co.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.stripe_customer_id, "cus_1");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "free");
  assertEquals(store.workspaces.get(WS_ID)!.last_stripe_event_created, 10);

  const created = await handleStripeEvent(
    admin,
    subEvent({
      id: "evt_sub_c",
      type: "customer.subscription.created",
      created: 20,
      status: "active",
      priceId: PRICES.baselineMonthly,
    }),
  );
  assertEquals(created.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "baseline");
  assertEquals(store.claims.get(USER_ID), "baseline");

  const deleted = await handleStripeEvent(admin, {
    id: "evt_sub_d",
    type: "customer.subscription.deleted",
    created: 30,
    data: {
      object: {
        id: "sub_1",
        customer: "cus_1",
        status: "canceled",
        metadata: { workspace_id: WS_ID },
      },
    },
  });
  assertEquals(deleted.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "free");
  assertEquals(store.claims.get(USER_ID), "free");
});

Deno.test("claim-sync failure flags row but still returns applied (200 path)", async () => {
  setPriceEnv();
  const store = freshStore();
  store.claimSyncShouldFail = true;
  const admin = createMockAdmin(store);

  const result = await handleStripeEvent(
    admin,
    subEvent({
      id: "evt_claim_fail",
      type: "customer.subscription.created",
      created: 50,
      status: "active",
      priceId: PRICES.customMonthly,
    }),
  );
  assertEquals(result.status, "applied");
  assertEquals(result.claim_sync_pending, true);
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "custom");
  assertEquals(store.workspaces.get(WS_ID)!.claim_sync_pending, true);
  assertEquals(store.claims.get(USER_ID), "free");
  assertEquals(store.stripeEvents[0]!.applied_at != null, true);
});

Deno.test("poison-pill retry: insert then fail then retry re-applies", async () => {
  setPriceEnv();
  const store = freshStore();
  store.failNextCasUpdate = true;
  const admin = createMockAdmin(store);
  const evt = subEvent({
    id: "evt_poison",
    type: "customer.subscription.created",
    created: 60,
    status: "active",
    priceId: PRICES.baselineMonthly,
  });

  let threw = false;
  try {
    await handleStripeEvent(admin, evt);
  } catch {
    threw = true;
  }
  assertEquals(threw, true);
  assertEquals(store.stripeEvents.length, 1);
  assertEquals(store.stripeEvents[0]!.applied_at, null);
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "free");

  // Stripe retries — duplicate_pending path re-applies.
  const retry = await handleStripeEvent(admin, evt);
  assertEquals(retry.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "baseline");
  assertEquals(store.claims.get(USER_ID), "baseline");
  assertEquals(store.stripeEvents[0]!.applied_at != null, true);
});

Deno.test("invoice.payment_failed sets past_due and retries claim sync", async () => {
  setPriceEnv();
  const store = freshStore({
    plan_tier: "baseline",
    subscription_status: "active",
    last_stripe_event_created: 10,
    claim_sync_pending: true,
  });
  store.claims.set(USER_ID, "free"); // claim lagging behind workspace
  const admin = createMockAdmin(store);

  const result = await handleStripeEvent(admin, {
    id: "evt_invoice_fail",
    type: "invoice.payment_failed",
    created: 20,
    data: {
      object: {
        id: "in_1",
        customer: "cus_1",
        subscription: "sub_1",
        metadata: { workspace_id: WS_ID },
      },
    },
  });
  assertEquals(result.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.subscription_status, "past_due");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "baseline");
  assertEquals(store.claims.get(USER_ID), "baseline");
  assertEquals(store.workspaces.get(WS_ID)!.claim_sync_pending, false);
});

Deno.test("incomplete subscription maps to free on both stores", async () => {
  setPriceEnv();
  const store = freshStore({ plan_tier: "baseline", last_stripe_event_created: 1 });
  store.claims.set(USER_ID, "baseline");
  const admin = createMockAdmin(store);

  const result = await handleStripeEvent(
    admin,
    subEvent({
      id: "evt_incomplete",
      type: "customer.subscription.updated",
      created: 5,
      status: "incomplete",
      priceId: PRICES.baselineMonthly,
    }),
  );
  assertEquals(result.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "free");
  assertEquals(store.workspaces.get(WS_ID)!.subscription_status, "none");
  assertEquals(store.claims.get(USER_ID), "free");
});

// ---------------------------------------------------------------------------
// Checkout / portal auth gates
// ---------------------------------------------------------------------------

Deno.test("checkout/portal: missing bearer → 401 UNAUTHENTICATED", async () => {
  const res = requireBearerHeader(null);
  assertEquals(res?.status, 401);
  const body = await res!.json();
  assertEquals(body.code, "UNAUTHENTICATED");
});

Deno.test("checkout/portal: wrong workspace → 403 WORKSPACE_FORBIDDEN", async () => {
  const store = freshStore();
  const admin = createMockAdmin(store);
  const result = await requireWorkspaceOwner(
    admin,
    { id: USER_ID },
    "99999999-9999-9999-9999-999999999999",
  );
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.response.status, 403);
    const body = await result.response.json();
    assertEquals(body.code, "WORKSPACE_FORBIDDEN");
  }
});

Deno.test("checkout/portal: non-owner → 403 WORKSPACE_FORBIDDEN", async () => {
  const store = freshStore();
  store.members = [{ workspace_id: WS_ID, user_id: MEMBER_ID, role: "member" }];
  const admin = createMockAdmin(store);
  const result = await requireWorkspaceOwner(admin, { id: MEMBER_ID }, null);
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.response.status, 403);
  }
});
