/**
 * fx-hub-session — mints a session for a caller already verified to hold
 * fx_hub access.
 *
 * Check order is the edge function's: POST, shared secret, JSON, email,
 * key dictionaries, then the network. The secret key reads `fx_hub_grants`
 * and asks GoTrue for a magic link; the publishable key redeems it. No
 * legacy anon / service_role variable is consulted.
 */

import { envGet, readApiKey, type FxHubEnv } from "./env";
import { json, normalizeEmail, timingSafeEqual } from "./http";
import { generateMagicLink, lookupGrant, verifyOtp } from "./supabase-auth";

export async function handleFxHubSession(req: Request, env: FxHubEnv): Promise<Response> {
  if (req.method !== "POST") {
    return json({ ok: false, code: "METHOD_NOT_ALLOWED" }, 405);
  }

  const syncSecret = envGet(env, "FX_HUB_GRANT_SYNC_SECRET") ?? "";
  const presented = req.headers.get("X-Sync-Secret") ?? "";
  if (!syncSecret || !timingSafeEqual(presented, syncSecret)) {
    return json({ ok: false, code: "UNAUTHORIZED" }, 401);
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, code: "BAD_JSON" }, 400);
  }

  const email = normalizeEmail((body as { email?: unknown })?.email);
  if (!email || !email.includes("@")) {
    return json({ ok: false, code: "EMAIL_REQUIRED" }, 400);
  }

  const supabaseUrl = envGet(env, "SUPABASE_URL");
  const secretKey = readApiKey(env, "SUPABASE_SECRET_KEYS");
  const publishableKey = readApiKey(env, "SUPABASE_PUBLISHABLE_KEYS");
  if (!supabaseUrl || !secretKey || !publishableKey) {
    const missing = [
      !supabaseUrl ? "SUPABASE_URL" : null,
      !secretKey ? "SUPABASE_SECRET_KEYS[default]" : null,
      !publishableKey ? "SUPABASE_PUBLISHABLE_KEYS[default]" : null,
    ].filter((name): name is string => name !== null);
    console.error(
      `fx-hub-session: API keys not available, refusing to fall back to the ` +
        `deprecated legacy keys. Missing: ${missing.join(", ")}`,
    );
    return json(
      {
        ok: false,
        code: "API_KEYS_UNCONFIGURED",
        message: `project API keys not configured: ${missing.join(", ")}`,
      },
      500,
    );
  }

  const grant = await lookupGrant(supabaseUrl, secretKey, email);
  if (grant.error || !grant.data) {
    return json({ ok: false, code: "NOT_GRANTED" }, 403);
  }

  const link = await generateMagicLink(supabaseUrl, secretKey, email);
  const hashedToken = link.data.properties?.hashed_token;
  // GoTrue's flow type for this token is not always "magiclink". A first-seen
  // email is a signup confirmation; verify rejects a mismatched type.
  const verificationType = link.data.properties?.verification_type ?? "magiclink";
  if (link.error || !hashedToken) {
    return json(
      { ok: false, code: "LINK_FAILED", message: link.error?.message ?? "" },
      500,
    );
  }

  const verified = await verifyOtp(supabaseUrl, publishableKey, {
    type: verificationType,
    tokenHash: hashedToken,
  });
  const session = verified.data.session;
  if (verified.error || !session) {
    return json(
      { ok: false, code: "VERIFY_FAILED", message: verified.error?.message ?? "" },
      500,
    );
  }

  return json(
    {
      ok: true,
      access_token: session.access_token,
      refresh_token: session.refresh_token,
      expires_in: session.expires_in,
    },
    200,
  );
}
