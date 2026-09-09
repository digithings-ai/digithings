/**
 * Shared Stripe helpers for dashboard billing Edge Functions (T2).
 *
 * Secrets are read from Deno.env only — never log or return key material.
 * Signature verification uses the Stripe-Webhook-Signatures scheme (HMAC-SHA256).
 */

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

export function requireStripeSecret(
  getEnv: (key: string) => string | undefined = (k) => Deno.env.get(k),
): string {
  const key = getEnv("STRIPE_SECRET_KEY");
  if (!key) {
    throw new StripeHttpError(500, "STRIPE_NOT_CONFIGURED", "Stripe is not configured");
  }
  return key;
}

export function requireWebhookSecret(
  getEnv: (key: string) => string | undefined = (k) => Deno.env.get(k),
): string {
  const secret = getEnv("STRIPE_WEBHOOK_SECRET");
  if (!secret) {
    throw new StripeHttpError(500, "STRIPE_NOT_CONFIGURED", "Stripe webhook is not configured");
  }
  return secret;
}

/** Timing-safe string compare (constant-ish; avoids early exit on length mismatch alone). */
function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const aa = enc.encode(a);
  const bb = enc.encode(b);
  if (aa.length !== bb.length) {
    // Still walk both buffers so length leaks are harder.
    let diff = aa.length ^ bb.length;
    const n = Math.max(aa.length, bb.length);
    for (let i = 0; i < n; i++) {
      diff |= (aa[i] ?? 0) ^ (bb[i] ?? 0);
    }
    return diff === 0;
  }
  let diff = 0;
  for (let i = 0; i < aa.length; i++) {
    diff |= aa[i]! ^ bb[i]!;
  }
  return diff === 0;
}

function parseStripeSignatureHeader(header: string): { t: string; v1: string[] } {
  const parts = header.split(",").map((p) => p.trim());
  let t = "";
  const v1: string[] = [];
  for (const part of parts) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    const k = part.slice(0, eq);
    const v = part.slice(eq + 1);
    if (k === "t") t = v;
    if (k === "v1") v1.push(v);
  }
  return { t, v1 };
}

async function hmacSha256Hex(secret: string, payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload),
  );
  return [...new Uint8Array(sig)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Verify `Stripe-Signature` against the raw body. Throws StripeHttpError(400) on failure.
 * Does not log the secret or the signature header value.
 */
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
  const ok = v1.some((candidate) => timingSafeEqual(candidate, expected));
  if (!ok) {
    throw new StripeHttpError(400, "INVALID_SIGNATURE", "Signature verification failed");
  }
}

export interface StripeEvent {
  id: string;
  type: string;
  created: number;
  data: { object: Record<string, unknown> };
}

export function parseStripeEvent(rawBody: string): StripeEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    throw new StripeHttpError(400, "INVALID_PAYLOAD", "Body is not valid JSON");
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    typeof (parsed as StripeEvent).id !== "string" ||
    typeof (parsed as StripeEvent).type !== "string" ||
    typeof (parsed as StripeEvent).created !== "number"
  ) {
    throw new StripeHttpError(400, "INVALID_PAYLOAD", "Not a Stripe event");
  }
  return parsed as StripeEvent;
}

async function stripeForm(
  secretKey: string,
  method: "POST",
  path: string,
  params: Record<string, string>,
): Promise<Record<string, unknown>> {
  const body = new URLSearchParams(params);
  const res = await fetch(`${STRIPE_API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${secretKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });
  const json = await res.json() as Record<string, unknown>;
  if (!res.ok) {
    // Never echo Stripe error bodies that may contain request ids with customer PII.
    throw new StripeHttpError(502, "STRIPE_UPSTREAM", "Stripe request failed");
  }
  return json;
}

export async function createCheckoutSession(
  secretKey: string,
  args: {
    customerId?: string | null;
    customerEmail?: string | null;
    priceId: string;
    workspaceId: string;
    successUrl: string;
    cancelUrl: string;
  },
): Promise<{ id: string; url: string | null }> {
  const params: Record<string, string> = {
    mode: "subscription",
    "line_items[0][price]": args.priceId,
    "line_items[0][quantity]": "1",
    success_url: args.successUrl,
    cancel_url: args.cancelUrl,
    "metadata[workspace_id]": args.workspaceId,
    "subscription_data[metadata][workspace_id]": args.workspaceId,
  };
  if (args.customerId) {
    params.customer = args.customerId;
  } else if (args.customerEmail) {
    params.customer_email = args.customerEmail;
  }
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
