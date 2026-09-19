/**
 * POST /api/plan-proof — mint an HMAC-signed plan tier proof token (#3662).
 *
 * The dashboard (Cloudflare Pages static export) cannot host API routes, so
 * this route lives in digichat's Next.js server. The embed iframe calls it
 * after receiving the user's Supabase access_token via postMessage from the
 * authenticated dashboard parent.
 *
 * Request:  Authorization: Bearer <supabase access_token>
 *           Header: X-Embed-Token: <tenant embed token>
 *           Header: X-Embed-Host: digiquant.io
 *           Body is ignored for authorization (client tier assertions are never trusted).
 * Response: { proof: "<base64url-signed-token>", exp: <ms-epoch>, tier: "desk"|... }
 *
 * Flow: verify embed tenant → verify Supabase access token via /auth/v1/user →
 * read app_metadata.plan_tier → fall back to the effective tier from the
 * my_access RPC (max(plan_tier, plan_floor)) → mint an HMAC for a Desk+ tier
 * only. Free/brief claims and FX Hub-only invitees without a desk floor
 * receive `403 plan_tier_required` — a product grant never mints a
 * chat-eligible proof. DIGICHAT_PLAN_PROOF_SECRET never reaches the client.
 */

import { NextResponse } from "next/server";
import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";
import {
  signPlanProof,
  isProofEligibleTier,
  resolveEffectivePlanTierFromDashboardAccessToken,
  resolvePlanTierFromDashboardAccessToken,
  type ProofEligibleTier,
} from "@/lib/plan-proof";

function bearerToken(req: Request): string | null {
  const raw = req.headers.get("authorization")?.trim();
  if (!raw) return null;
  const match = /^Bearer\s+(.+)$/i.exec(raw);
  return match?.[1]?.trim() || null;
}

export async function POST(req: Request): Promise<NextResponse> {
  // Authenticate the embed caller via tenant registry + X-Embed-Token.
  const tenant = resolveVerifiedEmbedTenant(req);
  if (!tenant) {
    return NextResponse.json(
      { error: "unauthorized", message: "Invalid or missing embed token." },
      { status: 401 },
    );
  }

  // Only digiquant.io dashboard tenant is eligible for plan proof signing.
  if (tenant.slug !== "digiquant-dashboard") {
    return NextResponse.json(
      { error: "forbidden", message: "Plan proof not available for this tenant." },
      { status: 403 },
    );
  }

  const accessToken = bearerToken(req);
  if (!accessToken) {
    return NextResponse.json(
      {
        error: "unauthorized",
        message: "Authorization: Bearer <supabase access_token> required.",
      },
      { status: 401 },
    );
  }

  const secret = process.env.DIGICHAT_PLAN_PROOF_SECRET?.trim();
  const supabaseUrl = process.env.DIGICHAT_DASHBOARD_SUPABASE_URL?.trim();
  const anonKey = process.env.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY?.trim();
  if (!secret || !supabaseUrl || !anonKey) {
    console.error(
      "[plan-proof] DIGICHAT_PLAN_PROOF_SECRET / DIGICHAT_DASHBOARD_SUPABASE_URL / DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY not configured",
    );
    return NextResponse.json(
      { error: "server_error", message: "Plan proof service unavailable." },
      { status: 503 },
    );
  }

  // Claims first — never trust body.tier / X-Embed-Plan-Tier / ?plan_tier=.
  // Fall back to the effective tier (max(plan_tier, plan_floor) via my_access)
  // so desk-floor invitees can chat, while free/brief and FX Hub-only grants
  // without a desk floor still get 403 (#4305).
  const claimsTier = await resolvePlanTierFromDashboardAccessToken(accessToken, {
    supabaseUrl,
    anonKey,
  });
  let proofTier: ProofEligibleTier | null =
    claimsTier && isProofEligibleTier(claimsTier) ? claimsTier : null;
  if (!proofTier) {
    const effectiveTier = await resolveEffectivePlanTierFromDashboardAccessToken(
      accessToken,
      { supabaseUrl, anonKey },
    );
    proofTier =
      effectiveTier && isProofEligibleTier(effectiveTier) ? effectiveTier : null;
  }
  if (!proofTier) {
    return NextResponse.json(
      {
        error: "plan_tier_required",
        message: "Chat requires desk+ plan tier from authenticated session claims.",
      },
      { status: 403 },
    );
  }

  const proof = signPlanProof(proofTier, secret);
  const exp = Date.now() + 300_000; // 5 minutes, matches PROOF_TTL_MS

  return NextResponse.json({ proof, exp, tier: proofTier });
}
