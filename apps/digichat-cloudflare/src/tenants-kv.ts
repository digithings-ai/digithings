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

/**
 * Durable gated-tenant claims (U1), same KV namespace, key `gated-claims`.
 *
 * A JSON array of `{ "slug", "chatSlug", "host" }` rows naming every tenant
 * that is served only behind an invite. It lives outside the tenant registry
 * (`embed-tenants`) on purpose: if the registry is missing, unreadable or
 * loses a row, the claims still say "this host is gated" and the container
 * denies instead of falling through to the open house chat. The value holds
 * no secret and no secret name. Writers only ever add to it
 * ({@link addGatedClaims}); removing a claim is a deliberate manual edit.
 *
 * The Worker forwards the normalized list to the container as
 * `DIGICHAT_GATED_CLAIMS`; the app merges it into its R0-side claims.
 */
export const GATED_CLAIMS_KV_KEY = "gated-claims";

export type GatedClaim = { slug: string; chatSlug: string; host?: string };

export type GatedClaimsResult = {
  /** Normalized JSON array, or "" when there are no claims. */
  json: string;
  /** `error`: the KV read failed; the caller keeps what it already forwards. */
  source: "kv" | "none" | "error";
  claims: GatedClaim[];
};

const CLAIM_SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const CLAIM_HOST_RE = /^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/;

/** One claim row, or null when it is not a valid claim. Never throws. */
export function normalizeGatedClaim(value: unknown): GatedClaim | null {
  if (!isObj(value)) return null;
  const slug = typeof value.slug === "string" ? value.slug.trim().toLowerCase() : "";
  if (!CLAIM_SLUG_RE.test(slug)) return null;
  const chatSlugRaw = typeof value.chatSlug === "string" ? value.chatSlug.trim().toLowerCase() : "";
  if (chatSlugRaw && !CLAIM_SLUG_RE.test(chatSlugRaw)) return null;
  const hostRaw = typeof value.host === "string" ? value.host.trim().toLowerCase() : "";
  if (hostRaw && !CLAIM_HOST_RE.test(hostRaw)) return null;
  if (!chatSlugRaw && !hostRaw) return null;
  return hostRaw ? { slug, chatSlug: chatSlugRaw, host: hostRaw } : { slug, chatSlug: chatSlugRaw };
}

function claimKey(c: GatedClaim): string {
  return `${c.chatSlug}|${c.host ?? ""}`;
}

/**
 * Parse a claims value. Invalid rows are skipped one by one (a bad row never
 * hides the good ones); a value that is not a JSON array yields no claims.
 * Duplicates (same `chatSlug|host`) are kept once, first wins.
 */
export function parseGatedClaims(raw: string | null | undefined): GatedClaim[] {
  if (typeof raw !== "string" || !raw.trim()) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const out: GatedClaim[] = [];
  const seen = new Set<string>();
  for (const row of parsed) {
    const claim = normalizeGatedClaim(row);
    if (!claim) continue;
    const key = claimKey(claim);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(claim);
  }
  return out;
}

/**
 * Add-only merge for the tenant writer: every existing claim is kept as is,
 * and only new `chatSlug|host` keys are appended. Throws on an existing value
 * that is present but unparseable, so a writer never replaces claims it could
 * not read, and on an invalid new claim.
 */
export function addGatedClaims(existingRaw: string | null | undefined, add: readonly unknown[]): string {
  let existing: GatedClaim[] = [];
  if (typeof existingRaw === "string" && existingRaw.trim()) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(existingRaw);
    } catch {
      throw new Error(`${GATED_CLAIMS_KV_KEY}: existing value is not JSON; refusing to overwrite it`);
    }
    if (!Array.isArray(parsed)) {
      throw new Error(`${GATED_CLAIMS_KV_KEY}: existing value is not a JSON array; refusing to overwrite it`);
    }
    existing = parseGatedClaims(existingRaw);
    if (existing.length !== parsed.length) {
      throw new Error(`${GATED_CLAIMS_KV_KEY}: existing value has invalid or duplicate rows; fix it by hand first`);
    }
  }
  const out = [...existing];
  const seen = new Set(out.map(claimKey));
  for (const row of add) {
    const claim = normalizeGatedClaim(row);
    if (!claim) throw new Error(`${GATED_CLAIMS_KV_KEY}: refusing an invalid claim`);
    const key = claimKey(claim);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(claim);
  }
  return JSON.stringify(out);
}

/** Union of claim lists, first wins on `chatSlug|host`. */
export function unionGatedClaims(...lists: readonly GatedClaim[][]): GatedClaim[] {
  const out: GatedClaim[] = [];
  const seen = new Set<string>();
  for (const list of lists) {
    for (const claim of list) {
      const key = claimKey(claim);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(claim);
    }
  }
  return out;
}

/**
 * Read the durable claims from KV. A missing binding or key is `none`; a read
 * failure is `error` (logged, never thrown) so the caller can keep the claims
 * it already forwarded rather than dropping them for this window.
 */
export async function resolveGatedClaims(kv: KvLike | undefined): Promise<GatedClaimsResult> {
  if (!kv) return { json: "", source: "none", claims: [] };
  let raw: string | null;
  try {
    raw = await kv.get(GATED_CLAIMS_KV_KEY);
  } catch (e) {
    console.error(`[claims-kv] KV ${GATED_CLAIMS_KV_KEY} read failed, keeping current claims: ${(e as Error).message}`);
    return { json: "", source: "error", claims: [] };
  }
  if (typeof raw !== "string" || !raw.trim()) return { json: "", source: "none", claims: [] };
  const claims = parseGatedClaims(raw);
  return { json: claims.length ? JSON.stringify(claims) : "", source: "kv", claims };
}
