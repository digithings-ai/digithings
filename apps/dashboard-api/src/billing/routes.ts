/**
 * The three ported billing routes.
 *
 * Each handler replaces a `Deno.serve(async (req) => …)` with
 * `(req, env, deps) => Promise<Response>`. The CHECK ORDER, the status codes,
 * the error codes and the JSON bodies are all identical to the edge functions,
 * because the dashboard parses them: a reordering (for example resolving the
 * workspace before checking the bearer) changes what a caller observes on a
 * misconfigured deployment.
 */

import { requireBearerHeader, requireWorkspaceOwner } from "./billing-auth";
import { corsPreflight } from "./cors";
import { envFirst, type BillingEnv } from "./env";
import { createPostgrestAdmin, resolveUserFromToken, type AdminDb } from "./admin";
import { jsonError, jsonOk } from "./http";
import { settingsBillingReturnUrl } from "./app-url";
import { loadPriceTierEnv, pickPriceId, priceEnvKey, type Interval, type PaidTier } from "./tiers";
import {
  createBillingPortalSession,
  createCheckoutSession,
  parseStripeEvent,
  requireStripeSecret,
  requireWebhookSecret,
  StripeHttpError,
  verifyStripeSignature,
} from "./stripe";
import { handleStripeEvent } from "./webhook-handler";

const PAID_TIERS: readonly string[] = ["brief", "desk", "studio"];
const INTERVALS: readonly string[] = ["monthly", "annual"];

export interface BillingDeps {
  /**
   * Overrides how the routes obtain their `AdminDb`. Omit it in production
   * (the routes then build the PostgREST client from `env`) and inject a stub
   * in tests. Constructing it lazily matters: `createPostgrestAdmin` THROWS
   * when the Supabase env is missing, and the routes turn that throw into the
   * 500 `ADMIN_NOT_CONFIGURED` the edge functions returned.
   */
  createAdmin?: () => AdminDb;
}

/** The edge function's `createAdminClient()` call site, in one place. */
function adminFor(deps: BillingDeps, env: BillingEnv): AdminDb {
  return deps.createAdmin ? deps.createAdmin() : createPostgrestAdmin(env);
}

/**
 * stripe-webhook. `verify_jwt = false` on the edge function: the caller is
 * Stripe, authenticated by the signature over the RAW body, not by a bearer
 * token. The body is read exactly once, before any parsing, because the
 * signature covers those exact bytes.
 */
export async function handleStripeWebhook(
  req: Request,
  env: BillingEnv,
  deps: BillingDeps,
): Promise<Response> {
  if (req.method !== "POST") return jsonError(405, "METHOD_NOT_ALLOWED", "POST only");

  let rawBody: string;
  try {
    rawBody = await req.text();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Unable to read body");
  }

  let secret: string;
  try {
    secret = requireWebhookSecret(env);
    await verifyStripeSignature(rawBody, req.headers.get("stripe-signature"), secret);
  } catch (err) {
    if (err instanceof StripeHttpError) return jsonError(err.status, err.code, err.message);
    return jsonError(400, "INVALID_SIGNATURE", "Signature verification failed");
  }

  let event;
  try {
    event = parseStripeEvent(rawBody);
  } catch (err) {
    if (err instanceof StripeHttpError) return jsonError(err.status, err.code, err.message);
    return jsonError(400, "INVALID_PAYLOAD", "Not a Stripe event");
  }

  let admin: AdminDb;
  try {
    admin = adminFor(deps, env);
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  try {
    const result = await handleStripeEvent(admin, env, event);
    return jsonOk(result);
  } catch (err) {
    // Log the error NAME only: a message can carry a row payload or a Stripe id.
    console.error("stripe-webhook handler error", err instanceof Error ? err.name : "unknown");
    return jsonError(500, "WEBHOOK_FAILED", "Webhook processing failed");
  }
}

/** customer-portal. `verify_jwt = true` on the edge function. */
export async function handleCustomerPortal(
  req: Request,
  env: BillingEnv,
  deps: BillingDeps,
): Promise<Response> {
  if (req.method === "OPTIONS") return corsPreflight();
  if (req.method !== "POST" && req.method !== "GET") {
    return jsonError(405, "METHOD_NOT_ALLOWED", "GET or POST only");
  }

  const authHeader = req.headers.get("Authorization");
  const missingBearer = requireBearerHeader(authHeader);
  if (missingBearer) return missingBearer;

  if (!envFirst(env, ["SUPABASE_URL", "CORE_SUPABASE_URL"])) {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }
  if (!envFirst(env, ["SUPABASE_ANON_KEY", "CORE_SUPABASE_ANON_KEY"])) {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const user = await resolveUserFromToken(env, authHeader!);
  if (!user) return jsonError(401, "UNAUTHENTICATED", "Invalid session");

  let requestedWorkspaceId: string | null;
  if (req.method === "POST") {
    requestedWorkspaceId = null;
    try {
      const body = (await req.json()) as { workspace_id?: string };
      if (typeof body.workspace_id === "string") requestedWorkspaceId = body.workspace_id;
    } catch {
      // An empty body is legitimate here: the workspace then resolves by token.
    }
  } else {
    requestedWorkspaceId = new URL(req.url).searchParams.get("workspace_id");
  }

  let admin: AdminDb;
  try {
    admin = adminFor(deps, env);
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const authz = await requireWorkspaceOwner(admin, user, requestedWorkspaceId);
  if (!authz.ok) return authz.response;
  if (!authz.workspace.stripe_customer_id) {
    return jsonError(409, "NO_STRIPE_CUSTOMER", "No Stripe customer on workspace");
  }

  const appUrl = (envFirst(env, ["NEXT_PUBLIC_APP_URL", "APP_URL"]) ?? "").replace(/\/$/, "");
  if (!appUrl) return jsonError(500, "APP_URL_NOT_CONFIGURED", "App URL not configured");

  try {
    const secret = requireStripeSecret(env);
    const session = await createBillingPortalSession(secret, {
      customerId: authz.workspace.stripe_customer_id,
      returnUrl: settingsBillingReturnUrl(appUrl),
    });
    return jsonOk({ url: session.url });
  } catch (err) {
    if (err instanceof StripeHttpError) return jsonError(err.status, err.code, err.message);
    console.error("customer-portal error", err instanceof Error ? err.name : "unknown");
    return jsonError(502, "STRIPE_UPSTREAM", "Unable to create portal session");
  }
}

/** create-checkout-session. `verify_jwt = true` on the edge function. */
export async function handleCreateCheckoutSession(
  req: Request,
  env: BillingEnv,
  deps: BillingDeps,
): Promise<Response> {
  if (req.method === "OPTIONS") return corsPreflight();
  if (req.method !== "POST") return jsonError(405, "METHOD_NOT_ALLOWED", "POST only");

  const authHeader = req.headers.get("Authorization");
  const missingBearer = requireBearerHeader(authHeader);
  if (missingBearer) return missingBearer;

  if (!envFirst(env, ["SUPABASE_URL", "CORE_SUPABASE_URL"])) {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }
  if (!envFirst(env, ["SUPABASE_ANON_KEY", "CORE_SUPABASE_ANON_KEY"])) {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const user = await resolveUserFromToken(env, authHeader!);
  if (!user) return jsonError(401, "UNAUTHENTICATED", "Invalid session");

  let body: { tier?: PaidTier; interval?: Interval; workspace_id?: string };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Body must be JSON");
  }

  const tier = body.tier;
  if (!tier || !PAID_TIERS.includes(tier)) {
    return jsonError(400, "INVALID_TIER", "tier must be brief, desk, or studio");
  }
  const interval = body.interval ?? "monthly";
  if (!INTERVALS.includes(interval)) {
    return jsonError(400, "INVALID_INTERVAL", "interval must be monthly or annual");
  }

  const priceId = pickPriceId(tier, interval, loadPriceTierEnv(env));
  if (!priceId) {
    const envName = priceEnvKey(tier, interval);
    return jsonError(
      500,
      "PRICE_NOT_CONFIGURED",
      `${envName} is not set on Edge Function secrets`,
    );
  }

  let admin: AdminDb;
  try {
    admin = adminFor(deps, env);
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  const authz = await requireWorkspaceOwner(admin, user, body.workspace_id ?? null);
  if (!authz.ok) return authz.response;

  const appUrl = (envFirst(env, ["NEXT_PUBLIC_APP_URL", "APP_URL"]) ?? "").replace(/\/$/, "");
  if (!appUrl) return jsonError(500, "APP_URL_NOT_CONFIGURED", "App URL not configured");

  try {
    const secret = requireStripeSecret(env);
    const session = await createCheckoutSession(secret, {
      customerId: authz.workspace.stripe_customer_id,
      customerEmail: user.email,
      priceId,
      workspaceId: authz.workspace.id,
      successUrl: settingsBillingReturnUrl(appUrl, "success"),
      cancelUrl: settingsBillingReturnUrl(appUrl, "cancel"),
    });
    return jsonOk({ id: session.id, url: session.url });
  } catch (err) {
    if (err instanceof StripeHttpError) return jsonError(err.status, err.code, err.message);
    console.error("create-checkout-session error", err instanceof Error ? err.name : "unknown");
    return jsonError(502, "STRIPE_UPSTREAM", "Unable to create checkout session");
  }
}