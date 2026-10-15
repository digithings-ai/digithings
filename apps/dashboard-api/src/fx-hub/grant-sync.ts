/**
 * fx-hub-grant-sync — mirrors an fx_hub grant into `fx_hub_grants`.
 *
 * Same caller boundary as fx-hub-session (POST, then `X-Sync-Secret`). This
 * function needs only `SUPABASE_URL` and `SUPABASE_SECRET_KEYS[default]`.
 * The upsert is the secret key on `apikey`, with `on_conflict=email`.
 */

import { envGet, readApiKey, type FxHubEnv } from "./env";
import { json, normalizeEmail, timingSafeEqual } from "./http";
import { upsertGrant } from "./supabase-auth";

const SYNC_NOTE = "synced from core client_product_grants";

export async function handleFxHubGrantSync(req: Request, env: FxHubEnv): Promise<Response> {
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
  if (!supabaseUrl || !secretKey) {
    const missing = [
      !supabaseUrl ? "SUPABASE_URL" : null,
      !secretKey ? "SUPABASE_SECRET_KEYS[default]" : null,
    ].filter((name): name is string => name !== null);
    console.error(
      `fx-hub-grant-sync: API keys not available, refusing to fall back to the ` +
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

  const result = await upsertGrant(supabaseUrl, secretKey, { email, note: SYNC_NOTE });
  if (result.error) {
    return json({ ok: false, code: "DB_ERROR", message: result.error.message }, 500);
  }

  return json({ ok: true }, 200);
}
