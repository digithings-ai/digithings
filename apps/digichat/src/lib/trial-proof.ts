/**
 * HMAC-signed trial proof tokens for the X-Embed-Trial-Proof header (DIG-3795).
 *
 * Branch B leaf 1 of 3 (parent DIG-634 plan, CTO B1 approval 2026-10-15).
 * New module only; no wiring, no deletion.
 *
 * Digichat mints a signed token binding an embed host to an expiry. The embed
 * route verifies the signature before honouring a trial claim — a raw
 * client-asserted X-Embed-Trial-Proof value is NEVER trusted.
 *
 * Format: base64url(host|exp|sig), HMAC-SHA256 base64url.
 * TTL: 600 seconds (10 minutes).
 */

import { createHmac, timingSafeEqual } from "crypto";

/** Default trial proof lifetime: 600 seconds. */
export const TRIAL_PROOF_TTL_MS = 600_000;

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
 * Mint a signed trial proof token for an embed host.
 * Call server-side only.
 */
export function signTrialProof(
  host: string,
  secret: string,
  expiresAt?: number,
): string {
  const trimmedHost = host.trim();
  if (!trimmedHost) throw new Error("signTrialProof: host must be non-empty");
  if (!secret) throw new Error("signTrialProof: secret must be non-empty");
  const exp = expiresAt ?? Date.now() + TRIAL_PROOF_TTL_MS;
  const payload = `${trimmedHost}|${exp}`;
  const sig = hmacSign(secret, payload);
  return base64urlEncode(`${payload}|${sig}`);
}

/**
 * Verify a trial proof token and return the host, or null if
 * invalid/expired/malformed. Call server-side only.
 */
export function verifyTrialProof(
  token: string,
  secret: string,
): string | null {
  try {
    if (!token || !secret) return null;
    const decoded = base64urlDecode(token);
    const parts = decoded.split("|");
    if (parts.length !== 3) return null;

    const [host, expStr, sig] = parts;
    if (!host || !host.trim()) return null;
    const exp = Number(expStr);
    if (!Number.isFinite(exp) || Date.now() > exp) return null;

    const expectedPayload = `${host}|${exp}`;
    const expectedSig = hmacSign(secret, expectedPayload);

    // Constant-time comparison
    const sigBuf = Buffer.from(sig, "base64url");
    const expectedBuf = Buffer.from(expectedSig, "base64url");
    if (sigBuf.length !== expectedBuf.length) return null;
    if (!timingSafeEqual(sigBuf, expectedBuf)) return null;

    return host;
  } catch {
    return null;
  }
}
