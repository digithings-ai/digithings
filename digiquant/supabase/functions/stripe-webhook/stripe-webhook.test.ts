/**
 * Deno tests for T2 Stripe webhook + tier mapping.
 *
 * Run from digiquant/supabase/functions:
 *   deno test --allow-env _shared/tiers_test.ts stripe-webhook/stripe-webhook_test.ts
 *
 * No live Stripe or Supabase — mocked admin client + HMAC fixtures.
 */

import {
  assertEquals,
  assertRejects,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  parseStripeEvent,
  StripeHttpError,
  verifyStripeSignature,
} from "../_shared/stripe.ts";
import { handleStripeEvent } from "../_shared/webhook-handler.ts";
import {
  mapStripeStatus,
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
  }>;
  claims: Map<string, string>;
  claimSyncShouldFail: boolean;
  insertDuplicateNext: boolean;
}

function freshStore(): Store {
  const ws: WorkspaceRow = {
    id: WS_ID,
    stripe_customer_id: null,
    stripe_subscription_id: null,
    subscription_status: "none",
    plan_tier: "free",
    claim_sync_pending: false,
  };
  return {
    workspaces: new Map([[WS_ID, { ...ws }]]),
    members: [{ workspace_id: WS_ID, user_id: USER_ID, role: "owner" }],
    stripeEvents: [],
    claims: new Map([[USER_ID, "free"]]),
    claimSyncShouldFail: false,
    insertDuplicateNext: false,
  };
}

type Filter = { col: string; op: "eq" | "neq"; val: unknown };

function createMockAdmin(store: Store): AdminClient {
  const makeBuilder = (table: string) => {
    let filters: Filter[] = [];
    let pendingInsert: Record<string, unknown> | null = null;
    let pendingUpdate: Record<string, unknown> | null = null;
    let limitN: number | null = null;

    const api = {
      select(_cols?: string) {
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
      // Thenable so `await admin.from(...).insert(...)` and
      // `await admin.from(...).update(...).eq(...)` both work.
      // Mirror supabase-js: PostgREST errors resolve as `{ error }`, they do not reject.
      then(resolve: (v: { data: unknown; error: unknown }) => void) {
        api.thenResolve()
          .then((data) => resolve({ data, error: null }))
          .catch((e) => resolve({ data: null, error: e }));
      },
      async thenResolve(): Promise<unknown[]> {
        if (table === "stripe_events" && pendingInsert) {
          if (store.insertDuplicateNext) {
            store.insertDuplicateNext = false;
            throw { message: "duplicate key", code: "23505" };
          }
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
          });
          pendingInsert = null;
          return [];
        }

        if (table === "workspaces" && pendingUpdate) {
          for (const [id, row] of store.workspaces) {
            let ok = true;
            for (const f of filters) {
              const cur = (row as unknown as Record<string, unknown>)[f.col];
              if (f.op === "eq" && cur !== f.val) ok = false;
              if (f.op === "neq" && cur === f.val) ok = false;
            }
            if (!ok) continue;
            store.workspaces.set(id, { ...row, ...pendingUpdate } as WorkspaceRow);
          }
          pendingUpdate = null;
          return [];
        }

        if (table === "workspaces") {
          let rows = [...store.workspaces.values()];
          for (const f of filters) {
            rows = rows.filter((r) => {
              const cur = (r as unknown as Record<string, unknown>)[f.col];
              if (f.op === "eq") return cur === f.val;
              if (f.op === "neq") return cur !== f.val;
              return true;
            });
          }
          return rows;
        }

        if (table === "workspace_members") {
          let rows = [...store.members];
          for (const f of filters) {
            rows = rows.filter((r) => {
              const cur = (r as unknown as Record<string, unknown>)[f.col];
              if (f.op === "eq") return cur === f.val;
              if (f.op === "neq") return cur !== f.val;
              return true;
            });
          }
          return rows;
        }

        if (table === "stripe_events") {
          let rows = [...store.stripeEvents];
          for (const f of filters) {
            rows = rows.filter((r) => {
              const cur = (r as unknown as Record<string, unknown>)[f.col];
              if (f.op === "eq") return cur === f.val;
              if (f.op === "neq") return cur !== f.val;
              return true;
            });
          }
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

Deno.test("parseStripeEvent rejects garbage", () => {
  assertRejectsSync(() => parseStripeEvent("not-json"));
  assertRejectsSync(() => parseStripeEvent("{}"));
});

function assertRejectsSync(fn: () => unknown) {
  let threw = false;
  try {
    fn();
  } catch (e) {
    threw = e instanceof StripeHttpError;
  }
  assertEquals(threw, true);
}

Deno.test("planTierFromPriceId maps baseline/custom/unknown", () => {
  assertEquals(planTierFromPriceId("price_baseline_m", PRICES), "baseline");
  assertEquals(planTierFromPriceId("price_custom_a", PRICES), "custom");
  assertEquals(planTierFromPriceId("price_other", PRICES), "free");
  assertEquals(planTierFromPriceId(null, PRICES), "free");
});

Deno.test("mapStripeStatus covers roadmap statuses", () => {
  assertEquals(mapStripeStatus("active"), "active");
  assertEquals(mapStripeStatus("trialing"), "active");
  assertEquals(mapStripeStatus("past_due"), "past_due");
  assertEquals(mapStripeStatus("canceled"), "canceled");
});

// ---------------------------------------------------------------------------
// Webhook handler scenarios
// ---------------------------------------------------------------------------

Deno.test("duplicate stripe event is a 200 no-op", async () => {
  Deno.env.set("STRIPE_PRICE_BASELINE_MONTHLY", PRICES.baselineMonthly);
  Deno.env.set("STRIPE_PRICE_BASELINE_ANNUAL", PRICES.baselineAnnual);
  Deno.env.set("STRIPE_PRICE_CUSTOM_MONTHLY", PRICES.customMonthly);
  Deno.env.set("STRIPE_PRICE_CUSTOM_ANNUAL", PRICES.customAnnual);

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
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "baseline");

  const second = await handleStripeEvent(admin, evt);
  assertEquals(second.status, "duplicate");
  // Tier unchanged by replay
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "baseline");
});

Deno.test("out-of-order older event does not regress tier", async () => {
  Deno.env.set("STRIPE_PRICE_BASELINE_MONTHLY", PRICES.baselineMonthly);
  Deno.env.set("STRIPE_PRICE_BASELINE_ANNUAL", PRICES.baselineAnnual);
  Deno.env.set("STRIPE_PRICE_CUSTOM_MONTHLY", PRICES.customMonthly);
  Deno.env.set("STRIPE_PRICE_CUSTOM_ANNUAL", PRICES.customAnnual);

  const store = freshStore();
  const admin = createMockAdmin(store);

  const newer = subEvent({
    id: "evt_new",
    type: "customer.subscription.updated",
    created: 200,
    status: "active",
    priceId: PRICES.customMonthly,
  });
  const older = subEvent({
    id: "evt_old",
    type: "customer.subscription.updated",
    created: 100,
    status: "active",
    priceId: PRICES.baselineMonthly,
  });

  assertEquals((await handleStripeEvent(admin, newer)).status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "custom");
  assertEquals(store.claims.get(USER_ID), "custom");

  assertEquals((await handleStripeEvent(admin, older)).status, "out_of_order");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "custom");
  assertEquals(store.claims.get(USER_ID), "custom");
});

Deno.test("checkout → active → cancel yields free→baseline→free on both stores", async () => {
  Deno.env.set("STRIPE_PRICE_BASELINE_MONTHLY", PRICES.baselineMonthly);
  Deno.env.set("STRIPE_PRICE_BASELINE_ANNUAL", PRICES.baselineAnnual);
  Deno.env.set("STRIPE_PRICE_CUSTOM_MONTHLY", PRICES.customMonthly);
  Deno.env.set("STRIPE_PRICE_CUSTOM_ANNUAL", PRICES.customAnnual);

  const store = freshStore();
  const admin = createMockAdmin(store);

  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "free");
  assertEquals(store.claims.get(USER_ID), "free");

  const co = await handleStripeEvent(admin, checkoutEvent(10));
  assertEquals(co.status, "applied");
  assertEquals(store.workspaces.get(WS_ID)!.stripe_customer_id, "cus_1");
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "free"); // tier still free until sub event

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
  assertEquals(store.workspaces.get(WS_ID)!.subscription_status, "active");
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
  assertEquals(store.workspaces.get(WS_ID)!.subscription_status, "canceled");
  assertEquals(store.claims.get(USER_ID), "free");
  assertEquals(store.workspaces.get(WS_ID)!.claim_sync_pending, false);
});

Deno.test("claim-sync failure flags row but still returns applied (200 path)", async () => {
  Deno.env.set("STRIPE_PRICE_BASELINE_MONTHLY", PRICES.baselineMonthly);
  Deno.env.set("STRIPE_PRICE_BASELINE_ANNUAL", PRICES.baselineAnnual);
  Deno.env.set("STRIPE_PRICE_CUSTOM_MONTHLY", PRICES.customMonthly);
  Deno.env.set("STRIPE_PRICE_CUSTOM_ANNUAL", PRICES.customAnnual);

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
  // Workspace tier DID update (auth sync is last / best-effort).
  assertEquals(store.workspaces.get(WS_ID)!.plan_tier, "custom");
  assertEquals(store.workspaces.get(WS_ID)!.claim_sync_pending, true);
  // Claim store unchanged because auth update failed.
  assertEquals(store.claims.get(USER_ID), "free");
});
