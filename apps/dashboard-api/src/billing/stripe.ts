/**
 * Stripe client — a port of `digiquant/supabase/functions/_shared/stripe.ts`.
 *
 * The only Deno-isms were `Deno.env.get` inside two default parameters, both of
 * which already took an injectable `getEnv`; the port passes the worker `env`
 * record instead. Signature verification, the event shape guard, and the two
 * session creators are otherwise byte-for-byte the same algorithm, so a Stripe
 * signature that validates today validates after the cutover.
 *
 * Deliberate parity rules carried over:
 * - never echo a Stripe error body (it can carry customer PII) — 502 only;
 * - never log a secret key;
 * - the webhook signature is checked against the RAW body, so the webhook route
 *   must read `req.text()` exactly once and before any parsing.
 */

import { envFirst, envGet, type BillingEnv } from "./env";

const STRIPE_API = "https://api.stripe.com/v1";

export class StripeHttpError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "StripeHttpError";
    this.status = status;
    this.code = code;
  }
}

export interface StripeEvent {
  id: string;
  type: string;
  created: number;
  data: { object: Record<string, unknown> };
}

export interface CheckoutSessionArgs {
  customerId?: string | null;
  customerEmail?: string | null;
  priceId: string;
  workspaceId: string;
  successUrl: string;
  cancelUrl: string;
}

export interface CheckoutSessionResult {
  id: string;
  url: string | null;
}

export function requireStripeSecret(env: BillingEnv): string {
  const secret = envGet(env, "STRIPE_SECRET_KEY");
  if (!secret) {
    throw new StripeHttpError(500, "STRIPE_NOT_CONFIGURED", "Stripe is not configured");
  }
  return secret;
}

export function requireWebhookSecret(env: BillingEnv): string {
  const secret = envFirst(env, ["STRIPE_WEBHOOK_SECRET"]);
  if (!secret) {
    throw new StripeHttpError(500, "STRIPE_NOT_CONFIGURED", "Stripe webhook is not configured");
  }
  return secret;
}

/** Constant-time compare that does not leak length via early exit. */
function timingSafeEqual(a: string, b: string): boolean {
  const encoder = new TextEncoder();
  const aa = encoder.encode(a);
  const bb = encoder.encode(b);
  if (aa.length !== bb.length) {
    // Walk the longer buffer so the work is independent of where they differ.
    const max = Math.max(aa.length, bb.length);
    let diff = aa.length ^ bb.length;
    for (let i = 0; i < max; i++) diff |= (aa[i] ?? 0) ^ (bb[i] ?? 0);
    return diff === 0;
  }
  let diff = 0;
  for (let i = 0; i < aa.length; i++) diff |= aa[i] ^ bb[i];
  return diff === 0;
}

function parseStripeSignatureHeader(header: string): { t: string | null; v1: string[] } {
  let timestamp: string | null = null;
  const v1: string[] = [];
  for (const part of header.split(",")) {
    const trimmed = part.trim();
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq);
    const value = trimmed.slice(eq + 1);
    if (key === "t") timestamp = value;
    else if (key === "v1") v1.push(value);
  }
  return { t: timestamp, v1 };
}

async function hmacSha256Hex(secret: string, payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyStripeSignature(
  rawBody: string,
  signatureHeader: string | null,
  webhookSecret: string,
  toleranceSeconds = 300,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): Promise<void> {
  if (!signatureHeader) {
    throw new StripeHttpError(400, "INVALID_SIGNATURE", "Missing Stripe-Signature header");
  }
  const { t, v1 } = parseStripeSignatureHeader(signatureHeader);
  if (!t || v1.length === 0) {
    throw new StripeHttpError(400, "INVALID_SIGNATURE", "Malformed Stripe-Signature header");
  }
  const ts = Number(t);
  if (!Number.isFinite(ts)) {
    throw new StripeHttpError(400, "INVALID_SIGNATURE", "Invalid signature timestamp");
  }
  if (Math.abs(nowSeconds - ts) > toleranceSeconds) {
    throw new StripeHttpError(400, "INVALID_SIGNATURE", "Signature timestamp outside tolerance");
  }
  const expected = await hmacSha256Hex(webhookSecret, `${t}.${rawBody}`);
  if (!v1.some((candidate) => timingSafeEqual(candidate, expected))) {
    throw new StripeHttpError(400, "INVALID_SIGNATURE", "Signature verification failed");
  }
}

export function parseStripeEvent(rawBody: string): StripeEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    throw new StripeHttpError(400, "INVALID_PAYLOAD", "Body is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null) {
    throw new StripeHttpError(400, "INVALID_PAYLOAD", "Not a Stripe event");
  }
  const candidate = parsed as Partial<StripeEvent>;
  if (
    typeof candidate.id !== "string" ||
    typeof candidate.type !== "string" ||
    typeof candidate.created !== "number"
  ) {
    throw new StripeHttpError(400, "INVALID_PAYLOAD", "Not a Stripe event");
  }
  return {
    id: candidate.id,
    type: candidate.type,
    created: candidate.created,
    data: { object: candidate.data?.object ?? {} },
  };
}

async function stripeForm(
  secretKey: string,
  method: "POST",
  path: string,
  params: Record<string, string>,
): Promise<Record<string, unknown>> {
  const body = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) body.set(key, value);
  const res = await fetch(`${STRIPE_API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${secretKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });
  const data = (await res.json()) as Record<string, unknown>;
  if (!res.ok) {
    // Never surface the Stripe body: it can carry request ids tied to customers.
    throw new StripeHttpError(502, "STRIPE_UPSTREAM", "Stripe request failed");
  }
  return data;
}

export async function createCheckoutSession(
  secretKey: string,
  args: CheckoutSessionArgs,
): Promise<CheckoutSessionResult> {
  const params: Record<string, string> = {
    mode: "subscription",
    "line_items[0][price]": args.priceId,
    "line_items[0][quantity]": "1",
    success_url: args.successUrl,
    cancel_url: args.cancelUrl,
    "metadata[workspace_id]": args.workspaceId,
    "subscription_data[metadata][workspace_id]": args.workspaceId,
  };
  if (args.customerId) params["customer"] = args.customerId;
  else if (args.customerEmail) params["customer_email"] = args.customerEmail;
  const session = await stripeForm(secretKey, "POST", "/checkout/sessions", params);
  return {
    id: String(session.id ?? ""),
    url: typeof session.url === "string" ? session.url : null,
  };
}

export async function createBillingPortalSession(
  secretKey: string,
  args: { customerId: string; returnUrl: string },
): Promise<{ url: string | null }> {
  const session = await stripeForm(secretKey, "POST", "/billing_portal/sessions", {
    customer: args.customerId,
    return_url: args.returnUrl,
  });
  return { url: typeof session.url === "string" ? session.url : null };
}