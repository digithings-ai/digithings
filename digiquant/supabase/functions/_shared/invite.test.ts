import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  FX_HUB_PRODUCT,
  INVITE_MAX_ATTEMPTS,
  planFloorOutranks,
  redeemProductInvite,
  resolveInviteBrand,
  sha256Hex,
  timingSafeEqualHex,
  type InviteCodeRow,
  type InviteStore,
} from "./invite.ts";

const USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const EMAIL = "teammate@12x.example";
const PLAIN = "12x-desk-invite-alpha";

type Mem = {
  attempts: Array<{ user_id: string; ok: boolean; attempted_at: string }>;
  grants: Map<string, string[]>;
  planFloors: Map<string, string>;
  redemptions: Array<Record<string, unknown>>;
  codes: InviteCodeRow[];
  audits: Array<Record<string, unknown>>;
  increments: string[];
  externalSyncs: Array<{ email: string; productKey: string }>;
};

function memStore(init?: Partial<Mem>): { mem: Mem; store: InviteStore } {
  const mem: Mem = {
    attempts: [],
    grants: new Map(),
    planFloors: new Map(),
    redemptions: [],
    codes: [],
    audits: [],
    increments: [],
    externalSyncs: [],
    ...init,
  };
  const store: InviteStore = {
    countAttempts: async (userId, sinceIso) =>
      mem.attempts.filter((a) => a.user_id === userId && a.attempted_at >= sinceIso)
        .length,
    recordAttempt: async (row) => {
      mem.attempts.push(row);
    },
    listActiveCodes: async () => mem.codes,
    hasGrant: async (email, productKey) =>
      (mem.grants.get(email) ?? []).includes(productKey),
    insertGrant: async (email, productKey) => {
      const prev = mem.grants.get(email) ?? [];
      mem.grants.set(email, [...prev, productKey]);
    },
    upsertPlanFloor: async (email, planFloor) => {
      const current = mem.planFloors.get(email) ?? null;
      if (planFloorOutranks(planFloor, current)) {
        mem.planFloors.set(email, planFloor);
      }
    },
    syncExternalGrant: async (email, productKey) => {
      mem.externalSyncs.push({ email, productKey });
    },
    recordRedemption: async (row) => {
      mem.redemptions.push(row);
    },
    incrementRedemptionCount: async (id) => {
      mem.increments.push(id);
    },
    recordAdminAudit: async (row) => {
      mem.audits.push(row);
    },
  };
  return { mem, store };
}

Deno.test("sha256Hex is stable and timingSafeEqualHex rejects length mismatch", async () => {
  const a = await sha256Hex("abc");
  const b = await sha256Hex("abc");
  assertEquals(a, b);
  assertEquals(a.length, 64);
  assertEquals(timingSafeEqualHex(a, b), true);
  assertEquals(timingSafeEqualHex(a, a.slice(0, 32)), false);
});

Deno.test("env hash grants fx_hub and writes admin audit", async () => {
  const { mem, store } = memStore();
  const envHash = await sha256Hex(PLAIN);
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: FX_HUB_PRODUCT,
    code: PLAIN,
    envHash,
    now: new Date("2026-08-31T12:00:00Z"),
    workspaceId: "ws-1",
    store,
  });
  assertEquals(result, { ok: true, alreadyGranted: false, productKey: "fx_hub", planFloor: null });
  assertEquals(mem.grants.get(EMAIL), ["fx_hub"]);
  assertEquals(mem.redemptions.length, 1);
  assertEquals(mem.redemptions[0]?.source, "env");
  assertEquals(mem.audits.length, 1);
  assertEquals(mem.audits[0]?.event_key, "fx_hub_invite_redeemed");
  assertEquals(mem.externalSyncs, [{ email: EMAIL, productKey: "fx_hub" }]);
});

Deno.test("table hash grants when env hash is unset", async () => {
  const hash = await sha256Hex(PLAIN);
  const { mem, store } = memStore({
    codes: [{
      id: "code-1",
      code_hash: hash,
      max_redemptions: 50,
      redemption_count: 0,
      revoked_at: null,
      plan_floor: null,
    }],
  });
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: `  ${PLAIN}  `,
    store,
  });
  assertEquals(result.ok, true);
  assertEquals(mem.increments, ["code-1"]);
  assertEquals(mem.redemptions[0]?.source, "table");
});

Deno.test("wrong code is INVITE_INVALID and does not grant", async () => {
  const { mem, store } = memStore();
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: "totally-wrong-invite",
    envHash: await sha256Hex(PLAIN),
    store,
  });
  assertEquals(result.ok, false);
  if (!result.ok) assertEquals(result.code, "INVITE_INVALID");
  assertEquals(mem.grants.size, 0);
  assertEquals(mem.attempts[0]?.ok, false);
});

Deno.test("already granted returns ok without a second insert", async () => {
  const { mem, store } = memStore({
    grants: new Map([[EMAIL, ["fx_hub"]]]),
  });
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: PLAIN,
    envHash: await sha256Hex(PLAIN),
    store,
  });
  assertEquals(result, { ok: true, alreadyGranted: true, productKey: "fx_hub", planFloor: null });
  assertEquals(mem.redemptions.length, 0);
});

Deno.test("tiered code grants fx_hub and raises plan_floor", async () => {
  const hash = await sha256Hex(PLAIN);
  const { mem, store } = memStore({
    codes: [{
      id: "code-tiered",
      code_hash: hash,
      max_redemptions: null,
      redemption_count: 0,
      revoked_at: null,
      plan_floor: "desk",
    }],
  });
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: PLAIN,
    store,
  });
  assertEquals(result, { ok: true, alreadyGranted: false, productKey: "fx_hub", planFloor: "desk" });
  assertEquals(mem.planFloors.get(EMAIL), "desk");
});

Deno.test("tiered redemption never downgrades an existing higher tier", async () => {
  const hash = await sha256Hex(PLAIN);
  const { mem, store } = memStore({
    codes: [{
      id: "code-tiered",
      code_hash: hash,
      max_redemptions: null,
      redemption_count: 0,
      revoked_at: null,
      plan_floor: "brief",
    }],
    planFloors: new Map([[EMAIL, "studio"]]),
    grants: new Map([[EMAIL, ["fx_hub"]]]),
  });
  await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: PLAIN,
    store,
  });
  assertEquals(mem.planFloors.get(EMAIL), "studio");
});

Deno.test("planFloorOutranks ranks brief < desk < studio < enterprise", () => {
  assertEquals(planFloorOutranks("desk", "brief"), true);
  assertEquals(planFloorOutranks("brief", "desk"), false);
  assertEquals(planFloorOutranks("brief", null), true);
});

Deno.test("short codes and missing email fail closed", async () => {
  const { store } = memStore();
  const short = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: "short",
    envHash: await sha256Hex(PLAIN),
    store,
  });
  assertEquals(short.ok, false);
  const noEmail = await redeemProductInvite({
    userId: USER,
    email: null,
    productKey: "fx_hub",
    code: PLAIN,
    envHash: await sha256Hex(PLAIN),
    store,
  });
  assertEquals(noEmail.ok, false);
  if (!noEmail.ok) assertEquals(noEmail.code, "EMAIL_REQUIRED");
});

Deno.test("rate limit after INVITE_MAX_ATTEMPTS in the window", async () => {
  const now = new Date("2026-08-31T12:00:00Z");
  const attempts = Array.from({ length: INVITE_MAX_ATTEMPTS }, () => ({
    user_id: USER,
    ok: false,
    attempted_at: "2026-08-31T11:30:00Z",
  }));
  const { store } = memStore({ attempts });
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: PLAIN,
    envHash: await sha256Hex(PLAIN),
    now,
    store,
  });
  assertEquals(result.ok, false);
  if (!result.ok) assertEquals(result.code, "INVITE_RATE_LIMIT");
});

Deno.test("revoked or exhausted table codes do not match", async () => {
  const hash = await sha256Hex(PLAIN);
  const { store } = memStore({
    codes: [
      {
        id: "revoked",
        code_hash: hash,
        max_redemptions: null,
        redemption_count: 0,
        revoked_at: "2026-08-01T00:00:00Z",
        plan_floor: null,
      },
      {
        id: "full",
        code_hash: hash,
        max_redemptions: 1,
        redemption_count: 1,
        revoked_at: null,
        plan_floor: null,
      },
    ],
  });
  const result = await redeemProductInvite({
    userId: USER,
    email: EMAIL,
    productKey: "fx_hub",
    code: PLAIN,
    store,
  });
  assertEquals(result.ok, false);
});

Deno.test("resolveInviteBrand returns marker and line for a branded active code", async () => {
  const hash = await sha256Hex(PLAIN);
  const { store } = memStore({
    codes: [{
      id: "code-brand",
      code_hash: hash,
      max_redemptions: 10,
      redemption_count: 0,
      revoked_at: null,
      plan_floor: null,
      brand_marker: "12X",
      brand_line: "Purpose-built for the 12X desk",
    }],
  });
  assertEquals(await resolveInviteBrand({ productKey: "fx_hub", code: PLAIN, store }), {
    marker: "12X",
    line: "Purpose-built for the 12X desk",
  });
});

Deno.test("resolveInviteBrand returns null for unknown, revoked, and unbranded codes", async () => {
  const hash = await sha256Hex(PLAIN);
  const { store } = memStore({
    codes: [
      {
        id: "code-revoked",
        code_hash: hash,
        max_redemptions: 10,
        redemption_count: 0,
        revoked_at: "2026-09-24T00:00:00Z",
        plan_floor: null,
        brand_marker: "12X",
        brand_line: null,
      },
      {
        id: "code-plain",
        code_hash: await sha256Hex("unbranded-code-alpha"),
        max_redemptions: 10,
        redemption_count: 0,
        revoked_at: null,
        plan_floor: null,
      },
    ],
  });
  assertEquals(
    await resolveInviteBrand({ productKey: "fx_hub", code: "totally-wrong-invite", store }),
    null,
  );
  assertEquals(await resolveInviteBrand({ productKey: "fx_hub", code: PLAIN, store }), null);
  assertEquals(
    await resolveInviteBrand({ productKey: "fx_hub", code: "unbranded-code-alpha", store }),
    null,
  );
});
