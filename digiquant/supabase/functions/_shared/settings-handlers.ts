/**
 * Settings Edge Function handlers (T3) — extracted for Deno unit tests.
 *
 * Routes (mounted under /functions/v1/settings):
 *   GET    /profile            — load tip olympus_profile_config (or empty defaults; no write)
 *   PATCH  /profile            — versioned olympus_profile_config append (workspace-scoped)
 *   GET    /brokers            — list fingerprints only
 *   POST   /brokers/connect    — api_key | oauth (Alpaca code exchange server-side)
 *   POST   /brokers/revoke     — mark revoked (fail closed on unknown)
 *   GET    /notifications      — load notification_prefs (or empty defaults; no write)
 *   PATCH  /notifications      — upsert notification_prefs (workspace member)
 *
 * Deploy preconditions: module/digiquant migrations 096–098 (workspaces +
 * olympus_profile_config.workspace_id), K3 vault + broker_connections, and
 * K5 migration 103 (notification_prefs).
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
  /** Override APP_URL for pinned OAuth redirect_uri (tests). */
  appUrl?: string;
};

const FINGERPRINT_COLUMNS =
  "id, workspace_id, broker, env, auth_kind, fingerprint, scopes, status, created_at, revoked_at, last_used_at";

/** Custom/enterprise only — baseline cannot write profiles or connect brokers. */
const ELIGIBLE_TIERS = new Set(["custom", "enterprise"]);

/** Fixed OAuth callback path under Olympus (must match frontend alpacaOAuthCallbackPath). */
export const ALPACA_OAUTH_CALLBACK_PATH = "/olympus/settings/brokers/callback/";

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

  if (method === "GET" && (path === "/profile" || path === "/profile/")) {
    return getProfile(req, deps);
  }
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
  if (
    method === "GET" &&
    (path === "/notifications" || path === "/notifications/")
  ) {
    return getNotifications(req, deps);
  }
  if (method === "PATCH" && path === "/notifications") {
    return patchNotifications(req, deps);
  }
  return jsonError(404, "NOT_FOUND", "Unknown settings route");
}

/** Matches migration 103 CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$'). */
const EMAIL_RE = /^[^@]+@[^@]+\.[^@]+$/;

const PREFS_COLUMNS =
  "workspace_id, email, daily_digest, holding_change_alerts, execution_alerts, digest_hour_utc, updated_at";

async function resolveMember(
  deps: SettingsDeps,
  bodyWorkspaceId: string | null,
) {
  return requireWorkspaceMember(deps.admin, deps.user, bodyWorkspaceId);
}

/**
 * Fail closed on plan tier using the authoritative workspace row.
 *
 * `workspaces.plan_tier` is CAS-updated by the Stripe webhook. Preferring the
 * JWT `app_metadata.plan_tier` claim here fails open after cancel when claim
 * sync sets `claim_sync_pending` but leaves a stale elevated claim on the
 * token — and fails closed incorrectly on upgrade when the claim lags.
 */
function requireEligibleTier(workspacePlanTier: string): Response | null {
  const tier = (workspacePlanTier ?? "").trim().toLowerCase();
  if (!ELIGIBLE_TIERS.has(tier)) {
    return jsonError(
      403,
      "TIER_FORBIDDEN",
      "plan_tier must be custom or enterprise for this settings action",
    );
  }
  return null;
}

/** Server-pinned OAuth redirect_uri — rejects client mismatches. */
export function pinnedAlpacaRedirectUri(appUrl?: string): string {
  const raw =
    appUrl ??
    Deno.env.get("APP_URL") ??
    Deno.env.get("NEXT_PUBLIC_APP_URL") ??
    "";
  const base = raw.replace(/\/+$/, "");
  if (!base) {
    throw new Error("APP_URL unset");
  }
  return `${base}${ALPACA_OAUTH_CALLBACK_PATH}`;
}

function isUniqueViolation(err: { code?: string; message?: string }): boolean {
  if (err.code === "23505") return true;
  const msg = (err.message ?? "").toLowerCase();
  return msg.includes("unique") || msg.includes("duplicate");
}

const DEFAULT_PROFILE_KEY = "workspace";

function emptyProfileBody(
  workspaceId: string,
  profileKey: string,
): Record<string, unknown> {
  return {
    version_id: null,
    workspace_id: workspaceId,
    profile_key: profileKey,
    schema_version: 1,
    label: "",
    supersedes_id: null,
    recorded_at: null,
    investment: null,
    assets: null,
  };
}

function profileResponseBody(row: Record<string, unknown>): Record<string, unknown> {
  const payload =
    row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
      ? (row.payload as Record<string, unknown>)
      : {};
  return {
    version_id: row.id ?? null,
    workspace_id: row.workspace_id,
    profile_key: row.profile_key,
    schema_version: row.schema_version ?? payload.schema_version ?? 1,
    label: typeof row.label === "string" ? row.label : String(payload.label ?? ""),
    supersedes_id: row.supersedes_id ?? null,
    recorded_at: row.recorded_at ?? null,
    investment: payload.investment ?? null,
    assets: payload.assets ?? null,
  };
}

/**
 * GET /profile — tip overlay for hydrate (member authz; no tier write gate).
 * Empty contract: no tip → 200 with version_id/recorded_at null and empty label
 * (never inserts). Optional `?profile_key=` (default `workspace`); `house` rejected.
 */
async function getProfile(req: Request, deps: SettingsDeps): Promise<Response> {
  const url = new URL(req.url);
  const workspaceId = url.searchParams.get("workspace_id");
  const authz = await resolveMember(deps, workspaceId);
  if (!authz.ok) return authz.response;

  const rawKey = (url.searchParams.get("profile_key") ?? DEFAULT_PROFILE_KEY).trim();
  const profileKey = rawKey || DEFAULT_PROFILE_KEY;
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

  const { data: tip, error: tipErr } = await deps.admin
    .from("olympus_profile_config")
    .select("id, workspace_id, profile_key, schema_version, label, supersedes_id, recorded_at, payload")
    .eq("workspace_id", authz.workspace.id)
    .eq("profile_key", profileKey)
    .eq("is_house_default", false)
    .order("recorded_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (tipErr) {
    return jsonError(503, "NOT_READY", "olympus_profile_config not available");
  }

  if (!tip) {
    return jsonOk(emptyProfileBody(authz.workspace.id, profileKey));
  }

  return jsonOk(profileResponseBody(tip as Record<string, unknown>));
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

  const authz = await resolveMember(deps, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const tierErr = requireEligibleTier(authz.workspace.plan_tier);
  if (tierErr) return tierErr;

  const workspaceId = authz.workspace.id;
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

  // Optimistic concurrency: tip is scoped by (workspace_id, profile_key).
  if (expected) {
    const { data: tip, error: tipErr } = await deps.admin
      .from("olympus_profile_config")
      .select("id, supersedes_id")
      .eq("workspace_id", workspaceId)
      .eq("profile_key", profileKey)
      .eq("is_house_default", false)
      .order("recorded_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (tipErr) {
      return jsonError(500, "PROFILE_LOOKUP_FAILED", "Unable to load profile tip");
    }
    if (tip && tip.id !== expected) {
      return jsonError(
        409,
        "VERSION_CONFLICT",
        "profile changed elsewhere — reload",
      );
    }
    if (!tip && expected) {
      const { data: row } = await deps.admin
        .from("olympus_profile_config")
        .select("id")
        .eq("id", expected)
        .eq("workspace_id", workspaceId)
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

  // Bind crypto: unbound `crypto.randomUUID` throws TypeError ("expected Crypto") on Deno/Edge.
  const versionId = deps.uuid ? deps.uuid() : crypto.randomUUID();
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
      workspace_id: workspaceId,
      profile_key: profileKey,
      schema_version: 1,
      is_house_default: false,
      label,
      payload,
      supersedes_id: expected,
    })
    .select("id, profile_key, schema_version, label, supersedes_id, recorded_at, workspace_id")
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
    if (isUniqueViolation(insertErr)) {
      // supersedes_id unique (or tip race) → stable 409, never 500.
      return jsonError(
        409,
        "VERSION_CONFLICT",
        "profile changed elsewhere — reload",
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
    workspace_id: inserted.workspace_id,
  });
}

async function listBrokers(req: Request, deps: SettingsDeps): Promise<Response> {
  const url = new URL(req.url);
  const workspaceId = url.searchParams.get("workspace_id");
  const authz = await resolveMember(deps, workspaceId);
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

  const authz = await resolveMember(deps, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const tierErr = requireEligibleTier(authz.workspace.plan_tier);
  if (tierErr) return tierErr;

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
      if (typeof code !== "string" || !code) {
        return jsonError(400, "INVALID_PAYLOAD", "oauth connect requires code");
      }

      let expectedRedirect: string;
      try {
        expectedRedirect = pinnedAlpacaRedirectUri(deps.appUrl);
      } catch {
        return jsonError(500, "OAUTH_MISCONFIGURED", "APP_URL is not configured");
      }
      const clientRedirect = body.redirect_uri;
      if (
        typeof clientRedirect === "string" &&
        clientRedirect.length > 0 &&
        clientRedirect !== expectedRedirect
      ) {
        return jsonError(
          400,
          "REDIRECT_URI_MISMATCH",
          "redirect_uri must match the server-pinned OAuth callback",
        );
      }
      // Always exchange with the pinned URI (ignore client even when matching).
      const exchanger = deps.exchangeAlpacaCode ?? exchangeAlpacaCodeDefault;
      let tokens: { access_token: string; refresh_token?: string };
      try {
        tokens = await exchanger({ code, redirectUri: expectedRedirect });
      } catch (err) {
        if (err instanceof AlpacaOAuthNotConfiguredError) {
          return jsonError(
            500,
            "OAUTH_NOT_CONFIGURED",
            "ALPACA_OAUTH_CLIENT_ID and ALPACA_OAUTH_CLIENT_SECRET must be set",
          );
        }
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

  return insertBrokerConnection(deps, {
    workspaceId: authz.workspace.id,
    broker,
    env,
    credentialKind: credential.kind,
    envelope,
    fingerprint: fp,
    scopes,
  });
}

async function insertBrokerConnection(
  deps: SettingsDeps,
  args: {
    workspaceId: string;
    broker: string;
    env: string;
    credentialKind: string;
    envelope: { ciphertext: Uint8Array; nonce: Uint8Array; key_id: string };
    fingerprint: string;
    scopes: string[];
  },
): Promise<Response> {
  const id = deps.uuid ? deps.uuid() : crypto.randomUUID();
  const row = {
    id,
    workspace_id: args.workspaceId,
    broker: args.broker,
    env: args.env,
    auth_kind: args.credentialKind,
    ciphertext: encodeBytea(args.envelope.ciphertext),
    nonce: encodeBytea(args.envelope.nonce),
    key_id: args.envelope.key_id,
    fingerprint: args.fingerprint,
    scopes: args.scopes,
    status: "active",
  };

  const { data: inserted, error: insertErr } = await deps.admin
    .from("broker_connections")
    .insert(row)
    .select(FINGERPRINT_COLUMNS)
    .single();

  if (!insertErr) {
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

  if (!isUniqueViolation(insertErr)) {
    console.error("broker connect insert failed", insertErr.code ?? "unknown");
    return jsonError(500, "CONNECT_FAILED", "Unable to store broker connection");
  }

  // Active-row unique on (workspace, broker, env) — K3 reconnect: revoke then insert.
  const stamp = (deps.now ?? (() => new Date))().toISOString();
  const { error: revokeErr } = await deps.admin
    .from("broker_connections")
    .update({ status: "revoked", revoked_at: stamp })
    .eq("workspace_id", args.workspaceId)
    .eq("broker", args.broker)
    .eq("env", args.env)
    .eq("status", "active");

  if (revokeErr) {
    console.error("broker reconnect revoke failed", revokeErr.code ?? "unknown");
    return jsonError(500, "CONNECT_FAILED", "Unable to revoke prior connection");
  }

  const retryId = deps.uuid ? deps.uuid() : crypto.randomUUID();
  const retryRow = { ...row, id: retryId };
  const { data: retried, error: retryErr } = await deps.admin
    .from("broker_connections")
    .insert(retryRow)
    .select(FINGERPRINT_COLUMNS)
    .single();

  if (retryErr) {
    console.error("broker reconnect insert failed", retryErr.code ?? "unknown");
    return jsonError(500, "CONNECT_FAILED", "Unable to store broker connection");
  }

  return jsonOk({
    id: retried.id,
    broker: retried.broker,
    env: retried.env,
    auth_kind: retried.auth_kind,
    fingerprint: retried.fingerprint,
    status: retried.status,
    last_used_at: retried.last_used_at,
    created_at: retried.created_at,
  });
}

async function revokeBroker(req: Request, deps: SettingsDeps): Promise<Response> {
  let body: { workspace_id?: string; connection_id?: string };
  try {
    body = await req.json();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const authz = await resolveMember(deps, body.workspace_id ?? null);
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

/**
 * Empty-prefs contract (no row yet): HTTP 200 with sensible defaults and
 * `updated_at: null` — never writes. Clients hydrate the form from this body
 * so an accidental Save does not overwrite with blank defaults unknowingly.
 * Missing table → 503 NOT_READY (same as PATCH).
 */
function emptyNotificationPrefs(
  workspaceId: string,
  userEmail: string | null | undefined,
): Record<string, unknown> {
  const email =
    typeof userEmail === "string" && userEmail.trim() ? userEmail.trim() : "";
  return {
    workspace_id: workspaceId,
    email,
    daily_digest: false,
    holding_change_alerts: false,
    execution_alerts: false,
    digest_hour_utc: 12,
    updated_at: null,
  };
}

function prefsResponseBody(row: Record<string, unknown>): Record<string, unknown> {
  return {
    workspace_id: row.workspace_id,
    email: row.email,
    daily_digest: row.daily_digest,
    holding_change_alerts: row.holding_change_alerts,
    execution_alerts: row.execution_alerts,
    digest_hour_utc: row.digest_hour_utc,
    updated_at: row.updated_at ?? null,
  };
}

async function getNotifications(
  req: Request,
  deps: SettingsDeps,
): Promise<Response> {
  const url = new URL(req.url);
  const workspaceId = url.searchParams.get("workspace_id");
  const authz = await resolveMember(deps, workspaceId);
  if (!authz.ok) return authz.response;

  const { data: existing, error: lookupErr } = await deps.admin
    .from("notification_prefs")
    .select(PREFS_COLUMNS)
    .eq("workspace_id", authz.workspace.id)
    .maybeSingle();

  if (lookupErr) {
    return jsonError(
      503,
      "NOT_READY",
      "notification_prefs not available",
    );
  }

  if (!existing) {
    return jsonOk(emptyNotificationPrefs(authz.workspace.id, deps.user.email));
  }

  return jsonOk(prefsResponseBody(existing as Record<string, unknown>));
}

async function patchNotifications(
  req: Request,
  deps: SettingsDeps,
): Promise<Response> {
  let body: {
    workspace_id?: string;
    email?: string;
    daily_digest?: boolean;
    holding_change_alerts?: boolean;
    execution_alerts?: boolean;
    digest_hour_utc?: number;
  };
  try {
    body = await req.json();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const authz = await resolveMember(deps, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const { data: existing, error: lookupErr } = await deps.admin
    .from("notification_prefs")
    .select(PREFS_COLUMNS)
    .eq("workspace_id", authz.workspace.id)
    .maybeSingle();

  if (lookupErr) {
    return jsonError(
      503,
      "NOT_READY",
      "notification_prefs not available",
    );
  }

  const emailRaw = typeof body.email === "string" ? body.email.trim() : "";
  const emailFallback =
    typeof deps.user.email === "string" ? deps.user.email.trim() : "";
  const email =
    emailRaw ||
    (typeof existing?.email === "string" ? existing.email : "") ||
    emailFallback;
  if (!email || !EMAIL_RE.test(email)) {
    return jsonError(
      400,
      "INVALID_EMAIL",
      "email is required and must be a valid address",
    );
  }

  if (body.digest_hour_utc !== undefined) {
    const hour = body.digest_hour_utc;
    if (
      typeof hour !== "number" ||
      !Number.isInteger(hour) ||
      hour < 0 ||
      hour > 23
    ) {
      return jsonError(
        400,
        "INVALID_DIGEST_HOUR",
        "digest_hour_utc must be an integer 0..23",
      );
    }
  }

  const asBool = (
    incoming: boolean | undefined,
    prior: unknown,
    fallback: boolean,
  ): boolean => {
    if (typeof incoming === "boolean") return incoming;
    if (typeof prior === "boolean") return prior;
    return fallback;
  };

  const row = {
    workspace_id: authz.workspace.id,
    email,
    daily_digest: asBool(body.daily_digest, existing?.daily_digest, false),
    holding_change_alerts: asBool(
      body.holding_change_alerts,
      existing?.holding_change_alerts,
      false,
    ),
    execution_alerts: asBool(
      body.execution_alerts,
      existing?.execution_alerts,
      false,
    ),
    digest_hour_utc:
      body.digest_hour_utc !== undefined
        ? body.digest_hour_utc
        : typeof existing?.digest_hour_utc === "number"
        ? existing.digest_hour_utc
        : 12,
  };

  const { data: upserted, error: upsertErr } = await deps.admin
    .from("notification_prefs")
    .upsert(row, { onConflict: "workspace_id" })
    .select(PREFS_COLUMNS)
    .single();

  if (upsertErr) {
    const msg = (upsertErr.message ?? "").toLowerCase();
    if (msg.includes("email") || msg.includes("check")) {
      return jsonError(
        400,
        "INVALID_EMAIL",
        "email is required and must be a valid address",
      );
    }
    console.error("notification_prefs upsert failed", upsertErr.code ?? "unknown");
    return jsonError(500, "PREFS_WRITE_FAILED", "Unable to save notification preferences");
  }

  return jsonOk(prefsResponseBody(upserted as Record<string, unknown>));
}

/** Raised when Alpaca OAuth client id/secret are missing from EF secrets. */
export class AlpacaOAuthNotConfiguredError extends Error {
  constructor() {
    super("Alpaca OAuth client not configured");
    this.name = "AlpacaOAuthNotConfiguredError";
  }
}

async function exchangeAlpacaCodeDefault(args: {
  code: string;
  redirectUri: string;
}): Promise<{ access_token: string; refresh_token?: string }> {
  const clientId = Deno.env.get("ALPACA_OAUTH_CLIENT_ID") ??
    Deno.env.get("NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID");
  const clientSecret = Deno.env.get("ALPACA_OAUTH_CLIENT_SECRET");
  if (!clientId || !clientSecret) {
    throw new AlpacaOAuthNotConfiguredError();
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
