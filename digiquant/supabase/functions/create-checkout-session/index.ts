/**
 * create-checkout-session — logged-in user starts Stripe Checkout (T2).
 *
 * verify_jwt = true. Caller → workspace via workspace_members; reuses
 * stripe_customer_id when present. success/cancel URLs from NEXT_PUBLIC_APP_URL.
 */

import {
  createCheckoutSession,
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
import { loadPriceTierEnv, type PlanTier } from "../_shared/tiers.ts";

type Interval = "monthly" | "annual";
type PaidTier = Extract<PlanTier, "baseline" | "custom">;

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return jsonError(405, "METHOD_NOT_ALLOWED", "POST only");
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
  const user = userData.user;

  let body: { tier?: string; interval?: string; workspace_id?: string };
  try {
    body = await req.json();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const tier = body.tier as PaidTier | undefined;
  const interval = (body.interval ?? "monthly") as Interval;
  if (tier !== "baseline" && tier !== "custom") {
    return jsonError(400, "INVALID_TIER", "tier must be baseline or custom");
  }
  if (interval !== "monthly" && interval !== "annual") {
    return jsonError(400, "INVALID_INTERVAL", "interval must be monthly or annual");
  }

  const prices = loadPriceTierEnv();
  const priceId = pickPriceId(tier, interval, prices);
  if (!priceId) {
    return jsonError(500, "PRICE_NOT_CONFIGURED", "Price id not configured");
  }

  let admin;
  try {
    admin = createAdminClient();
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const authz = await requireWorkspaceOwner(
    admin,
    { id: user.id, email: user.email },
    body.workspace_id ?? null,
  );
  if (!authz.ok) return authz.response;

  const appUrl = (Deno.env.get("NEXT_PUBLIC_APP_URL") ?? "").replace(/\/$/, "");
  if (!appUrl) {
    return jsonError(500, "APP_URL_NOT_CONFIGURED", "App URL not configured");
  }

  try {
    const secret = requireStripeSecret();
    const session = await createCheckoutSession(secret, {
      customerId: authz.workspace.stripe_customer_id,
      customerEmail: user.email,
      priceId,
      workspaceId: authz.workspace.id,
      successUrl: `${appUrl}/settings/billing?checkout=success`,
      cancelUrl: `${appUrl}/settings/billing?checkout=cancel`,
    });
    return jsonOk({ id: session.id, url: session.url });
  } catch (err) {
    if (err instanceof StripeHttpError) {
      return jsonError(err.status, err.code, err.message);
    }
    console.error("create-checkout-session error", err instanceof Error ? err.name : "unknown");
    return jsonError(502, "STRIPE_UPSTREAM", "Unable to create checkout session");
  }
});

function pickPriceId(
  tier: PaidTier,
  interval: Interval,
  prices: ReturnType<typeof loadPriceTierEnv>,
): string {
  if (tier === "baseline") {
    return interval === "monthly" ? prices.baselineMonthly : prices.baselineAnnual;
  }
  return interval === "monthly" ? prices.customMonthly : prices.customAnnual;
}
