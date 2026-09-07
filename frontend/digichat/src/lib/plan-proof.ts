/**
 * HMAC-signed plan proof tokens for the digiquant dashboard embed (#3662).
 *
 * The dashboard mints a signed token proving the user's plan_tier. The chat
 * route verifies the signature before accepting the tier — raw client-asserted
 * X-Embed-Plan-Tier / ?plan_tier= are NEVER trusted.
 *
 * Secret: DIGICHAT_PLAN_PROOF_SECRET (env, never committed).
 * Format: base64url(tier|exp|sig)
 * TTL: 300 seconds (5 minutes).
 */

import { createHmac, timingSafeEqual } from "crypto";

const PROOF_TTL_MS = 300_000; // 5 minutes
const PLAN_TIERS = ["free", "brief", "desk", "studio", "enterprise"] as const;
export type PlanTier = (typeof PLAN_TIERS)[number];

export function isValidPlanTier(value: string): value is PlanTier {
  return (PLAN_TIERS as readonly string[]).includes(value);
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
 * Mint a signed plan proof token.  Call server-side only (dashboard API route).
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
 * Best-effort tier from query param or header.  NEVER used for authorization —
 * only for non-security UI hints.  The chat route uses verifyPlanProof() instead.
 */
export function rawTierFromRequest(req: Request): PlanTier | null {
  const raw =
    req.headers.get("x-embed-plan-tier")?.trim().toLowerCase() ||
    new URL(req.url).searchParams.get("plan_tier")?.trim().toLowerCase() ||
    null;
  return raw && isValidPlanTier(raw) ? raw : null;
}
