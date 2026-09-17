/**
 * HMAC-signed plan proof tokens for the digiquant dashboard embed (#3662).
 *
 * Digichat mints a signed token only after verifying a dashboard Supabase
 * access token and reading plan_tier from app_metadata claims. The chat
 * route verifies the signature before accepting the tier — raw client-asserted
 * X-Embed-Plan-Tier / ?plan_tier= are NEVER trusted.
 *
 * Env (names only): DIGICHAT_PLAN_PROOF_SECRET,
 * DIGICHAT_DASHBOARD_SUPABASE_URL, DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY.
 * Format: base64url(tier|exp|sig)
 * TTL: 300 seconds (5 minutes).
 */

import { createHmac, timingSafeEqual } from "crypto";

const PROOF_TTL_MS = 300_000; // 5 minutes
const PLAN_TIERS = ["free", "brief", "desk", "studio", "enterprise"] as const;
export type PlanTier = (typeof PLAN_TIERS)[number];

/** Desk+ tiers eligible for a signed chat proof. */
export const PROOF_ELIGIBLE_TIERS = ["desk", "studio", "enterprise"] as const;
export type ProofEligibleTier = (typeof PROOF_ELIGIBLE_TIERS)[number];

export function isValidPlanTier(value: string): value is PlanTier {
  return (PLAN_TIERS as readonly string[]).includes(value);
}

export function isProofEligibleTier(value: string): value is ProofEligibleTier {
  return (PROOF_ELIGIBLE_TIERS as readonly string[]).includes(value);
}

function base64urlEncode(data: string): string {
  return Buffer.from(data).toString("base64url");
}

function base64urlDecode(data: string): string {
  return Buffer.from(data, "base64url").toString();
}

function hmacSign(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

/**
 * Mint a signed plan proof token. Call server-side only after claims check.
 */
export function signPlanProof(
  tier: PlanTier,
  secret: string,
  expiresAt?: number,
): string {
  const exp = expiresAt ?? Date.now() + PROOF_TTL_MS;
  const payload = `${tier}|${exp}`;
  const sig = hmacSign(secret, payload);
  return base64urlEncode(`${payload}|${sig}`);
}

/**
 * Verify a plan proof token and return the tier, or null if invalid/expired.
 * Call server-side only (chat route).
 */
export function verifyPlanProof(
  token: string,
  secret: string,
): PlanTier | null {
  try {
    const decoded = base64urlDecode(token);
    const parts = decoded.split("|");
    if (parts.length !== 3) return null;

    const [tier, expStr, sig] = parts;
    const exp = Number(expStr);
    if (!Number.isFinite(exp) || Date.now() > exp) return null;
    if (!isValidPlanTier(tier)) return null;

    const expectedPayload = `${tier}|${exp}`;
    const expectedSig = hmacSign(secret, expectedPayload);

    // Constant-time comparison
    const sigBuf = Buffer.from(sig, "base64url");
    const expectedBuf = Buffer.from(expectedSig, "base64url");
    if (sigBuf.length !== expectedBuf.length) return null;
    if (!timingSafeEqual(sigBuf, expectedBuf)) return null;

    return tier;
  } catch {
    return null;
  }
}

/**
 * Resolve plan_tier from a digiquant dashboard Supabase access token.
 * Calls GET /auth/v1/user — never trusts client-asserted tier.
 * Returns null when the token is invalid or claims are missing/unusable.
 */
export async function resolvePlanTierFromDashboardAccessToken(
  accessToken: string,
  opts?: {
    supabaseUrl?: string;
    anonKey?: string;
    fetchImpl?: typeof fetch;
  },
): Promise<PlanTier | null> {
  const supabaseUrl = (
    opts?.supabaseUrl ?? process.env.DIGICHAT_DASHBOARD_SUPABASE_URL ?? ""
  ).trim().replace(/\/$/, "");
  const anonKey = (
    opts?.anonKey ?? process.env.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY ?? ""
  ).trim();
  if (!supabaseUrl || !anonKey || !accessToken.trim()) return null;

  const fetchImpl = opts?.fetchImpl ?? fetch;
  try {
    const res = await fetchImpl(`${supabaseUrl}/auth/v1/user`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${accessToken.trim()}`,
        apikey: anonKey,
      },
    });
    if (!res.ok) return null;
    const user = (await res.json()) as {
      app_metadata?: { plan_tier?: unknown };
    };
    const raw = user?.app_metadata?.plan_tier;
    if (typeof raw !== "string") return null;
    const tier = raw.trim().toLowerCase();
    return isValidPlanTier(tier) ? tier : null;
  } catch {
    return null;
  }
}

/**
 * Best-effort tier from query param or header. NEVER used for authorization —
 * only for non-security UI hints. The chat route uses verifyPlanProof() instead.
 */
export function rawTierFromRequest(req: Request): PlanTier | null {
  const raw =
    req.headers.get("x-embed-plan-tier")?.trim().toLowerCase() ||
    new URL(req.url).searchParams.get("plan_tier")?.trim().toLowerCase() ||
    null;
  return raw && isValidPlanTier(raw) ? raw : null;
}
