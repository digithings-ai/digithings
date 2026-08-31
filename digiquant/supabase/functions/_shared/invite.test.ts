import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  FX_HUB_PRODUCT,
  INVITE_MAX_ATTEMPTS,
  redeemProductInvite,
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
  redemptions: Array<Record<string, unknown>>;
  codes: InviteCodeRow[];
  audits: Array<Record<string, unknown>>;
  increments: string[];
};

function memStore(init?: Partial<Mem>): { mem: Mem; store: InviteStore } {
  const mem: Mem = {
    attempts: [],
    grants: new Map(),
    redemptions: [],
    codes: [],
    audits: [],
    increments: [],
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
  assertEquals(result, { ok: true, alreadyGranted: false, productKey: "fx_hub" });
  assertEquals(mem.grants.get(EMAIL), ["fx_hub"]);
  assertEquals(mem.redemptions.length, 1);
  assertEquals(mem.redemptions[0]?.source, "env");
  assertEquals(mem.audits.length, 1);
  assertEquals(mem.audits[0]?.event_key, "fx_hub_invite_redeemed");
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
  assertEquals(result, { ok: true, alreadyGranted: true, productKey: "fx_hub" });
  assertEquals(mem.redemptions.length, 0);
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
      },
      {
        id: "full",
        code_hash: hash,
        max_redemptions: 1,
        redemption_count: 1,
        revoked_at: null,
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
