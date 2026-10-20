/**
 * POST /api/embed/trial-proof-mint — mint an HMAC-signed trial proof token.
 *
 * Branch B leaf 2 of 3 (parent DIG-634 plan, CTO B1 approval 2026-10-15).
 * Companion to `POST /api/plan-proof` (#3662), which signs a plan TIER from a
 * user's Supabase claims. This route signs a HOST instead, for a caller that
 * already knows which embed host it is checking: the tenant's answer-integrity
 * check needs a verifiable trial proof for a named host and has no dashboard
 * session to present.
 *
 * TWO credentials, TWO mechanisms, and they never mix.
 *
 * 1. Tenant credential — header x-embed-tenant-mint-token, list in
 *    DIGICHAT_TENANT_MINT_CREDENTIALS as comma separated `host=token` pairs
 *    (embed-tenant-mint-token.ts). It is bound to ONE host: the route mints
 *    the proof for the host in that pair and refuses every other host, so a
 *    tenant can never mint a proof for another tenant's host. When the header
 *    is present the tenant rule decides the whole request — there is NO
 *    fall-through to the monitor rule, so a tenant token is never read as a
 *    monitor token. The credential is a server-side secret: the tenant's
 *    backend holds it, never the embedding page.
 * 2. Monitor credential — header x-embed-monitor-token, allowlist in
 *    DIGICHAT_MONITOR_TOKENS (embed-monitor-token.ts). Unchanged, host
 *    unscoped, and only for an internal monitor that already knows its host.
 *
 * Request:  Header: x-embed-tenant-mint-token: <host-scoped tenant secret>
 *              or  x-embed-monitor-token: <server-side monitor secret>
 *           Body: { host: "tenant.example.com" }
 * Response: 200 { proof: "<base64url-signed-token>" }
 *           401 credential missing, too short, not allowlisted, or not scoped
 *                  to the requested host
 *
 * Authentication is a server-side secret, not a user session, so this route is
 * self-authenticating: nothing here reads a client-asserted tier or expiry.
 * That is the same property that makes the minted token trustworthy — a raw
 * client-asserted X-Embed-Trial-Proof value is NEVER trusted, because only
 * this server holds DIGICHAT_TRIAL_PROOF_SECRET and only it can produce a
 * signature that verifies. The secret itself never appears in any response.
 *
 * No credential is X-Embed-Token: that one is a Stripe-style publishable key
 * rendered into the embedding page on purpose, so a mint endpoint keyed on it
 * would be an unauthenticated public endpoint.
 */

import { NextResponse } from "next/server";
import {
  EMBED_MONITOR_TOKEN_HEADER,
  isAllowlistedMonitorToken,
} from "@/lib/embed-monitor-token";
import {
  EMBED_TENANT_MINT_TOKEN_HEADER,
  tenantMintCredentialHost,
  tenantMintHostMatches,
} from "@/lib/embed-tenant-mint-token";
import { signTrialProof } from "@/lib/trial-proof";

/**
 * The host the caller asked for, or the response to send instead.
 *
 * The body is read once and only after the caller proved which credential it
 * holds, so an unauthenticated caller learns "401" and never a 400 that
 * reveals how this route parses its body.
 */
async function readRequestedHost(
  req: Request,
): Promise<{ host: string } | { error: NextResponse }> {
  let host: unknown;
  try {
    const body = (await req.json()) as { host?: unknown };
    host = body?.host;
  } catch {
    return {
      error: NextResponse.json(
        { error: "bad_request", message: "Body must be JSON with a host." },
        { status: 400 },
      ),
    };
  }

  // The host is the ONLY caller-supplied input that reaches the signer, so it
  // is validated here rather than inside signTrialProof — a throw there would
  // surface as an opaque 500 instead of a 400 the caller can act on.
  if (typeof host !== "string" || !host.trim()) {
    return {
      error: NextResponse.json(
        { error: "bad_request", message: "host must be a non-empty string." },
        { status: 400 },
      ),
    };
  }

  return { host };
}

export async function POST(req: Request): Promise<NextResponse> {
  // The tenant credential, when PRESENT, decides the whole request. There is
  // no fall-through to the monitor rule: a tenant token is never read as a
  // monitor token, and a monitor token is never smuggled through the tenant
  // path. An unknown, ambiguous or unscoped tenant credential is refused
  // without reading the body, so a caller that holds no valid credential
  // learns nothing about how this route parses.
  const tenantCredential = req.headers.get(EMBED_TENANT_MINT_TOKEN_HEADER);
  if (tenantCredential !== null) {
    const boundHost = tenantMintCredentialHost(tenantCredential);
    if (!boundHost) {
      return NextResponse.json(
        {
          error: "unauthorized",
          message: "Invalid or missing tenant credential.",
        },
        { status: 401 },
      );
    }

    const requested = await readRequestedHost(req);
    if ("error" in requested) return requested.error;

    // The credential is bound to one host. Any other host is refused and
    // nothing is minted.
    if (!tenantMintHostMatches(requested.host, boundHost)) {
      return NextResponse.json(
        {
          error: "unauthorized",
          message: "Invalid or missing tenant credential.",
        },
        { status: 401 },
      );
    }

    // Fail CLOSED when the signing secret is absent: minting with an empty
    // secret would produce a token whose signature anyone can recompute, which
    // is worse than not minting at all. Env NAMES only — never a value.
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

    // The proof is minted for the host IN THE PAIR, never for the spelling in
    // the request: the request can only say WHICH host it wants, not WHAT
    // gets signed. So a caller can never obtain a proof for a host it does
    // not hold the credential for.
    //
    // Default TTL lives in trial-proof.ts (TRIAL_PROOF_TTL_MS) so the mint
    // route cannot drift from the verifier.
    return NextResponse.json({ proof: signTrialProof(boundHost, secret) });
  }

  // The monitor path, unchanged: authenticate FIRST, before parsing anything
  // the caller sent. isAllowlistedMonitorToken fails open (an unconfigured or
  // absent allowlist reads as "not a monitor"), so with no
  // DIGICHAT_MONITOR_TOKENS every caller lands here and the route is simply
  // unusable — it is never open.
  if (!isAllowlistedMonitorToken(req.headers.get(EMBED_MONITOR_TOKEN_HEADER))) {
    return NextResponse.json(
      { error: "unauthorized", message: "Invalid or missing monitor token." },
      { status: 401 },
    );
  }

  const requested = await readRequestedHost(req);
  if ("error" in requested) return requested.error;

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

  // The monitor credential is host-unscoped by design: it is an internal
  // monitor that already knows which host it is checking, and the monitor
  // mechanism itself does not change.
  return NextResponse.json({ proof: signTrialProof(requested.host, secret) });
}
