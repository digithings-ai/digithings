/**
 * Embed tenant registry from Workers KV (DIG-1210).
 *
 * Tenant config is deployment data, not code: it lives in the KV namespace
 * bound as `DIGICHAT_TENANTS_KV` under key `embed-tenants` (JSON object keyed
 * by host, same shape as DIGICHAT_EMBED_TENANTS). It holds no secret values:
 * credentials are referenced by name and resolved here from Worker secrets.
 *
 *   tenant.tokenEnv            → tenant.token (e.g. OCC_INVITE_KEY, digikey-rotatable)
 *   tenant.mcp.servers[].tokenEnv → server.token (e.g. MCP_EDGE_KEY)
 *
 * Merge with the legacy `DIGICHAT_EMBED_TENANTS` secret, host by host:
 *   - a KV host whose refs all resolve wins;
 *   - a KV host with an unresolved ref keeps the legacy entry if one exists,
 *     else is dropped (fail closed, never served without its token);
 *   - legacy-only hosts are kept, so nothing breaks before migration.
 * The result is handed to the container as DIGICHAT_EMBED_TENANTS, so the
 * Next.js app is unchanged.
 */

export const TENANTS_KV_KEY = "embed-tenants";

/**
 * digichat deployment document from the same KV namespace, key `config-yaml`.
 *
 * This is the whole config document (YAML or JSON text, same shape as
 * DIGICHAT_CONFIG_PATH / `config/defaults.yaml`): deployment, hosts, chrome.
 * It lives outside the Container image and outside the Worker so an operator
 * edit applies on the next Container boot with no redeploy. Non-secret by
 * design — credentials stay named env refs (`tokenEnv`) resolved in the
 * container's process environment, never inline tokens.
 */
export const CONFIG_KV_KEY = "config-yaml";

export type ConfigYamlResult = {
  yaml: string;
  source: "kv" | "none";
};

type Json = Record<string, unknown>;
export type TenantSecrets = Record<string, unknown>;

export type ResolveResult = {
  json: string;
  source: "kv" | "legacy" | "merged" | "none";
  /** host → missing env names (values never reported). */
  unresolved: Record<string, string[]>;
};

function isObj(v: unknown): v is Json {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function secretValue(env: TenantSecrets, name: unknown): string | null {
  if (typeof name !== "string" || !/^[A-Z][A-Z0-9_]*$/.test(name)) return null;
  const v = env[name];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/** Resolve *Env refs of one tenant. Returns the resolved copy + missing names. */
export function resolveTenantRefs(tenant: Json, env: TenantSecrets): { tenant: Json; missing: string[] } {
  const out: Json = structuredClone(tenant);
  const missing: string[] = [];
  if ("tokenEnv" in out) {
    const v = secretValue(env, out.tokenEnv);
    if (v) out.token = v;
    else missing.push(String(out.tokenEnv));
    delete out.tokenEnv;
  }
  const mcp = out.mcp;
  if (isObj(mcp) && Array.isArray(mcp.servers)) {
    mcp.servers = mcp.servers.map((s) => {
      if (!isObj(s) || !("tokenEnv" in s) || typeof s.token === "string") return s;
      const v = secretValue(env, s.tokenEnv);
      if (!v) {
        missing.push(String(s.tokenEnv));
        return s;
      }
      const { tokenEnv: _drop, ...rest } = s;
      return { ...rest, token: v };
    });
  }
  return { tenant: out, missing };
}

function parseObj(raw: string | null | undefined, ctx: string): Json | null {
  if (!raw || !raw.trim()) return null;
  const parsed: unknown = JSON.parse(raw);
  if (!isObj(parsed)) throw new Error(`${ctx} must be a JSON object keyed by host`);
  return parsed;
}

export function mergeTenants(
  kvRaw: string | null | undefined,
  legacyRaw: string | null | undefined,
  env: TenantSecrets,
): ResolveResult {
  let kv: Json | null = null;
  try {
    kv = parseObj(kvRaw, "KV embed-tenants");
  } catch (e) {
    // Invalid KV must not take chat down: fall back to the legacy secret.
    console.error(`[tenants-kv] ignoring invalid KV config: ${(e as Error).message}`);
  }
  let legacy: Json | null = null;
  try {
    legacy = parseObj(legacyRaw, "DIGICHAT_EMBED_TENANTS");
  } catch (e) {
    // A malformed legacy secret must not take the Worker down either: a
    // readable KV config still serves, otherwise no tenant is served at all.
    console.error(`[tenants-kv] ignoring invalid DIGICHAT_EMBED_TENANTS: ${(e as Error).message}`);
  }
  const unresolved: Record<string, string[]> = {};
  if (!kv) {
    return { json: legacy ? JSON.stringify(legacy) : "", source: legacy ? "legacy" : "none", unresolved };
  }
  const out: Json = { ...(legacy ?? {}) };
  for (const [host, value] of Object.entries(kv)) {
    if (!isObj(value)) continue;
    const { tenant, missing } = resolveTenantRefs(value, env);
    if (missing.length) {
      unresolved[host] = missing;
      continue; // legacy entry (if any) stays
    }
    out[host] = tenant;
  }
  return {
    json: Object.keys(out).length ? JSON.stringify(out) : "",
    source: legacy ? "merged" : "kv",
    unresolved,
  };
}

type KvLike = { get(key: string): Promise<string | null> };

export async function resolveEmbedTenants(
  kv: KvLike | undefined,
  legacyRaw: string | undefined,
  env: TenantSecrets,
): Promise<ResolveResult> {
  let kvRaw: string | null = null;
  if (kv) {
    try {
      kvRaw = await kv.get(TENANTS_KV_KEY);
    } catch (e) {
      console.error(`[tenants-kv] KV read failed, using legacy secret: ${(e as Error).message}`);
    }
  }
  const result = mergeTenants(kvRaw, legacyRaw, env);
  for (const [host, names] of Object.entries(result.unresolved)) {
    console.warn(`[tenants-kv] ${host}: unresolved secret refs ${names.join(",")}; kept legacy entry if any`);
  }
  return result;
}

/**
 * Read the deployment document from KV. A missing binding, a missing key or a
 * blank value all mean "none": the container then uses its own file/defaults,
 * exactly as it did before this key existed. A read failure is logged rather
 * than thrown — config plumbing must not take chat down — and the caller
 * forwards the empty string so the loader's own precedence still applies.
 */
export async function resolveConfigYaml(kv: KvLike | undefined): Promise<ConfigYamlResult> {
  if (!kv) return { yaml: "", source: "none" };
  try {
    const raw = await kv.get(CONFIG_KV_KEY);
    if (typeof raw !== "string" || !raw.trim()) return { yaml: "", source: "none" };
    return { yaml: raw, source: "kv" };
  } catch (e) {
    console.error(
      `[config-kv] KV ${CONFIG_KV_KEY} read failed, using the container's file/defaults: ${(e as Error).message}`,
    );
    return { yaml: "", source: "none" };
  }
}
