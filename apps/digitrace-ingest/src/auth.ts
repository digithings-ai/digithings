/**
 * The ingest token, and the tenant it may write for.
 *
 * ADR-0036 §2: the token is looked up server-side and the claimed slug is
 * checked against the tenants that token may write for. A slug the token may not
 * claim is rejected and the batch is dropped — fail closed, never repaired.
 *
 * The token itself is never stored: the KV key is its SHA-256, so a read of the
 * namespace does not yield a usable credential. The KV record holds only what
 * the Worker needs after the check — the source name and the allowed tenants.
 *
 * `tenant_slug_verified` is false on this path, and that is the documented
 * deviation from digikey (ADR-0036 §2): the flag is true only for a claim inside
 * a digikey-signed JWT, which this endpoint does not accept. The value is stored
 * either way, so a reader can tell a static-token claim from a signed one.
 */
import type { TokenRecord } from "./types";

/** The header carrying the per-source ingest credential. */
export const TOKEN_HEADER = "x-digitrace-token";
/** The header carrying the tenant slug the source claims. */
export const TENANT_HEADER = "x-digitrace-tenant";

/** The KV key for a token: its digest, never the secret itself. */
export const TOKEN_KEY_PREFIX = "tok:";

export interface AuthContext {
  /** The verified tenant slug. This is the only slug anything downstream uses. */
  tenant: string;
  /** The source that owns the token, from the KV record. */
  source: string;
  /** Always false for a static token (ADR-0036 §2). */
  tenantSlugVerified: boolean;
}

export type AuthResult =
  { ok: true; context: AuthContext } | { ok: false; status: 401 | 403; reason: string };

const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

/** Lowercase hex SHA-256 of a token. */
export async function hashToken(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  const bytes = new Uint8Array(digest);
  let hex = "";
  for (const byte of bytes) hex += byte.toString(16).padStart(2, "0");
  return hex;
}

/** The KV key for a token. */
export function tokenKey(token: string): Promise<string> {
  return hashToken(token).then((digest) => `${TOKEN_KEY_PREFIX}${digest}`);
}

/** A KV value as a usable record, or undefined when it is not one. */
export function parseTokenRecord(raw: unknown): TokenRecord | undefined {
  if (typeof raw !== "string" || raw === "") return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return undefined;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return undefined;
  const record = parsed as Partial<TokenRecord>;
  if (typeof record.source !== "string" || record.source.trim() === "") return undefined;
  if (!Array.isArray(record.tenants)) return undefined;
  const tenants = record.tenants.filter(
    (tenant): tenant is string => typeof tenant === "string" && SLUG.test(tenant),
  );
  if (tenants.length !== record.tenants.length || tenants.length === 0) return undefined;
  return { source: record.source.trim(), tenants };
}

/**
 * Resolve the request's credential and claim.
 *
 * The two failures are separate on purpose: an unknown token is 401 (nothing to
 * retry with), while a token that exists but may not claim this slug is 403 (the
 * source is misconfigured, and a retry will not help either).
 */
export async function authenticate(
  kv: KVNamespace,
  tokenHeader: string | null,
  tenantHeader: string | null,
): Promise<AuthResult> {
  const token = (tokenHeader ?? "").trim();
  if (token === "") return { ok: false, status: 401, reason: "missing ingest token" };

  const record = parseTokenRecord(await kv.get(await tokenKey(token)));
  if (record === undefined) return { ok: false, status: 401, reason: "unknown ingest token" };

  const claimed = (tenantHeader ?? "").trim();
  if (claimed === "") return { ok: false, status: 403, reason: "missing tenant claim" };
  if (!SLUG.test(claimed)) return { ok: false, status: 403, reason: "malformed tenant claim" };
  if (!record.tenants.includes(claimed)) {
    return { ok: false, status: 403, reason: "tenant claim is not allowed for this token" };
  }

  return {
    ok: true,
    context: { tenant: claimed, source: record.source, tenantSlugVerified: false },
  };
}
