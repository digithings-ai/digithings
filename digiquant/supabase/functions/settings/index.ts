/**
 * settings — authenticated dashboard Settings workspace backend (T3).
 *
 * Routes: GET/PATCH profile, GET/POST brokers, GET/PATCH notifications,
 * GET notifications/log, GET jobs, GET fills, GET app-urls,
 * POST /access/redeem-invite.
 *
 * DEPLOY BLOCKED ON K3: sealing credentials requires the vault master key and
 * `broker_connections` table from K3. See README.md in this directory.
 */

import { createClient } from "@supabase/supabase-js";
import { requireBearerHeader } from "../_shared/billing-auth.ts";
import { corsPreflight, withCors } from "../_shared/cors.ts";
import {
  createDefaultDeps,
  handleSettingsRequest,
} from "../_shared/settings-handlers.ts";
import { createAdminClient, jsonError } from "../_shared/supabase-admin.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return corsPreflight();
  }

  const authHeader = req.headers.get("Authorization");
  const missing = requireBearerHeader(authHeader);
  if (missing) return withCors(missing);

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? Deno.env.get("CORE_SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("CORE_SUPABASE_ANON_KEY");
  if (!supabaseUrl || !anonKey) {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Settings backend not configured");
  }

  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader! } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userErr } = await userClient.auth.getUser();
  if (userErr || !userData?.user) {
    return jsonError(401, "UNAUTHENTICATED", "Invalid session");
  }

  let admin;
  try {
    admin = createAdminClient();
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Settings backend not configured");
  }

  try {
    return withCors(
      await handleSettingsRequest(
        req,
        createDefaultDeps(
          {
            id: userData.user.id,
            email: userData.user.email,
            plan_tier:
              typeof userData.user.app_metadata?.plan_tier === "string"
                ? userData.user.app_metadata.plan_tier
                : null,
          },
          admin,
        ),
      ),
    );
  } catch (err) {
    console.error("settings error", err instanceof Error ? err.name : "unknown");
    return jsonError(500, "INTERNAL", "Settings request failed");
  }
});
