/**
 * Settings Edge Function handlers (T3) — extracted for Deno unit tests.
 *
 * Routes (mounted under /functions/v1/settings):
 *   PATCH  /profile            — versioned olympus_profile_config append
 *   GET    /brokers            — list fingerprints only
 *   POST   /brokers/connect    — api_key | oauth (Alpaca code exchange server-side)
 *   POST   /brokers/revoke     — mark revoked (fail closed on unknown)
 *   PATCH  /notifications      — 503 NOT_READY until K5 lands notification_prefs
 */

import {
  requireBearerHeader,
  requireWorkspaceMember,
  type AuthUser,
} from "./billing-auth.ts";
import {
  HOUSE_PROFILE_KEY,
  validateAssetPreferences,
  validateInvestmentProfile,
} from "./profile-schemas.ts";
import {
  createAdminClient,
  jsonError,
  jsonOk,
  type AdminClient,
} from "./supabase-admin.ts";
import {
  buildAad,
  encodeBytea,
  fingerprint,
  parseCredential,
  sealCredential,
  VaultPayloadError,
  type BrokerCredential,
  type MasterKey,
} from "./vault.ts";

export type SettingsDeps = {
  admin: AdminClient;
  user: AuthUser;
  /** Injected vault master key (tests); production loads from env. */
  vaultKey?: MasterKey;
  /** Alpaca OAuth token exchange (tests mock). */
  exchangeAlpacaCode?: (args: {
    code: string;
    redirectUri: string;
  }) => Promise<{ access_token: string; refresh_token?: string }>;
  /** crypto.randomUUID override for deterministic tests. */
  uuid?: () => string;
  now?: () => Date;
};

const FINGERPRINT_COLUMNS =
  "id, workspace_id, broker, env, auth_kind, fingerprint, scopes, status, created_at, revoked_at, last_used_at";

function pathOf(url: URL): string {
  // Supabase mounts at /settings or /functions/v1/settings — strip both prefixes.
  let p = url.pathname.replace(/\/+$/, "");
  const markers = ["/functions/v1/settings", "/settings"];
  for (const m of markers) {
    const idx = p.indexOf(m);
    if (idx >= 0) {
      p = p.slice(idx + m.length) || "/";
      break;
    }
  }
  if (!p.startsWith("/")) p = `/${p}`;
  return p === "" ? "/" : p;
}

export async function handleSettingsRequest(
  req: Request,
  deps: SettingsDeps,
): Promise<Response> {
  const authHeader = req.headers.get("Authorization");
  const missing = requireBearerHeader(authHeader);
  if (missing) return missing;

  const url = new URL(req.url);
  const path = pathOf(url);
  const method = req.method.toUpperCase();

  if (method === "PATCH" && path === "/profile") {
    return patchProfile(req, deps);
  }
  if (method === "GET" && (path === "/brokers" || path === "/brokers/")) {
    return listBrokers(req, deps);
  }
  if (method === "POST" && path === "/brokers/connect") {
    return connectBroker(req, deps);
  }
  if (method === "POST" && path === "/brokers/revoke") {
    return revokeBroker(req, deps);
  }
  if (method === "PATCH" && path === "/notifications") {
    return patchNotifications();
  }
  return jsonError(404, "NOT_FOUND", "Unknown settings route");
}

async function resolveMember(
  req: Request,
  deps: SettingsDeps,
  bodyWorkspaceId: string | null,
) {
  return requireWorkspaceMember(deps.admin, deps.user, bodyWorkspaceId);
}

async function patchProfile(req: Request, deps: SettingsDeps): Promise<Response> {
  let body: {
    workspace_id?: string;
    profile_key?: string;
    label?: string;
    investment?: unknown;
    assets?: unknown;
    expected_version_id?: string | null;
    supersedes_id?: string | null;
    watchlist?: string[];
    themes?: string[];
  };
  try {
    body = await req.json();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const authz = await resolveMember(req, deps, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const profileKey = (body.profile_key ?? "").trim();
  if (!profileKey) {
    return jsonError(400, "INVALID_PROFILE_KEY", "profile_key is required");
  }
  if (profileKey === HOUSE_PROFILE_KEY) {
    return jsonError(
      400,
      "HOUSE_KEY_FORBIDDEN",
      "overlay ProfileConfig cannot use the reserved house profile_key",
    );
  }
  if (profileKey.length > 100) {
    return jsonError(400, "INVALID_PROFILE_KEY", "profile_key too long");
  }

  const label = (body.label ?? "").trim();
  if (!label || label.length > 200) {
    return jsonError(400, "INVALID_LABEL", "label is required (1..200 chars)");
  }

  if (body.investment !== undefined && body.investment !== null) {
    const inv = validateInvestmentProfile(body.investment);
    if (!inv.ok) {
      return jsonError(400, "SCHEMA_INVALID", inv.errors[0]?.message ?? "invalid investment");
    }
  }
  if (body.assets !== undefined && body.assets !== null) {
    const assets = validateAssetPreferences(body.assets);
    if (!assets.ok) {
      return jsonError(400, "SCHEMA_INVALID", assets.errors[0]?.message ?? "invalid assets");
    }
  }

  const expected =
    body.expected_version_id ?? body.supersedes_id ?? null;

  // Optimistic concurrency: when a last-seen version is provided, it must still
  // be the tip for this profile_key (no newer superseding row).
  if (expected) {
    const { data: tip, error: tipErr } = await deps.admin
      .from("olympus_profile_config")
      .select("id, supersedes_id")
      .eq("profile_key", profileKey)
      .eq("is_house_default", false)
      .order("recorded_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (tipErr) {
      return jsonError(500, "PROFILE_LOOKUP_FAILED", "Unable to load profile tip");
    }
    if (tip && tip.id !== expected) {
      // Also accept when expected is the tip's supersedes chain head and tip is expected
      // — mismatch means another writer landed first.
      return jsonError(
        409,
        "VERSION_CONFLICT",
        "profile changed elsewhere — reload",
      );
    }
    if (!tip && expected) {
      // Client thinks there is a tip but none exists yet — still conflict if they
      // sent a non-null expected that isn't found as a row at all.
      const { data: row } = await deps.admin
        .from("olympus_profile_config")
        .select("id")
        .eq("id", expected)
        .maybeSingle();
      if (!row) {
        return jsonError(
          409,
          "VERSION_CONFLICT",
          "profile changed elsewhere — reload",
        );
      }
    }
  }

  const versionId = (deps.uuid ?? crypto.randomUUID)();
  const payload = {
    version_id: versionId,
    profile_key: profileKey,
    schema_version: 1,
    is_house_default: false,
    label,
    watchlist: body.watchlist ?? [],
    themes: body.themes ?? [],
    research_budget_usd: null,
    investment: body.investment ?? null,
    assets: body.assets ?? null,
  };

  const { data: inserted, error: insertErr } = await deps.admin
    .from("olympus_profile_config")
    .insert({
      id: versionId,
      profile_key: profileKey,
      schema_version: 1,
      is_house_default: false,
      label,
      payload,
      supersedes_id: expected,
    })
    .select("id, profile_key, schema_version, label, supersedes_id, recorded_at")
    .single();

  if (insertErr) {
    const msg = (insertErr.message ?? "").toLowerCase();
    if (msg.includes("house") || msg.includes("chk_olympus_profile_config")) {
      return jsonError(
        400,
        "HOUSE_KEY_FORBIDDEN",
        "overlay ProfileConfig cannot use the reserved house profile_key",
      );
    }
    console.error("profile insert failed", insertErr.code ?? "unknown");
    return jsonError(500, "PROFILE_WRITE_FAILED", "Unable to append profile version");
  }

  return jsonOk({
    version_id: inserted.id,
    profile_key: inserted.profile_key,
    schema_version: inserted.schema_version,
    label: inserted.label,
    supersedes_id: inserted.supersedes_id,
    recorded_at: inserted.recorded_at,
  });
}

async function listBrokers(req: Request, deps: SettingsDeps): Promise<Response> {
  const url = new URL(req.url);
  const workspaceId = url.searchParams.get("workspace_id");
  const authz = await resolveMember(req, deps, workspaceId);
  if (!authz.ok) return authz.response;

  const { data, error } = await deps.admin
    .from("broker_connections")
    .select(FINGERPRINT_COLUMNS)
    .eq("workspace_id", authz.workspace.id)
    .order("created_at", { ascending: false });

  if (error) {
    // Table may not exist until K3 migration deploys — surface clearly.
    return jsonError(503, "NOT_READY", "broker_connections not available (blocked on K3)");
  }

  const connections = (data ?? []).map((row: Record<string, unknown>) => ({
    id: row.id,
    broker: row.broker,
    env: row.env,
    auth_kind: row.auth_kind,
    fingerprint: row.fingerprint,
    status: row.status,
    last_used_at: row.last_used_at,
    created_at: row.created_at,
  }));

  return jsonOk({ connections });
}

async function connectBroker(req: Request, deps: SettingsDeps): Promise<Response> {
  let body: {
    workspace_id?: string;
    broker?: string;
    env?: string;
    kind?: string;
    // api_key
    key_id?: string;
    secret?: string;
    // oauth
    code?: string;
    redirect_uri?: string;
    scopes?: string[];
  };
  try {
    body = await req.json();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const authz = await resolveMember(req, deps, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const broker = (body.broker ?? "").toLowerCase();
  if (broker !== "alpaca" && broker !== "ibkr") {
    return jsonError(400, "INVALID_BROKER", "broker must be alpaca or ibkr");
  }
  const env = (body.env ?? "paper").toLowerCase();
  if (env !== "paper") {
    return jsonError(400, "LIVE_ENV_FORBIDDEN", "only env=paper is permitted in v1");
  }

  const kind = body.kind;
  let credential: BrokerCredential;
  let scopes: string[] = body.scopes ?? [];

  try {
    if (kind === "api_key") {
      credential = parseCredential({
        kind: "api_key",
        key_id: body.key_id,
        secret: body.secret,
      });
    } else if (kind === "oauth") {
      if (broker !== "alpaca") {
        return jsonError(
          400,
          "OAUTH_UNSUPPORTED",
          "OAuth connect is Alpaca-only in v1; IBKR uses API-credential entry (beta)",
        );
      }
      const code = body.code;
      const redirectUri = body.redirect_uri;
      if (typeof code !== "string" || !code || typeof redirectUri !== "string" || !redirectUri) {
        return jsonError(400, "INVALID_PAYLOAD", "oauth connect requires code and redirect_uri");
      }
      const exchanger = deps.exchangeAlpacaCode ?? exchangeAlpacaCodeDefault;
      let tokens: { access_token: string; refresh_token?: string };
      try {
        tokens = await exchanger({ code, redirectUri });
      } catch (err) {
        console.error(
          "alpaca oauth exchange failed",
          err instanceof Error ? err.name : "unknown",
        );
        return jsonError(502, "OAUTH_EXCHANGE_FAILED", "Unable to exchange OAuth code");
      }
      credential = parseCredential({
        kind: "oauth",
        access_token: tokens.access_token,
        ...(tokens.refresh_token ? { refresh_token: tokens.refresh_token } : {}),
      });
      if (scopes.length === 0) {
        scopes = ["account:write", "trading"];
      }
    } else {
      return jsonError(400, "INVALID_KIND", "kind must be api_key or oauth");
    }
  } catch (err) {
    if (err instanceof VaultPayloadError) {
      // Never log the raw validation error — it can echo secrets.
      return jsonError(400, "INVALID_CREDENTIAL", "credential payload is invalid");
    }
    throw err;
  }

  const aad = buildAad(authz.workspace.id, broker, env);
  const envelope = await sealCredential(credential, {
    aad,
    key: deps.vaultKey,
  });
  const fp = await fingerprint(credential);
  const id = (deps.uuid ?? crypto.randomUUID)();

  const row = {
    id,
    workspace_id: authz.workspace.id,
    broker,
    env,
    auth_kind: credential.kind,
    ciphertext: encodeBytea(envelope.ciphertext),
    nonce: encodeBytea(envelope.nonce),
    key_id: envelope.key_id,
    fingerprint: fp,
    scopes,
    status: "active",
  };

  const { data: inserted, error: insertErr } = await deps.admin
    .from("broker_connections")
    .insert(row)
    .select(FINGERPRINT_COLUMNS)
    .single();

  if (insertErr) {
    console.error("broker connect insert failed", insertErr.code ?? "unknown");
    return jsonError(500, "CONNECT_FAILED", "Unable to store broker connection");
  }

  // Return fingerprint projection ONLY — no ciphertext/nonce/secret.
  return jsonOk({
    id: inserted.id,
    broker: inserted.broker,
    env: inserted.env,
    auth_kind: inserted.auth_kind,
    fingerprint: inserted.fingerprint,
    status: inserted.status,
    last_used_at: inserted.last_used_at,
    created_at: inserted.created_at,
  });
}

async function revokeBroker(req: Request, deps: SettingsDeps): Promise<Response> {
  let body: { workspace_id?: string; connection_id?: string };
  try {
    body = await req.json();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const authz = await resolveMember(req, deps, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const connectionId = body.connection_id;
  if (typeof connectionId !== "string" || !connectionId) {
    return jsonError(400, "INVALID_PAYLOAD", "connection_id is required");
  }

  const stamp = (deps.now ?? (() => new Date))().toISOString();
  const { data: updated, error: updErr } = await deps.admin
    .from("broker_connections")
    .update({ status: "revoked", revoked_at: stamp })
    .eq("id", connectionId)
    .eq("workspace_id", authz.workspace.id)
    .neq("status", "revoked")
    .select(FINGERPRINT_COLUMNS)
    .maybeSingle();

  if (updErr) {
    return jsonError(500, "REVOKE_FAILED", "Unable to revoke connection");
  }

  if (updated) {
    return jsonOk({
      id: updated.id,
      broker: updated.broker,
      env: updated.env,
      fingerprint: updated.fingerprint,
      status: updated.status,
      last_used_at: updated.last_used_at,
      revoked_at: updated.revoked_at,
    });
  }

  // Fail closed on unknown row (or wrong workspace).
  const { data: existing } = await deps.admin
    .from("broker_connections")
    .select(FINGERPRINT_COLUMNS)
    .eq("id", connectionId)
    .eq("workspace_id", authz.workspace.id)
    .maybeSingle();

  if (!existing) {
    return jsonError(404, "CONNECTION_NOT_FOUND", "Unknown broker connection");
  }

  // Already revoked — idempotent success with fingerprint projection.
  return jsonOk({
    id: existing.id,
    broker: existing.broker,
    env: existing.env,
    fingerprint: existing.fingerprint,
    status: existing.status,
    last_used_at: existing.last_used_at,
    revoked_at: existing.revoked_at,
  });
}

function patchNotifications(): Response {
  // notification_prefs table lands with K5 — return a clear 503 until then.
  return jsonError(
    503,
    "NOT_READY",
    "notification_prefs is not available until K5; prefs cannot be saved yet",
  );
}

async function exchangeAlpacaCodeDefault(args: {
  code: string;
  redirectUri: string;
}): Promise<{ access_token: string; refresh_token?: string }> {
  const clientId = Deno.env.get("ALPACA_OAUTH_CLIENT_ID") ??
    Deno.env.get("NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID");
  const clientSecret = Deno.env.get("ALPACA_OAUTH_CLIENT_SECRET");
  if (!clientId || !clientSecret) {
    throw new Error("Alpaca OAuth client not configured");
  }
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: args.code,
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uri: args.redirectUri,
  });
  const res = await fetch("https://api.alpaca.markets/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    throw new Error(`Alpaca token HTTP ${res.status}`);
  }
  const json = await res.json() as {
    access_token?: string;
    refresh_token?: string;
  };
  if (typeof json.access_token !== "string" || !json.access_token) {
    throw new Error("Alpaca token response missing access_token");
  }
  return {
    access_token: json.access_token,
    ...(typeof json.refresh_token === "string"
      ? { refresh_token: json.refresh_token }
      : {}),
  };
}

/** Helper for index.ts — build deps from a verified user + admin client. */
export function createDefaultDeps(user: AuthUser, admin?: AdminClient): SettingsDeps {
  return {
    admin: admin ?? createAdminClient(),
    user,
  };
}
