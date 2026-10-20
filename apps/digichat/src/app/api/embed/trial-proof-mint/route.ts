/**
 * POST /api/embed/trial-proof-mint — mint an HMAC-signed trial proof token.
 *
 * Branch B leaf 2 of 3 (parent DIG-634 plan, CTO B1 approval 2026-10-15).
 * Companion to `POST /api/plan-proof` (#3662), which signs a plan TIER from a
 * user's Supabase claims. This route signs a HOST instead, for a monitor that
 * already knows which embed host it is checking: the tenant's answer-integrity
 * check needs a verifiable trial proof for a named host and has no dashboard
 * session to present.
 *
 * Request:  Header: x-embed-monitor-token: <server-side monitor secret>
 *           Body: { host: "tenant.example.com" }
 * Response: 200 { proof: "<base64url-signed-token>" }
 *           401 monitor credential missing, too short, or not allowlisted
 *
 * Authentication is the monitor secret, not a user session, so this route is
 * self-authenticating: nothing here reads a client-asserted tier or expiry.
 * That is the same property that makes the minted token trustworthy — a raw
 * client-asserted X-Embed-Trial-Proof value is NEVER trusted, because only
 * this server holds DIGICHAT_TRIAL_PROOF_SECRET and only it can produce a
 * signature that verifies. The secret itself never appears in any response.
 *
 * The credential is deliberately x-embed-monitor-token (DIG-613), NOT
 * X-Embed-Token: that one is a Stripe-style publishable key rendered into the
 * embedding page on purpose, so a mint endpoint keyed on it would be an
 * unauthenticated public endpoint.
 */

import { NextResponse } from "next/server";
import {
  EMBED_MONITOR_TOKEN_HEADER,
  isAllowlistedMonitorToken,
} from "@/lib/embed-monitor-token";
import { signTrialProof } from "@/lib/trial-proof";

export async function POST(req: Request): Promise<NextResponse> {
  // Authenticate FIRST, before parsing anything the caller sent: an
  // unauthenticated caller must learn "401", never a 400 that reveals how this
  // route parses its body. isAllowlistedMonitorToken fails open (an unconfigured
  // or absent allowlist reads as "not a monitor"), so with no
  // DIGICHAT_MONITOR_TOKENS every caller lands here and the route is simply
  // unusable — it is never open.
  if (!isAllowlistedMonitorToken(req.headers.get(EMBED_MONITOR_TOKEN_HEADER))) {
    return NextResponse.json(
      { error: "unauthorized", message: "Invalid or missing monitor token." },
      { status: 401 },
    );
  }

  let host: unknown;
  try {
    const body = (await req.json()) as { host?: unknown };
    host = body?.host;
  } catch {
    return NextResponse.json(
      { error: "bad_request", message: "Body must be JSON with a host." },
      { status: 400 },
    );
  }

  // The host is the ONLY caller-supplied input that reaches the signer, so it
  // is validated here rather than inside signTrialProof — a throw there would
  // surface as an opaque 500 instead of a 400 the caller can act on.
  if (typeof host !== "string" || !host.trim()) {
    return NextResponse.json(
      { error: "bad_request", message: "host must be a non-empty string." },
      { status: 400 },
    );
  }

  // Fail CLOSED when the signing secret is absent: minting with an empty secret
  // would produce a token whose signature anyone can recompute, which is worse
  // than not minting at all. Env NAMES only — never a value.
  const secret = process.env.DIGICHAT_TRIAL_PROOF_SECRET?.trim();
  if (!secret) {
    console.error(
      "[trial-proof-mint] DIGICHAT_TRIAL_PROOF_SECRET not configured",
    );
    return NextResponse.json(
      { error: "server_error", message: "Trial proof service unavailable." },
      { status: 503 },
    );
  }

  // Default TTL lives in trial-proof.ts (TRIAL_PROOF_TTL_MS) so the mint route
  // cannot drift from the verifier.
  return NextResponse.json({ proof: signTrialProof(host, secret) });
}