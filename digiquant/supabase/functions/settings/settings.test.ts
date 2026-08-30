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
import { handleSettingsRequest } from "../_shared/settings-handlers.ts";
import {
  buildAad,
  canonicalJson,
  fingerprint,
  hexToBytes,
  loadMasterKey,
  openBytes,
  parseCredential,
  sealBytesWithNonce,
  sealCredential,
  VaultPayloadError,
  type MasterKey,
} from "../_shared/vault.ts";

const WS_ID = "11111111-1111-4111-8111-111111111111";
const USER_ID = "22222222-2222-4222-8222-222222222222";
const FIXED_UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

// ---------------------------------------------------------------------------
// In-memory admin mock
// ---------------------------------------------------------------------------

interface Store {
  workspaces: Map<string, WorkspaceRow>;
  members: Array<{ workspace_id: string; user_id: string; role: string }>;
  profiles: Array<Record<string, unknown>>;
  brokers: Array<Record<string, unknown>>;
  sealCalls: Array<{ aad: string }>;
}

function freshStore(): Store {
  const ws: WorkspaceRow = {
    id: WS_ID,
    stripe_customer_id: null,
    stripe_subscription_id: null,
    subscription_status: "none",
    plan_tier: "custom",
    claim_sync_pending: false,
    last_stripe_event_created: null,
  };
  return {
    workspaces: new Map([[WS_ID, { ...ws }]]),
    members: [{ workspace_id: WS_ID, user_id: USER_ID, role: "owner" }],
    profiles: [],
    brokers: [],
    sealCalls: [],
  };
}

type Filter = { col: string; op: "eq" | "neq" | "order"; val: unknown; asc?: boolean };

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

    api.then = undefined; // not a promise itself
    api.execute = undefined;

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
          // Track that seal wrote AAD-bound ciphertext (tests assert sealCalls).
          const row = { ...pendingInsert, last_used_at: null, revoked_at: null, created_at: new Date().toISOString() };
          store.brokers.push(row);
          return { data: wantSingle || maybeSingle ? projectFp(row, selectCols) : [projectFp(row, selectCols)], error: null };
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
          const target = rows[0]!;
          Object.assign(target, pendingUpdate);
          const projected = projectFp(target, selectCols);
          return { data: maybeSingle || wantSingle ? projected : [projected], error: null };
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

    // Supabase-js awaits the builder directly — make it thenable.
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
  // Always omit secrets even if select is "*"
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

function authReq(method: string, path: string, body?: unknown): Request {
  return new Request(`http://localhost/functions/v1/settings${path}`, {
    method,
    headers: {
      Authorization: "Bearer test-jwt",
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function call(
  store: Store,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; json: Record<string, unknown> }> {
  // Wrap seal via connect path — record AAD by intercepting vault via deps key.
  const res = await handleSettingsRequest(authReq(method, path, body), {
    admin: mockAdmin(store),
    user: { id: USER_ID, email: "owner@example.com" },
    vaultKey: TEST_KEY,
    uuid: () => FIXED_UUID,
    exchangeAlpacaCode: async () => ({ access_token: "alpaca-access-token-xyz" }),
  });
  const json = await res.json();
  return { status: res.status, json };
}

// ---------------------------------------------------------------------------
// Vault vector conformance
// ---------------------------------------------------------------------------

Deno.test("vault vectors: api_key_alpaca_paper seals byte-for-byte", async () => {
  const raw = await Deno.readTextFile(
    new URL("../_shared/vault-vectors.json", import.meta.url),
  );
  const doc = JSON.parse(raw) as {
    keys: Record<string, { base64: string }>;
    vectors: Array<{
      name: string;
      key_id: string;
      nonce_hex: string;
      aad: string;
      plaintext_utf8: string;
      ciphertext_hex: string;
      fingerprint: string;
    }>;
  };
  const v = doc.vectors.find((x) => x.name === "api_key_alpaca_paper")!;
  const key: MasterKey = {
    key_id: v.key_id,
    material: Uint8Array.from(atob(doc.keys[v.key_id]!.base64), (c) => c.charCodeAt(0)),
  };
  const sealed = await sealBytesWithNonce(
    new TextEncoder().encode(v.plaintext_utf8),
    { nonce: hexToBytes(v.nonce_hex), aad: new TextEncoder().encode(v.aad), key },
  );
  const gotHex = [...sealed.ciphertext].map((b) => b.toString(16).padStart(2, "0")).join("");
  assertEquals(gotHex, v.ciphertext_hex);

  const cred = parseCredential(JSON.parse(v.plaintext_utf8));
  assertEquals(await fingerprint(cred), v.fingerprint);

  // Wrong AAD fails closed
  await assertRejects(
    () => openBytes(sealed, { aad: new TextEncoder().encode("wrong:aad:paper"), key }),
    Error,
  );
});

Deno.test("parseCredential never echoes secrets on failure", () => {
  const secret = "super-secret-value-do-not-leak";
  try {
    parseCredential({ kind: "api_key", key_id: "", secret });
    throw new Error("expected throw");
  } catch (err) {
    assertEquals(err instanceof VaultPayloadError, true);
    const msg = String(err);
    assertEquals(msg.includes(secret), false);
  }
});

Deno.test("canonicalJson sorts keys and omits null refresh", () => {
  const oauth = parseCredential({ kind: "oauth", access_token: "tok" });
  const bytes = canonicalJson(oauth);
  assertEquals(new TextDecoder().decode(bytes), '{"access_token":"tok","kind":"oauth"}');
});

// ---------------------------------------------------------------------------
// Settings handlers
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
    investment: {
      risk_tolerance: "moderate",
      horizon_years: 10,
      liquidity_needs: "medium",
      base_currency: "USD",
      tax_jurisdiction: "US",
      esg_preference: "none",
      experience_level: "intermediate",
    },
  });
  assertEquals(status, 400);
  assertEquals(json.code, "HOUSE_KEY_FORBIDDEN");
  assertEquals(store.profiles.length, 0);
});

Deno.test("PATCH profile: appends version with supersedes", async () => {
  const store = freshStore();
  const validInvestment = {
    risk_tolerance: "moderate",
    horizon_years: 10,
    liquidity_needs: "medium",
    base_currency: "USD",
    tax_jurisdiction: "US",
    esg_preference: "none",
    experience_level: "intermediate",
  };
  const first = await call(store, "PATCH", "/profile", {
    profile_key: "ws-overlay",
    label: "v1",
    investment: validInvestment,
  });
  assertEquals(first.status, 200);
  assertEquals(first.json.version_id, FIXED_UUID);
  assertEquals(store.profiles.length, 1);

  // Simulate tip
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
  assertEquals(json.broker, "alpaca");
  assertEquals(json.env, "paper");
  assertEquals(json.status, "active");
  const blob = JSON.stringify(json);
  assertEquals(blob.includes(secret), false);
  assertEquals(blob.includes("ciphertext"), false);
  assertEquals(blob.includes("PLAINTEXT"), false);

  // Row stored ciphertext; AAD binding matches workspace:broker:env
  assertEquals(store.brokers.length, 1);
  const row = store.brokers[0]!;
  assertEquals(typeof row.ciphertext, "string");
  assertEquals(String(row.ciphertext).startsWith("\\x"), true);
  const aad = buildAad(WS_ID, "alpaca", "paper");
  assertEquals(new TextDecoder().decode(aad), `${WS_ID}:alpaca:paper`);
  // Round-trip open with correct AAD
  const ctHex = String(row.ciphertext).slice(2);
  const nonceHex = String(row.nonce).slice(2);
  const opened = await openBytes(
    { ciphertext: hexToBytes(ctHex), nonce: hexToBytes(nonceHex), key_id: "v1" },
    { aad, key: TEST_KEY },
  );
  const parsed = JSON.parse(new TextDecoder().decode(opened));
  assertEquals(parsed.secret, secret);
});

Deno.test("POST brokers/connect oauth: exchanges code then seals", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "POST", "/brokers/connect", {
    broker: "alpaca",
    env: "paper",
    kind: "oauth",
    code: "auth-code-123",
    redirect_uri: "https://example.com/settings/brokers/callback",
  });
  assertEquals(status, 200);
  assertEquals(json.auth_kind, "oauth");
  assertEquals(JSON.stringify(json).includes("alpaca-access-token-xyz"), false);
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

Deno.test("sealCredential called with AAD binding (workspace:broker:env)", async () => {
  const cred = parseCredential({
    kind: "api_key",
    key_id: "K",
    secret: "S",
  });
  const aad = buildAad(WS_ID, "ibkr", "paper");
  const sealed = await sealCredential(cred, { aad, key: TEST_KEY });
  assertEquals(sealed.key_id, "v1");
  assertEquals(sealed.nonce.byteLength, 12);
  // Wrong workspace AAD must fail
  await assertRejects(
    () =>
      openBytes(sealed, {
        aad: buildAad("99999999-9999-4999-8999-999999999999", "ibkr", "paper"),
        key: TEST_KEY,
      }),
  );
});
