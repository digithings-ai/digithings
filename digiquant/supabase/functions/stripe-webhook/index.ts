/**
 * stripe-webhook — dashboard consumer billing (T2 / roadmap P4).
 *
 * verify_jwt = false (configured in config.toml). Auth is Stripe-Signature with
 * STRIPE_WEBHOOK_SECRET — never rely on Supabase JWT for this path.
 *
 * Binding behavior:
 * 1. Verify signature → insert stripe_events first (duplicate ⇒ 200 no-op) →
 *    out-of-order guard via event.created → apply P4 mapping.
 * 2. Price → plan_tier via _shared/tiers.ts (brief/desk/studio; deleted ⇒ free).
 * 3. After tier change: update workspaces, then auth claim sync; on claim failure
 *    set claim_sync_pending=true and still return 200.
 */

import {
  parseStripeEvent,
  requireWebhookSecret,
  StripeHttpError,
  verifyStripeSignature,
} from "../_shared/stripe.ts";
import {
  createAdminClient,
  jsonError,
  jsonOk,
} from "../_shared/supabase-admin.ts";
import { handleStripeEvent } from "../_shared/webhook-handler.ts";

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return jsonError(405, "METHOD_NOT_ALLOWED", "POST only");
  }

  let rawBody: string;
  try {
    rawBody = await req.text();
  } catch {
    return jsonError(400, "INVALID_PAYLOAD", "Unable to read body");
  }

  try {
    const secret = requireWebhookSecret();
    await verifyStripeSignature(
      rawBody,
      req.headers.get("stripe-signature"),
      secret,
    );
  } catch (err) {
    if (err instanceof StripeHttpError) {
      return jsonError(err.status, err.code, err.message);
    }
    return jsonError(400, "INVALID_SIGNATURE", "Signature verification failed");
  }

  let event;
  try {
    event = parseStripeEvent(rawBody);
  } catch (err) {
    if (err instanceof StripeHttpError) {
      return jsonError(err.status, err.code, err.message);
    }
    return jsonError(400, "INVALID_PAYLOAD", "Not a Stripe event");
  }

  let admin;
  try {
    admin = createAdminClient();
  } catch {
    return jsonError(500, "ADMIN_NOT_CONFIGURED", "Billing backend not configured");
  }

  try {
    const result = await handleStripeEvent(admin, event);
    return jsonOk(result);
  } catch (err) {
    // Never leak stacks or secrets to Stripe / clients.
    console.error("stripe-webhook handler error", err instanceof Error ? err.name : "unknown");
    return jsonError(500, "WEBHOOK_FAILED", "Webhook processing failed");
  }
});
