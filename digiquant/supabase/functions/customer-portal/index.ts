/**
 * customer-portal — Stripe Customer Portal session for the caller's workspace (T2).
 *
 * verify_jwt = true. Requires an existing stripe_customer_id on the workspace.
 * return_url from NEXT_PUBLIC_APP_URL.
 */

import {
  createBillingPortalSession,
  requireStripeSecret,
  StripeHttpError,
} from "../_shared/stripe.ts";
import {
  requireBearerHeader,
  requireWorkspaceOwner,
} from "../_shared/billing-auth.ts";
import {
  createAdminClient,
  jsonError,
  jsonOk,
} from "../_shared/supabase-admin.ts";
import { createClient } from "@supabase/supabase-js";

Deno.serve(async (req) => {
  if (req.method !== "POST" && req.method !== "GET") {
    return jsonError(405, "METHOD_NOT_ALLOWED", "GET or POST only");
  }

  const authHeader = req.headers.get("Authorization");
  const missing = requireBearerHeader(authHeader);
  if (missing) return missing;

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? Deno.env.get("CORE_SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("CORE_SUPABASE_ANON_KEY");
  if (!supabaseUrl || !anonKey) {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader! } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userErr } = await userClient.auth.getUser();
  if (userErr || !userData?.user) {
    return jsonError(401, "UNAUTHENTICATED", "Invalid session");
  }

  let requestedWorkspaceId: string | null = null;
  if (req.method === "POST") {
    try {
      const body = await req.json() as { workspace_id?: string };
      if (typeof body.workspace_id === "string") {
        requestedWorkspaceId = body.workspace_id;
      }
    } catch {
      // empty body is fine for portal
    }
  } else {
    const url = new URL(req.url);
    requestedWorkspaceId = url.searchParams.get("workspace_id");
  }

  let admin;
  try {
    admin = createAdminClient();
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const authz = await requireWorkspaceOwner(
    admin,
    { id: userData.user.id, email: userData.user.email },
    requestedWorkspaceId,
  );
  if (!authz.ok) return authz.response;

  const customerId = authz.workspace.stripe_customer_id;
  if (!customerId) {
    return jsonError(409, "NO_STRIPE_CUSTOMER", "No Stripe customer on workspace");
  }

  const appUrl = (Deno.env.get("NEXT_PUBLIC_APP_URL") ?? "").replace(/\/$/, "");
  if (!appUrl) {
    return jsonError(500, "APP_URL_NOT_CONFIGURED", "App URL not configured");
  }

  try {
    const secret = requireStripeSecret();
    const session = await createBillingPortalSession(secret, {
      customerId,
      returnUrl: `${appUrl}/settings/billing`,
    });
    return jsonOk({ url: session.url });
  } catch (err) {
    if (err instanceof StripeHttpError) {
      return jsonError(err.status, err.code, err.message);
    }
    console.error("customer-portal error", err instanceof Error ? err.name : "unknown");
    return jsonError(502, "STRIPE_UPSTREAM", "Unable to create portal session");
  }
});
