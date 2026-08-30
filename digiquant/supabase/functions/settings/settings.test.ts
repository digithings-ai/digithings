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
  keys: Array<Record<string, unknown>>;
  prefs: Array<Record<string, unknown>>;
  jobs: Array<Record<string, unknown>>;
  fills: Array<Record<string, unknown>>;
  notifyLog: Array<Record<string, unknown>>;
  /** Ops/creator plan floors keyed by lowercased email (migration 108). */
  entitlementGrants: Map<string, string>;
  /** Client product keys keyed by lowercased email. */
  productGrants: Map<string, string[]>;
  /** When true, notification_prefs lookups fail as if the table is missing. */
  prefsMissing?: boolean;
  /** When true, olympus_profile_config lookups fail as if the table is missing. */
  profilesMissing?: boolean;
  /** When true, workspace_provider_credentials lookups fail as if missing. */
  keysMissing?: boolean;
  /** When true, ensure_personal_workspace RPC fails (bootstrap disabled). */
  bootstrapDisabled?: boolean;
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
    keys: [],
    prefs: [],
    jobs: [],
    fills: [],
    notifyLog: [],
    entitlementGrants: new Map(),
    productGrants: new Map(),
  };
}

type Filter = { col: string; op: "eq" | "neq"; val: unknown };

function mockAdmin(store: Store): AdminClient {
  const makeBuilder = (table: string) => {
    const filters: Filter[] = [];
    let pendingInsert: Record<string, unknown> | null = null;
    let pendingUpdate: Record<string, unknown> | null = null;
    let pendingUpsert: Record<string, unknown> | null = null;
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
    api.upsert = (row: Record<string, unknown>, _opts?: unknown) => {
      pendingUpsert = row;
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
        if (store.profilesMissing) {
          return {
            data: null,
            error: { message: 'relation "olympus_profile_config" does not exist', code: "42P01" },
          };
        }
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

      if (table === "workspace_provider_credentials") {
        if (store.keysMissing) {
          return {
            data: null,
            error: {
              message: 'relation "workspace_provider_credentials" does not exist',
              code: "42P01",
            },
          };
        }
        if (pendingInsert) {
          const activeClash = store.keys.some(
            (k) =>
              k.workspace_id === pendingInsert!.workspace_id &&
              k.provider === pendingInsert!.provider &&
              k.status === "active",
          );
          if (activeClash) {
            return {
              data: null,
              error: {
                message:
                  "duplicate key value violates unique constraint uq_workspace_provider_credentials_active",
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
          store.keys.push(row);
          return {
            data: wantSingle || maybeSingle
              ? projectFp(row, selectCols)
              : [projectFp(row, selectCols)],
            error: null,
          };
        }
        if (pendingUpdate) {
          let rows = [...store.keys];
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
          return {
            data: maybeSingle || wantSingle
              ? projected
              : rows.map((r) => projectFp(r, selectCols)),
            error: null,
          };
        }
        let rows = [...store.keys];
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

      if (table === "notification_prefs") {
        if (store.prefsMissing) {
          return {
            data: null,
            error: { message: 'relation "notification_prefs" does not exist', code: "42P01" },
          };
        }
        if (pendingUpsert) {
          const email = String(pendingUpsert.email ?? "");
          if (!/^[^@]+@[^@]+\.[^@]+$/.test(email)) {
            return {
              data: null,
              error: { message: "new row violates check constraint notification_prefs_email_check", code: "23514" },
            };
          }
          const idx = store.prefs.findIndex(
            (p) => p.workspace_id === pendingUpsert!.workspace_id,
          );
          const row = {
            ...pendingUpsert,
            updated_at: new Date().toISOString(),
          };
          if (idx >= 0) store.prefs[idx] = row;
          else store.prefs.push(row);
          return {
            data: wantSingle || maybeSingle ? row : [row],
            error: null,
          };
        }
        let rows = [...store.prefs];
        for (const f of filters) {
          if (f.op === "eq") rows = rows.filter((r) => r[f.col] === f.val);
        }
        if (wantSingle || maybeSingle) {
          return { data: rows[0] ?? null, error: null };
        }
        return { data: rows, error: null };
      }

      if (table === "entitlement_grants") {
        const email = String(
          filters.find((f) => f.col === "email" && f.op === "eq")?.val ?? "",
        ).toLowerCase();
        const floor = store.entitlementGrants.get(email);
        const row = floor ? { email, plan_floor: floor } : null;
        if (wantSingle || maybeSingle) {
          return { data: row, error: null };
        }
        return { data: row ? [row] : [], error: null };
      }

      if (table === "client_product_grants") {
        const email = String(
          filters.find((f) => f.col === "email" && f.op === "eq")?.val ?? "",
        ).toLowerCase();
        const keys = store.productGrants.get(email) ?? [];
        const rows = keys.map((product_key) => ({ email, product_key }));
        if (wantSingle || maybeSingle) {
          return { data: rows[0] ?? null, error: null };
        }
        return { data: rows, error: null };
      }

      if (table === "job_runs" || table === "broker_executions" || table === "notification_log") {
        const source =
          table === "job_runs"
            ? store.jobs
            : table === "broker_executions"
            ? store.fills
            : store.notifyLog;
        let rows = [...source];
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

      return { data: null, error: { message: `unknown table ${table}` } };
    };

    api.then = (onFulfilled: (v: unknown) => unknown, onRejected?: (e: unknown) => unknown) =>
      run().then(onFulfilled, onRejected);

    return api;
  };

  return {
    from: (table: string) => makeBuilder(table),
    rpc: async (fn: string, args?: Record<string, unknown>) => {
      if (fn !== "ensure_personal_workspace") {
        return { data: null, error: { message: `unknown rpc ${fn}`, code: "PGRST202" } };
      }
      if (store.bootstrapDisabled) {
        return { data: null, error: { message: "bootstrap disabled", code: "P0001" } };
      }
      const userId = String(args?.p_user_id ?? "");
      if (!userId) {
        return { data: null, error: { message: "p_user_id required", code: "P0001" } };
      }
      const existing = store.members.find((m) => m.user_id === userId);
      if (existing) {
        return { data: existing.workspace_id, error: null };
      }
      const id = `bbbbbbbb-bbbb-4bbb-8bbb-${userId.replace(/-/g, "").slice(0, 12).padEnd(12, "0")}`;
      store.workspaces.set(id, wsRow(id, "free"));
      store.members.push({ workspace_id: id, user_id: userId, role: "owner" });
      return { data: id, error: null };
    },
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

Deno.test("403 WORKSPACE_FORBIDDEN when bootstrap RPC fails", async () => {
  const store = freshStore();
  store.bootstrapDisabled = true;
  const { status, json } = await call(store, "GET", "/brokers", undefined, {
    userId: "99999999-9999-4999-8999-999999999999",
  });
  assertEquals(status, 403);
  assertEquals(json.code, "WORKSPACE_FORBIDDEN");
});

Deno.test("GET brokers: auto-bootstraps personal workspace for new Auth user", async () => {
  const store = freshStore();
  const newUser = "99999999-9999-4999-8999-999999999999";
  assertEquals(store.members.filter((m) => m.user_id === newUser).length, 0);
  const { status, json } = await call(store, "GET", "/brokers", undefined, {
    userId: newUser,
  });
  assertEquals(status, 200);
  assertEquals(Array.isArray(json.connections), true);
  assertEquals(store.members.filter((m) => m.user_id === newUser).length, 1);
  assertEquals(store.members.find((m) => m.user_id === newUser)?.role, "owner");
  const wsId = store.members.find((m) => m.user_id === newUser)!.workspace_id;
  assertEquals(store.workspaces.get(wsId)?.plan_tier, "free");
});

Deno.test("GET profile: auto-bootstraps then returns empty contract", async () => {
  const store = freshStore();
  const newUser = "88888888-8888-4888-8888-888888888888";
  const { status, json } = await call(store, "GET", "/profile", undefined, {
    userId: newUser,
  });
  assertEquals(status, 200);
  assertEquals(json.profile_key, "workspace");
  assertEquals(json.version_id, null);
  assertEquals(store.members.filter((m) => m.user_id === newUser).length, 1);
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

Deno.test(
  "creator entitlement_grants elevates free workspace to allow profile write",
  async () => {
    const store = freshStore();
    store.workspaces.set(WS_A, wsRow(WS_A, "free"));
    store.entitlementGrants.set("owner@example.com", "custom");
    store.productGrants.set("owner@example.com", ["fx_hub"]);
    const { status, json } = await call(store, "PATCH", "/profile", {
      profile_key: "workspace",
      label: "Creator overlay",
      investment: validInvestment,
    }, { planTier: "free" });
    assertEquals(status, 200, JSON.stringify(json));
    assertEquals(json.label, "Creator overlay");
    assertEquals(store.profiles.length, 1);
  },
);

Deno.test("403 TIER_FORBIDDEN for baseline on broker connect", async () => {
  const store = freshStore();
  store.workspaces.set(WS_A, wsRow(WS_A, "baseline"));
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

Deno.test(
  "403 TIER_FORBIDDEN when workspace is free but JWT claim is still custom (stale claim after cancel)",
  async () => {
    const store = freshStore();
    store.workspaces.set(WS_A, wsRow(WS_A, "free"));
    store.workspaces.get(WS_A)!.claim_sync_pending = true;
    const profile = await call(store, "PATCH", "/profile", {
      profile_key: "ws-overlay",
      label: "Should not write",
      investment: validInvestment,
    }, { planTier: "custom" });
    assertEquals(profile.status, 403);
    assertEquals(profile.json.code, "TIER_FORBIDDEN");
    assertEquals(store.profiles.length, 0);

    const connect = await call(store, "POST", "/brokers/connect", {
      broker: "alpaca",
      env: "paper",
      kind: "api_key",
      key_id: "PK",
      secret: "sec",
    }, { planTier: "custom" });
    assertEquals(connect.status, 403);
    assertEquals(connect.json.code, "TIER_FORBIDDEN");
    assertEquals(store.brokers.length, 0);
  },
);

Deno.test(
  "allows custom workspace when JWT claim lags at free (stale claim after upgrade)",
  async () => {
    const store = freshStore();
    store.workspaces.set(WS_A, wsRow(WS_A, "custom"));
    store.workspaces.get(WS_A)!.claim_sync_pending = true;
    const { status, json } = await call(store, "PATCH", "/profile", {
      profile_key: "ws-overlay",
      label: "Lagging claim OK",
      investment: validInvestment,
    }, { planTier: "free" });
    assertEquals(status, 200);
    assertEquals(json.workspace_id, WS_A);
    assertEquals(store.profiles.length, 1);
  },
);

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

Deno.test(
  "POST brokers/connect: crypto.randomUUID bound when deps.uuid omitted (Edge TypeError regression)",
  async () => {
    // Production createDefaultDeps does not inject uuid. Unbound
    // `(crypto.randomUUID)()` throws TypeError "expected Crypto" on Deno/Edge.
    const store = freshStore();
    const secret = "EDGE-UUID-BIND-SECRET";
    const res = await handleSettingsRequest(
      authReq("POST", "/brokers/connect", {
        broker: "alpaca",
        env: "paper",
        kind: "api_key",
        key_id: "PKTEST",
        secret,
      }),
      {
        admin: mockAdmin(store),
        user: { id: USER_A, email: "owner@example.com", plan_tier: "custom" },
        vaultKey: TEST_KEY,
        appUrl: APP_URL,
      },
    );
    const json = await res.json();
    assertEquals(res.status, 200);
    assertEquals(typeof json.id, "string");
    assertEquals((json.id as string).length, 36);
    assertEquals(store.brokers.length, 1);
    assertEquals(JSON.stringify(json).includes(secret), false);
  },
);

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

Deno.test("POST brokers/connect oauth: OAUTH_NOT_CONFIGURED when Alpaca client secrets missing", async () => {
  const store = freshStore();
  Deno.env.delete("ALPACA_OAUTH_CLIENT_ID");
  Deno.env.delete("NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID");
  Deno.env.delete("ALPACA_OAUTH_CLIENT_SECRET");
  const res = await handleSettingsRequest(
    authReq("POST", "/brokers/connect", {
      broker: "alpaca",
      env: "paper",
      kind: "oauth",
      code: "auth-code-no-secrets",
      redirect_uri: pinnedAlpacaRedirectUri(APP_URL),
    }),
    {
      admin: mockAdmin(store),
      user: { id: USER_A, email: "owner@example.com", plan_tier: "custom" },
      vaultKey: TEST_KEY,
      appUrl: APP_URL,
      // Intentionally omit exchangeAlpacaCode → production default path.
    },
  );
  const json = await res.json();
  assertEquals(res.status, 500);
  assertEquals(json.code, "OAUTH_NOT_CONFIGURED");
  assertEquals(String(json.message).includes("ALPACA_OAUTH_CLIENT_ID"), true);
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

Deno.test("GET profile: empty contract — 200 defaults, version_id null, no write", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", "/profile");
  assertEquals(status, 200);
  assertEquals(json.workspace_id, WS_A);
  assertEquals(json.profile_key, "workspace");
  assertEquals(json.version_id, null);
  assertEquals(json.recorded_at, null);
  assertEquals(json.label, "");
  assertEquals(json.investment, null);
  assertEquals(json.assets, null);
  assertEquals(store.profiles.length, 0);
});

Deno.test("GET profile: returns tip for workspace member", async () => {
  const store = freshStore();
  store.profiles.push({
    id: "tip-v1",
    workspace_id: WS_A,
    profile_key: "workspace",
    schema_version: 1,
    is_house_default: false,
    label: "My overlay",
    supersedes_id: null,
    recorded_at: "2026-08-30T12:00:00Z",
    payload: {
      version_id: "tip-v1",
      profile_key: "workspace",
      label: "My overlay",
      investment: validInvestment,
      assets: { schema_version: 1, excluded_tickers: ["XYZ"] },
    },
  });
  const { status, json } = await call(store, "GET", "/profile");
  assertEquals(status, 200);
  assertEquals(json.version_id, "tip-v1");
  assertEquals(json.label, "My overlay");
  assertEquals(json.profile_key, "workspace");
  assertEquals((json.investment as { risk_tolerance: string }).risk_tolerance, "moderate");
  assertEquals((json.assets as { excluded_tickers: string[] }).excluded_tickers[0], "XYZ");
});

Deno.test("GET profile: house profile_key rejected", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", "/profile?profile_key=house");
  assertEquals(status, 400);
  assertEquals(json.code, "HOUSE_KEY_FORBIDDEN");
});

Deno.test("GET profile: 503 when olympus_profile_config missing", async () => {
  const store = freshStore();
  store.profilesMissing = true;
  const { status, json } = await call(store, "GET", "/profile");
  assertEquals(status, 503);
  assertEquals(json.code, "NOT_READY");
});

Deno.test("GET profile: wrong workspace is forbidden", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", `/profile?workspace_id=${WS_B}`);
  assertEquals(status, 403);
  assertEquals(json.code, "WORKSPACE_FORBIDDEN");
});

Deno.test("GET notifications: returns row for workspace member", async () => {
  const store = freshStore();
  store.prefs.push({
    workspace_id: WS_A,
    email: "pm@example.com",
    daily_digest: true,
    holding_change_alerts: false,
    execution_alerts: true,
    digest_hour_utc: 9,
    updated_at: "2026-01-01T00:00:00Z",
  });
  const { status, json } = await call(store, "GET", "/notifications");
  assertEquals(status, 200);
  assertEquals(json.workspace_id, WS_A);
  assertEquals(json.email, "pm@example.com");
  assertEquals(json.daily_digest, true);
  assertEquals(json.execution_alerts, true);
  assertEquals(json.digest_hour_utc, 9);
  assertEquals(json.updated_at, "2026-01-01T00:00:00Z");
  assertEquals(store.prefs.length, 1);
});

Deno.test("GET notifications: empty contract — 200 defaults, updated_at null, no write", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", "/notifications");
  assertEquals(status, 200);
  assertEquals(json.workspace_id, WS_A);
  assertEquals(json.email, "owner@example.com");
  assertEquals(json.daily_digest, false);
  assertEquals(json.holding_change_alerts, false);
  assertEquals(json.execution_alerts, false);
  assertEquals(json.digest_hour_utc, 12);
  assertEquals(json.updated_at, null);
  assertEquals(store.prefs.length, 0);
});

Deno.test("GET notifications: 503 when notification_prefs missing", async () => {
  const store = freshStore();
  store.prefsMissing = true;
  const { status, json } = await call(store, "GET", "/notifications");
  assertEquals(status, 503);
  assertEquals(json.code, "NOT_READY");
});

Deno.test("GET notifications: wrong workspace is forbidden", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", `/notifications?workspace_id=${WS_B}`);
  assertEquals(status, 403);
  assertEquals(json.code, "WORKSPACE_FORBIDDEN");
});

Deno.test("PATCH notifications: upserts prefs for workspace member", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/notifications", {
    email: "pm@example.com",
    daily_digest: true,
    holding_change_alerts: false,
    execution_alerts: true,
    digest_hour_utc: 9,
  });
  assertEquals(status, 200);
  assertEquals(json.workspace_id, WS_A);
  assertEquals(json.email, "pm@example.com");
  assertEquals(json.daily_digest, true);
  assertEquals(json.execution_alerts, true);
  assertEquals(json.digest_hour_utc, 9);
  assertEquals(store.prefs.length, 1);
});

Deno.test("PATCH notifications: rejects invalid email", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/notifications", {
    email: "not-an-email",
    daily_digest: true,
  });
  assertEquals(status, 400);
  assertEquals(json.code, "INVALID_EMAIL");
});

Deno.test("PATCH notifications: rejects digest_hour_utc out of range", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/notifications", {
    email: "pm@example.com",
    digest_hour_utc: 24,
  });
  assertEquals(status, 400);
  assertEquals(json.code, "INVALID_DIGEST_HOUR");
});

Deno.test("PATCH notifications: 503 when notification_prefs missing", async () => {
  const store = freshStore();
  store.prefsMissing = true;
  const { status, json } = await call(store, "PATCH", "/notifications", {
    email: "pm@example.com",
    daily_digest: true,
  });
  assertEquals(status, 503);
  assertEquals(json.code, "NOT_READY");
});

Deno.test("PATCH notifications: partial update merges prior row", async () => {
  const store = freshStore();
  store.prefs.push({
    workspace_id: WS_A,
    email: "old@example.com",
    daily_digest: true,
    holding_change_alerts: true,
    execution_alerts: false,
    digest_hour_utc: 12,
    updated_at: "2026-01-01T00:00:00Z",
  });
  const { status, json } = await call(store, "PATCH", "/notifications", {
    execution_alerts: true,
  });
  assertEquals(status, 200);
  assertEquals(json.email, "old@example.com");
  assertEquals(json.daily_digest, true);
  assertEquals(json.holding_change_alerts, true);
  assertEquals(json.execution_alerts, true);
  assertEquals(json.digest_hour_utc, 12);
});

Deno.test("PATCH notifications: wrong workspace is forbidden", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/notifications", {
    workspace_id: WS_B,
    email: "pm@example.com",
  });
  assertEquals(status, 403);
  assertEquals(json.code, "WORKSPACE_FORBIDDEN");
});

// ---------------------------------------------------------------------------
// Vault helpers used by handlers
// ---------------------------------------------------------------------------

Deno.test("403 TIER_FORBIDDEN for baseline on keys connect", async () => {
  const store = freshStore();
  store.workspaces.set(WS_A, wsRow(WS_A, "baseline"));
  const { status, json } = await call(store, "POST", "/keys/connect", {
    provider: "openai",
    kind: "api_key",
    secret: "sk-test-baseline-blocked",
  });
  assertEquals(status, 403);
  assertEquals(json.code, "TIER_FORBIDDEN");
  assertEquals(store.keys.length, 0);
});

Deno.test("PATCH profile: persists watchlist/themes/research_budget_usd", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/profile", {
    profile_key: "workspace",
    label: "Overlay A",
    watchlist: ["aapl", "MSFT", "aapl"],
    themes: ["AI", "ai", "Energy"],
    research_budget_usd: 12.5,
  });
  assertEquals(status, 200);
  assertEquals(typeof json.version_id, "string");
  const tip = store.profiles[0]!;
  const payload = tip.payload as Record<string, unknown>;
  assertEquals(payload.watchlist, ["AAPL", "MSFT"]);
  assertEquals(payload.themes, ["ai", "energy"]);
  assertEquals(payload.research_budget_usd, 12.5);

  const got = await call(store, "GET", "/profile");
  assertEquals(got.status, 200);
  assertEquals(got.json.watchlist, ["AAPL", "MSFT"]);
  assertEquals(got.json.themes, ["ai", "energy"]);
  assertEquals(got.json.research_budget_usd, 12.5);
});

Deno.test("PATCH profile: rejects negative research_budget_usd", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "PATCH", "/profile", {
    profile_key: "workspace",
    label: "Overlay A",
    research_budget_usd: -1,
  });
  assertEquals(status, 400);
  assertEquals(json.code, "INVALID_BUDGET");
});

Deno.test("POST keys/connect: seals with AAD workspace:provider:llm; no secret in response", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "POST", "/keys/connect", {
    provider: "openai",
    kind: "api_key",
    key_id: "user",
    secret: "sk-live-never-echo",
  });
  assertEquals(status, 200);
  assertEquals(json.provider, "openai");
  assertEquals(typeof json.fingerprint, "string");
  assertEquals((json.fingerprint as string).length, 8);
  assertEquals(json.status, "active");
  const blob = JSON.stringify(json);
  assertEquals(blob.includes("sk-live-never-echo"), false);
  assertEquals(blob.includes("ciphertext"), false);
  assertEquals(store.keys.length, 1);
  const row = store.keys[0]!;
  assertEquals(typeof row.ciphertext, "string");
  assertEquals(String(row.ciphertext).startsWith("\\x"), true);

  const aad = buildAad(WS_A, "openai", "llm");
  const sealed = {
    ciphertext: hexToBytes(String(row.ciphertext).slice(2)),
    nonce: hexToBytes(String(row.nonce).slice(2)),
    key_id: String(row.key_id),
  };
  const opened = await openBytes(sealed, { aad, key: TEST_KEY });
  const openedText = new TextDecoder().decode(opened);
  assertEquals(openedText.includes("sk-live-never-echo"), true);
});

Deno.test("POST keys/connect reconnect: revoke-then-insert on active unique", async () => {
  const store = freshStore();
  const first = await call(store, "POST", "/keys/connect", {
    provider: "groq",
    secret: "sk-first",
  });
  assertEquals(first.status, 200);
  const second = await call(store, "POST", "/keys/connect", {
    provider: "groq",
    secret: "sk-second",
  });
  assertEquals(second.status, 200);
  assertEquals(store.keys.filter((k) => k.status === "active").length, 1);
  assertEquals(store.keys.filter((k) => k.status === "revoked").length, 1);
  assertEquals(second.json.fingerprint !== first.json.fingerprint, true);
});

Deno.test("POST keys/revoke: fails closed on unknown row", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "POST", "/keys/revoke", {
    credential_id: "00000000-0000-4000-8000-000000000099",
  });
  assertEquals(status, 404);
  assertEquals(json.code, "CREDENTIAL_NOT_FOUND");
});

Deno.test("GET keys: 503 when workspace_provider_credentials missing", async () => {
  const store = freshStore();
  store.keysMissing = true;
  const { status, json } = await call(store, "GET", "/keys");
  assertEquals(status, 503);
  assertEquals(json.code, "NOT_READY");
});

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
  assertEquals(
    pinnedAlpacaRedirectUri("https://app.example/olympus"),
    "https://app.example/olympus/settings/brokers/callback/",
  );
});

Deno.test("GET profile: includes workspace billing snapshot without Stripe ids", async () => {
  const store = freshStore();
  store.workspaces.set(WS_A, {
    ...wsRow(WS_A, "free"),
    subscription_status: "none",
    stripe_customer_id: "cus_secret",
    stripe_subscription_id: "sub_secret",
  });
  const { status, json } = await call(store, "GET", "/profile");
  assertEquals(status, 200);
  assertEquals(json.plan_tier, "free");
  assertEquals(json.subscription_status, "none");
  assertEquals(json.has_stripe_subscription, true);
  assertEquals(json.stripe_customer_id, undefined);
  assertEquals(json.stripe_subscription_id, undefined);
});

Deno.test("GET /jobs: member lists overlay job_runs; other workspace isolated", async () => {
  const store = freshStore();
  store.jobs.push({
    id: "job-a",
    workspace_id: WS_A,
    job_type: "overlay_daily",
    status: "succeeded",
    error: null,
    idempotency_key: `${WS_A}:overlay_daily:2026-08-31`,
    started_at: "2026-08-31T00:00:00Z",
    finished_at: "2026-08-31T00:01:00Z",
  });
  store.jobs.push({
    id: "job-b",
    workspace_id: WS_B,
    job_type: "overlay_daily",
    status: "succeeded",
    error: null,
    idempotency_key: `${WS_B}:overlay_daily:2026-08-31`,
    started_at: "2026-08-31T00:00:00Z",
    finished_at: "2026-08-31T00:01:00Z",
  });
  const { status, json } = await call(store, "GET", "/jobs");
  assertEquals(status, 200);
  const jobs = json.jobs as Array<Record<string, unknown>>;
  assertEquals(jobs.length, 1);
  assertEquals(jobs[0]!.id, "job-a");
  assertEquals(jobs[0]!.job_type, "overlay_daily");
  assertEquals(jobs[0]!.status, "succeeded");
});

Deno.test("GET /fills: member lists broker_executions fingerprints", async () => {
  const store = freshStore();
  store.fills.push({
    id: "fill-a",
    workspace_id: WS_A,
    symbol: "AAPL",
    quantity: 1,
    executed_at: "2026-08-31T14:00:00Z",
    recorded_at: "2026-08-31T14:00:01Z",
    external_fill_id: "ext-secret",
  });
  store.fills.push({
    id: "fill-b",
    workspace_id: WS_B,
    symbol: "MSFT",
    quantity: 2,
    executed_at: "2026-08-31T14:00:00Z",
    recorded_at: "2026-08-31T14:00:01Z",
    external_fill_id: "other",
  });
  const { status, json } = await call(store, "GET", "/fills");
  assertEquals(status, 200);
  const fills = json.fills as Array<Record<string, unknown>>;
  assertEquals(fills.length, 1);
  assertEquals(fills[0]!.symbol, "AAPL");
  assertEquals(fills[0]!.external_fill_id, undefined);
});

Deno.test("GET /notifications/log: member lists digest event keys only", async () => {
  const store = freshStore();
  store.notifyLog.push({
    workspace_id: WS_A,
    event_key: "digest:2026-08-31",
    sent_date: "2026-08-31",
    sent_at: "2026-08-31T12:00:00Z",
  });
  store.notifyLog.push({
    workspace_id: WS_B,
    event_key: "digest:2026-08-31",
    sent_date: "2026-08-31",
    sent_at: "2026-08-31T12:00:00Z",
  });
  const { status, json } = await call(store, "GET", "/notifications/log");
  assertEquals(status, 200);
  const events = json.events as Array<Record<string, unknown>>;
  assertEquals(events.length, 1);
  assertEquals(events[0]!.event_key, "digest:2026-08-31");
});

Deno.test("GET /app-urls: pinned Alpaca + billing return under /olympus", async () => {
  const store = freshStore();
  const { status, json } = await call(store, "GET", "/app-urls");
  assertEquals(status, 200);
  assertEquals(
    json.alpaca_redirect_uri,
    "https://app.example/olympus/settings/brokers/callback/",
  );
  assertEquals(
    json.billing_return_url,
    "https://app.example/olympus/settings/?tab=billing",
  );
});
