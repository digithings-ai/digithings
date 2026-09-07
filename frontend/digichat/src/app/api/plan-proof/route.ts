/**
 * POST /api/plan-proof — mint an HMAC-signed plan tier proof token (#3662).
 *
 * The dashboard (Cloudflare Pages static export) cannot host API routes, so
 * this route lives in digichat's Next.js server.  The embed iframe calls it
 * after receiving the user's tier via postMessage from the authenticated
 * dashboard parent.
 *
 * Request:  { tier: "desk" | "studio" | "enterprise" }
 *           Header: X-Embed-Token: <tenant embed token>
 *           Header: X-Embed-Host: digiquant.io
 * Response: { proof: "<base64url-signed-token>", exp: <ms-epoch> }
 *
 * The embed token authenticates the caller against the tenant registry;
 * only registered tenants may obtain signed proofs.  The HMAC secret
 * (DIGICHAT_PLAN_PROOF_SECRET) never reaches the client.
 */

import { NextResponse } from "next/server";
import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";
import { signPlanProof, isValidPlanTier } from "@/lib/plan-proof";

const VALID_PROOF_TIERS = ["desk", "studio", "enterprise"] as const;

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
  // Other tenants (digithings.ai, occ, datatap) don't use plan-tier gating.
  if (tenant.slug !== "digiquant-dashboard") {
    return NextResponse.json(
      { error: "forbidden", message: "Plan proof not available for this tenant." },
      { status: 403 },
    );
  }

  const secret = process.env.DIGICHAT_PLAN_PROOF_SECRET?.trim();
  if (!secret) {
    console.error("[plan-proof] DIGICHAT_PLAN_PROOF_SECRET not configured");
    return NextResponse.json(
      { error: "server_error", message: "Plan proof service unavailable." },
      { status: 503 },
    );
  }

  let body: { tier?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const tier = body.tier?.trim().toLowerCase();
  if (!tier || !isValidPlanTier(tier) || !VALID_PROOF_TIERS.includes(tier as (typeof VALID_PROOF_TIERS)[number])) {
    return NextResponse.json(
      {
        error: "invalid_tier",
        message: `tier must be one of: ${VALID_PROOF_TIERS.join(", ")}`,
      },
      { status: 400 },
    );
  }

  const proof = signPlanProof(tier as (typeof VALID_PROOF_TIERS)[number], secret);
  const exp = Date.now() + 300_000; // 5 minutes, matches PROOF_TTL_MS

  return NextResponse.json({ proof, exp });
}
