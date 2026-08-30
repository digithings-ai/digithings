/**
 * Deno tests for T3 settings handlers + vault TS mirror.
 *
 * Run from digiquant/supabase/functions:
 *   deno test --allow-env --allow-read _shared/vault.test.ts settings/settings.test.ts
 *
 * No live Stripe/Supabase/Alpaca — mocked admin + vault seam.
 */

import {
  assertEquals,
  assertRejects,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import type { AdminClient, WorkspaceRow } from "../_shared/supabase-admin.ts";
import {
  handleSettingsRequest,
  pinnedAlpacaRedirectUri,
} from "../_shared/settings-handlers.ts";
import {
  buildAad,
  canonicalJson,
  fingerprint,
  hexToBytes,
  loadMasterKey,
  openBytes,
  parseCredential,
  sealCredential,
  VaultPayloadError,
  type MasterKey,
} from "../_shared/vault.ts";

const WS_A = "11111111-1111-4111-8111-111111111111";
const WS_B = "22222222-2222-4222-8222-222222222222";
const USER_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const USER_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const APP_URL = "https://app.example";

// ---------------------------------------------------------------------------
// In-memory admin mock
// ---------------------------------------------------------------------------

interface Store {
  workspaces: Map<string, WorkspaceRow>;
  members: Array<{ workspace_id: string; user_id: string; role: string }>;
  profiles: Array<Record<string, unknown>>;
  brokers: Array<Record<string, unknown>>;
}

function wsRow(id: string, planTier = "custom"): WorkspaceRow {
  return {
    id,
    stripe_customer_id: null,
    stripe_subscription_id: null,
    subscription_status: "none",
    plan_tier: planTier,
    claim_sync_pending: false,
    last_stripe_event_created: null,
  };
}

function freshStore(): Store {
  return {
    workspaces: new Map([
      [WS_A, wsRow(WS_A, "custom")],
      [WS_B, wsRow(WS_B, "custom")],
    ]),
    members: [
      { workspace_id: WS_A, user_id: USER_A, role: "owner" },
      { workspace_id: WS_B, user_id: USER_B, role: "owner" },
    ],
    profiles: [],
    brokers: [],
  };
}

type Filter = { col: string; op: "eq" | "neq"; val: unknown };

function mockAdmin(store: Store): AdminClient {
  const makeBuilder = (table: string) => {
    const filters: Filter[] = [];
    let pendingInsert: Record<string, unknown> | null = null;
    let pendingUpdate: Record<string, unknown> | null = null;
    let selectCols = "*";
    let limitN: number | null = null;
    let maybeSingle = false;
    let wantSingle = false;
    let orderCol: string | null = null;
    let orderAsc = true;

    const api: Record<string, unknown> = {};
    const chain = () => api;

    api.select = (cols: string) => {
      selectCols = cols;
      return chain();
    };
    api.insert = (row: Record<string, unknown>) => {
      pendingInsert = row;
      return chain();
    };
    api.update = (vals: Record<string, unknown>) => {
      pendingUpdate = vals;
      return chain();
    };
    api.eq = (col: string, val: unknown) => {
      filters.push({ col, op: "eq", val });
      return chain();
    };
    api.neq = (col: string, val: unknown) => {
      filters.push({ col, op: "neq", val });
      return chain();
    };
    api.order = (col: string, opts?: { ascending?: boolean }) => {
      orderCol = col;
      orderAsc = opts?.ascending ?? true;
      return chain();
    };
    api.limit = (n: number) => {
      limitN = n;
      return chain();
    };
    api.maybeSingle = () => {
      maybeSingle = true;
      return chain();
    };
    api.single = () => {
      wantSingle = true;
      return chain();
    };

    const run = async () => {
      if (table === "workspace_members" && !pendingInsert && !pendingUpdate) {
        const uid = filters.find((f) => f.col === "user_id" && f.op === "eq")?.val;
        const rows = store.members
          .filter((m) => m.user_id === uid)
          .map((m) => ({
            role: m.role,
            workspace_id: m.workspace_id,
            workspaces: store.workspaces.get(m.workspace_id),
          }));
        return { data: rows, error: null };
      }

      if (table === "olympus_profile_config") {
        if (pendingInsert) {
          if (pendingInsert.profile_key === "house" && pendingInsert.is_house_default === false) {
            return {
              data: null,
              error: { message: "chk_olympus_profile_config_house_key", code: "23514" },
            };
          }
          // Simulate supersedes_id unique collision.
          if (
            pendingInsert.supersedes_id &&
            store.profiles.some((p) => p.supersedes_id === pendingInsert!.supersedes_id)
          ) {
            return {
              data: null,
              error: { message: "duplicate key value violates unique constraint", code: "23505" },
            };
          }
          const row = {
            ...pendingInsert,
            recorded_at: new Date().toISOString(),
          };
          store.profiles.push(row);
          const data = wantSingle || maybeSingle ? row : [row];
          return { data, error: null };
        }
        let rows = [...store.profiles];
        for (const f of filters) {
          if (f.op === "eq") rows = rows.filter((r) => r[f.col] === f.val);
        }
        if (orderCol) {
          const col = orderCol;
          rows.sort((a, b) => {
            const av = String(a[col] ?? "");
            const bv = String(b[col] ?? "");
            return orderAsc ? av.localeCompare(bv) : bv.localeCompare(av);
          });
        }
        if (limitN != null) rows = rows.slice(0, limitN);
        if (wantSingle || maybeSingle) {
          return { data: rows[0] ?? null, error: null };
        }
        return { data: rows, error: null };
      }

      if (table === "broker_connections") {
        if (pendingInsert) {
          const activeClash = store.brokers.some(
            (b) =>
              b.workspace_id === pendingInsert!.workspace_id &&
              b.broker === pendingInsert!.broker &&
              b.env === pendingInsert!.env &&
              b.status === "active",
          );
          if (activeClash) {
            return {
              data: null,
              error: {
                message: "duplicate key value violates unique constraint uq_broker_connections_active",
                code: "23505",
              },
            };
          }
          const row = {
            ...pendingInsert,
            last_used_at: null,
            revoked_at: null,
            created_at: new Date().toISOString(),
          };
          store.brokers.push(row);
          return {
            data: wantSingle || maybeSingle ? projectFp(row, selectCols) : [projectFp(row, selectCols)],
            error: null,
          };
        }
        if (pendingUpdate) {
          let rows = [...store.brokers];
          for (const f of filters) {
            if (f.op === "eq") rows = rows.filter((r) => r[f.col] === f.val);
            if (f.op === "neq") rows = rows.filter((r) => r[f.col] !== f.val);
          }
          if (rows.length === 0) {
            return { data: maybeSingle || wantSingle ? null : [], error: null };
          }
          for (const target of rows) {
            Object.assign(target, pendingUpdate);
          }
          const projected = projectFp(rows[0]!, selectCols);
          return { data: maybeSingle || wantSingle ? projected : rows.map((r) => projectFp(r, selectCols)), error: null };
        }
        let rows = [...store.brokers];
        for (const f of filters) {
          if (f.op === "eq") rows = rows.filter((r) => r[f.col] === f.val);
        }
        if (orderCol) {
          const col = orderCol;
          rows.sort((a, b) => {
            const av = String(a[col] ?? "");
            const bv = String(b[col] ?? "");
            return orderAsc ? av.localeCompare(bv) : bv.localeCompare(av);
          });
        }
        const projected = rows.map((r) => projectFp(r, selectCols));
        if (wantSingle || maybeSingle) {
          return { data: projected[0] ?? null, error: null };
        }
        return { data: projected, error: null };
      }

      return { data: null, error: { message: `unknown table ${table}` } };
    };

    api.then = (onFulfilled: (v: unknown) => unknown, onRejected?: (e: unknown) => unknown) =>
      run().then(onFulfilled, onRejected);

    return api;
  };

  return {
    from: (table: string) => makeBuilder(table),
  } as unknown as AdminClient;
}

function projectFp(row: Record<string, unknown>, cols: string): Record<string, unknown> {
  if (cols.includes("ciphertext")) return { ...row };
  const out: Record<string, unknown> = {};
  for (const c of cols.split(",").map((s) => s.trim())) {
    if (c in row) out[c] = row[c];
  }
  delete out.ciphertext;
  delete out.nonce;
  delete out.secret;
  delete out.access_token;
  return out;
}

const TEST_KEY: MasterKey = loadMasterKey({
  DIGIQUANT_VAULT_MASTER_KEY: "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
  DIGIQUANT_VAULT_KEY_ID: "v1",
});

let uuidSeq = 0;
function nextUuid(): string {
  uuidSeq += 1;
  return `aaaaaaaa-bbbb-4ccc-8ddd-${String(uuidSeq).padStart(12, "0")}`;
}

function authReq(method: string, path: string, body?: unknown, auth = true): Request {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) headers.Authorization = "Bearer test-jwt";
  return new Request(`http://localhost/functions/v1/settings${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function call(
  store: Store,
  method: string,
  path: string,
  body?: unknown,
  opts: {
    userId?: string;
    planTier?: string | null;
    auth?: boolean;
  } = {},
): Promise<{ status: number; json: Record<string, unknown> }> {
  const userId = opts.userId ?? USER_A;
  const res = await handleSettingsRequest(authReq(method, path, body, opts.auth !== false), {
    admin: mockAdmin(store),
    user: {
      id: userId,
      email: "owner@example.com",
      plan_tier: opts.planTier === undefined ? "custom" : opts.planTier,
    },
    vaultKey: TEST_KEY,
    uuid: nextUuid,
    appUrl: APP_URL,
    exchangeAlpacaCode: async ({ redirectUri }) => {
      // Capture that exchange uses server-pinned URI.
      if (redirectUri !== pinnedAlpacaRedirectUri(APP_URL)) {
        throw new Error("redirect_uri not pinned");
      }
      return { access_token: "alpaca-access-token-xyz" };
    },
  });
  const json = await res.json();
  return { status: res.status, json };
}

const validInvestment = {
  risk_tolerance: "moderate",
  horizon_years: 10,
  liquidity_needs: "medium",
  base_currency: "USD",
  tax_jurisdiction: "US",
  esg_preference: "none",
  experience_level: "intermediate",
};

// ---------------------------------------------------------------------------
// Auth / tier
// ---------------------------------------------------------------------------

Deno.test("401 when Authorization bearer missing", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", "/brokers", undefined, { auth: false });
  assertEquals(status, 401);
  assertEquals(json.code, "UNAUTHENTICATED");
});

Deno.test("403 WORKSPACE_FORBIDDEN when user has no membership", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", "/brokers", undefined, {
    userId: "99999999-9999-4999-8999-999999999999",
  });
  assertEquals(status, 403);
  assertEquals(json.code, "WORKSPACE_FORBIDDEN");
});

Deno.test("403 TIER_FORBIDDEN for baseline on profile write", async () => {
  const store = freshStore();
  store.workspaces.set(WS_A, wsRow(WS_A, "baseline"));
  const { status, json } = await call(store, "PATCH", "/profile", {
    profile_key: "workspace",
    label: "L",
    investment: validInvestment,
  }, { planTier: "baseline" });
  assertEquals(status, 403);
  assertEquals(json.code, "TIER_FORBIDDEN");
  assertEquals(store.profiles.length, 0);
});

Deno.test("403 TIER_FORBIDDEN for baseline on broker connect", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "api_key",
    key_id: "PK",
    secret: "sec",
  }, { planTier: "baseline" });
  assertEquals(status, 403);
  assertEquals(json.code, "TIER_FORBIDDEN");
});

// ---------------------------------------------------------------------------
// Profile — workspace isolation
// ---------------------------------------------------------------------------

Deno.test("PATCH profile: schema re-validation reject", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/profile", {
    profile_key: "ws-overlay",
    label: "My overlay",
    investment: { risk_tolerance: "yolo", horizon_years: 10 },
  });
  assertEquals(status, 400);
  assertEquals(json.code, "SCHEMA_INVALID");
  assertEquals(store.profiles.length, 0);
});

Deno.test("PATCH profile: house-key reject (fail closed)", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/profile", {
    profile_key: "house",
    label: "Nope",
    investment: validInvestment,
  });
  assertEquals(status, 400);
  assertEquals(json.code, "HOUSE_KEY_FORBIDDEN");
});

Deno.test("PATCH profile: stamps workspace_id; same profile_key isolated across workspaces", async () => {
  const store = freshStore();
  const a1 = await call(store, "PATCH", "/profile", {
    profile_key: "workspace",
    label: "A-v1",
    investment: validInvestment,
  }, { userId: USER_A });
  assertEquals(a1.status, 200);
  assertEquals(a1.json.workspace_id, WS_A);
  assertEquals(store.profiles[0]!.workspace_id, WS_A);

  store.profiles[0]!.recorded_at = "2026-08-01T00:00:00Z";

  const b1 = await call(store, "PATCH", "/profile", {
    profile_key: "workspace",
    label: "B-v1",
    investment: validInvestment,
  }, { userId: USER_B });
  assertEquals(b1.status, 200);
  assertEquals(b1.json.workspace_id, WS_B);
  assertEquals(store.profiles.length, 2);

  // Workspace A tip chain stays independent — B's write does not 409 A's tip.
  const a2 = await call(store, "PATCH", "/profile", {
    profile_key: "workspace",
    label: "A-v2",
    investment: validInvestment,
    expected_version_id: a1.json.version_id,
  }, { userId: USER_A });
  assertEquals(a2.status, 200);
  assertEquals(store.profiles.filter((p) => p.workspace_id === WS_A).length, 2);
  assertEquals(store.profiles.filter((p) => p.workspace_id === WS_B).length, 1);
});

Deno.test("PATCH profile: VERSION_CONFLICT on stale tip", async () => {
  const store = freshStore();
  const first = await call(store, "PATCH", "/profile", {
    profile_key: "ws-overlay",
    label: "v1",
    investment: validInvestment,
  });
  assertEquals(first.status, 200);
  store.profiles[0]!.recorded_at = "2026-08-01T00:00:00Z";

  const conflict = await call(store, "PATCH", "/profile", {
    profile_key: "ws-overlay",
    label: "stale",
    investment: validInvestment,
    expected_version_id: "00000000-0000-4000-8000-000000000099",
  });
  assertEquals(conflict.status, 409);
  assertEquals(conflict.json.code, "VERSION_CONFLICT");
});

Deno.test("PATCH profile: supersedes unique collision → 409 VERSION_CONFLICT", async () => {
  const store = freshStore();
  const first = await call(store, "PATCH", "/profile", {
    profile_key: "ws-overlay",
    label: "v1",
    investment: validInvestment,
  });
  store.profiles[0]!.recorded_at = "2026-08-01T00:00:00Z";
  // Pre-seed a row that already claims the same supersedes_id.
  store.profiles.push({
    id: "already-superseding",
    workspace_id: WS_A,
    profile_key: "ws-overlay",
    supersedes_id: first.json.version_id,
    is_house_default: false,
    recorded_at: "2026-08-02T00:00:00Z",
  });
  const clash = await call(store, "PATCH", "/profile", {
    profile_key: "ws-overlay",
    label: "race",
    investment: validInvestment,
    expected_version_id: first.json.version_id,
  });
  // Tip check may 409 first, or insert unique → 409.
  assertEquals(clash.status, 409);
  assertEquals(clash.json.code, "VERSION_CONFLICT");
});

// ---------------------------------------------------------------------------
// Brokers
// ---------------------------------------------------------------------------

Deno.test("POST brokers/connect api_key: seals with AAD; response has no secret", async () => {
  const store = freshStore();
  const secret = "PLAINTEXT-SECRET-MUST-NOT-ESCAPE";
  const { status, json } = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "api_key",
    key_id: "PKTEST",
    secret,
  });
  assertEquals(status, 200);
  assertEquals(json.fingerprint, await fingerprint(parseCredential({
    kind: "api_key",
    key_id: "PKTEST",
    secret,
  })));
  const blob = JSON.stringify(json);
  assertEquals(blob.includes(secret), false);
  assertEquals(blob.includes("ciphertext"), false);

  assertEquals(store.brokers.length, 1);
  const row = store.brokers[0]!;
  const aad = buildAad(WS_A, "alpaca", "paper");
  const ctHex = String(row.ciphertext).slice(2);
  const nonceHex = String(row.nonce).slice(2);
  const opened = await openBytes(
    { ciphertext: hexToBytes(ctHex), nonce: hexToBytes(nonceHex), key_id: "v1" },
    { aad, key: TEST_KEY },
  );
  const parsed = JSON.parse(new TextDecoder().decode(opened));
  assertEquals(parsed.secret, secret);
});

Deno.test("POST brokers/connect oauth: pins redirect_uri; rejects client mismatch", async () => {
  const store = freshStore();
  const mismatch = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "oauth",
    code: "auth-code-123",
    redirect_uri: "https://evil.example/callback",
  });
  assertEquals(mismatch.status, 400);
  assertEquals(mismatch.json.code, "REDIRECT_URI_MISMATCH");

  const ok = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "oauth",
    code: "auth-code-123",
    redirect_uri: pinnedAlpacaRedirectUri(APP_URL),
  });
  assertEquals(ok.status, 200);
  assertEquals(ok.json.auth_kind, "oauth");
  assertEquals(JSON.stringify(ok.json).includes("alpaca-access-token-xyz"), false);
});

Deno.test("POST brokers/connect reconnect: revoke-then-insert on active unique", async () => {
  const store = freshStore();
  const first = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "api_key",
    key_id: "PK1",
    secret: "secret-one",
  });
  assertEquals(first.status, 200);
  const firstId = first.json.id;

  const second = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "api_key",
    key_id: "PK2",
    secret: "secret-two",
  });
  assertEquals(second.status, 200);
  assertEquals(second.json.id !== firstId, true);

  const revoked = store.brokers.filter((b) => b.status === "revoked");
  const active = store.brokers.filter((b) => b.status === "active");
  assertEquals(revoked.length, 1);
  assertEquals(revoked[0]!.id, firstId);
  assertEquals(active.length, 1);
  assertEquals(active[0]!.id, second.json.id);
});

Deno.test("POST brokers/revoke: fails closed on unknown row", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "POST", "/brokers/revoke", {
    connection_id: "00000000-0000-4000-8000-000000000001",
  });
  assertEquals(status, 404);
  assertEquals(json.code, "CONNECTION_NOT_FOUND");
});

Deno.test("PATCH notifications: 503 NOT_READY until K5", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/notifications", {
    email: "pm@example.com",
    daily_digest: true,
  });
  assertEquals(status, 503);
  assertEquals(json.code, "NOT_READY");
});

// ---------------------------------------------------------------------------
// Vault helpers used by handlers
// ---------------------------------------------------------------------------

Deno.test("parseCredential never echoes secrets on failure", () => {
  const secret = "super-secret-value-do-not-leak";
  try {
    parseCredential({ kind: "api_key", key_id: "", secret });
    throw new Error("expected throw");
  } catch (err) {
    assertEquals(err instanceof VaultPayloadError, true);
    assertEquals(String(err).includes(secret), false);
  }
});

Deno.test("canonicalJson sorts keys and omits null refresh", () => {
  const oauth = parseCredential({ kind: "oauth", access_token: "tok" });
  const bytes = canonicalJson(oauth);
  assertEquals(new TextDecoder().decode(bytes), '{"access_token":"tok","kind":"oauth"}');
});

Deno.test("sealCredential called with AAD binding (workspace:broker:env)", async () => {
  const cred = parseCredential({
    kind: "api_key",
    key_id: "K",
    secret: "S",
  });
  const aad = buildAad(WS_A, "ibkr", "paper");
  const sealed = await sealCredential(cred, { aad, key: TEST_KEY });
  assertEquals(sealed.key_id, "v1");
  await assertRejects(
    () =>
      openBytes(sealed, {
        aad: buildAad("99999999-9999-4999-8999-999999999999", "ibkr", "paper"),
        key: TEST_KEY,
      }),
  );
});

Deno.test("pinnedAlpacaRedirectUri uses APP_URL + /olympus callback", () => {
  assertEquals(
    pinnedAlpacaRedirectUri("https://app.example"),
    "https://app.example/olympus/settings/brokers/callback/",
  );
});
