import { describe, expect, it } from "vitest";
import { parseStripeEvent, StripeHttpError, verifyStripeSignature } from "./stripe";
import { loadPriceTierEnv, mapStripeStatus, pickPriceId, priceEnvKey } from "./tiers";
import { settingsBillingReturnUrl } from "./app-url";

// The Stripe port's load-bearing behaviour: a real HMAC must verify, a
// tampered body or an out-of-tolerance timestamp must not. A guard that only
// checked "verification returned something" would pass on a broken port.

const SECRET = "whsec_test";
const TOLERANCE = 300;
const NOW = 1_760_000_000;

async function hmacHex(secret: string, payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * A header with no `t=` and no `v1=`, i.e. the malformed arm. Deliberately not
 * `t=1,v1=x`: that is a well-formed header that only fails on tolerance, so
 * using it here would pin the wrong arm.
 */
const MALFORMED_HEADER = "no-equals-signs-here";


async function sign(t: number, body: string, secret = SECRET): Promise<string> {
  return `t=${t},v1=${await hmacHex(secret, `${t}.${body}`)}`;
}

describe("verifyStripeSignature", () => {
  it("accepts a signature produced with the real HMAC", async () => {
    const body = JSON.stringify({ id: "evt_1", type: "x", created: 1 });
    await expect(
      verifyStripeSignature(body, await sign(NOW, body), SECRET, TOLERANCE, NOW),
    ).resolves.toBeUndefined();
  });

  it("rejects a body mutated after signing", async () => {
    const body = JSON.stringify({ id: "evt_1", type: "x", created: 1 });
    const signature = await sign(NOW, body);
    const tampered = JSON.stringify({ id: "evt_2", type: "x", created: 1 });
    await expect(
      verifyStripeSignature(tampered, signature, SECRET, TOLERANCE, NOW),
    ).rejects.toMatchObject({ status: 400, code: "INVALID_SIGNATURE" });
  });

  it("rejects a signature made with the wrong secret", async () => {
    const body = "{}";
    const signature = await sign(NOW, body, "whsec_other");
    await expect(
      verifyStripeSignature(body, signature, SECRET, TOLERANCE, NOW),
    ).rejects.toBeInstanceOf(StripeHttpError);
  });

  it("rejects a timestamp outside the tolerance window", async () => {
    const body = "{}";
    const stale = NOW - (TOLERANCE + 1);
    const signature = await sign(stale, body);
    await expect(
      verifyStripeSignature(body, signature, SECRET, TOLERANCE, NOW),
    ).rejects.toMatchObject({
      status: 400,
      message: "Signature timestamp outside tolerance",
    });
  });

  it("accepts a signature exactly at the tolerance boundary", async () => {
    // The edge function used `>` not `>=`; this pins that boundary so the port
    // cannot silently narrow the window Stripe allows.
    const body = "{}";
    const edge = NOW - TOLERANCE;
    await expect(
      verifyStripeSignature(body, await sign(edge, body), SECRET, TOLERANCE, NOW),
    ).resolves.toBeUndefined();
  });

  it("rejects a missing header with the edge function's exact message", async () => {
    await expect(
      verifyStripeSignature("{}", null, SECRET, TOLERANCE, NOW),
    ).rejects.toMatchObject({ status: 400, message: "Missing Stripe-Signature header" });
  });

  it("rejects a malformed header with the edge function's exact message", async () => {
    await expect(
      verifyStripeSignature("{}", MALFORMED_HEADER, SECRET, TOLERANCE, NOW),
    ).rejects.toMatchObject({ status: 400, message: "Malformed Stripe-Signature header" });
  });

  it("accepts one valid v1 among several candidates", async () => {
    const body = "{}";
    const good = await hmacHex(SECRET, `${NOW}.${body}`);
    const signature = `t=${NOW},v1=0000000000000000000000000000000000000000000000000000000000000000,v1=${good}`;
    await expect(
      verifyStripeSignature(body, signature, SECRET, TOLERANCE, NOW),
    ).resolves.toBeUndefined();
  });
});

describe("parseStripeEvent", () => {
  it("rejects invalid JSON with the edge function's exact message", () => {
    expect(() => parseStripeEvent("not json")).toThrowError(
      expect.objectContaining({ status: 400, message: "Body is not valid JSON" }),
    );
  });

  it("rejects a well-formed object that is not a Stripe event", () => {
    expect(() => parseStripeEvent('{"hello":"world"}')).toThrowError(
      expect.objectContaining({ status: 400, message: "Not a Stripe event" }),
    );
  });

  it("accepts a minimal valid event", () => {
    const event = parseStripeEvent('{"id":"evt_1","type":"t","created":5,"data":{"object":{}}}');
    expect(event.id).toBe("evt_1");
    expect(event.created).toBe(5);
  });
});

describe("tier and price mapping", () => {
  const env = {
    STRIPE_PRICE_BRIEF_MONTHLY: "p_brief_m",
    STRIPE_PRICE_DESK_ANNUAL: "p_desk_a",
  };

  it("maps Stripe statuses the way the edge function did", () => {
    expect(mapStripeStatus("active")).toBe("active");
    expect(mapStripeStatus("trialing")).toBe("active");
    expect(mapStripeStatus("past_due")).toBe("past_due");
    expect(mapStripeStatus("unpaid")).toBe("past_due");
    expect(mapStripeStatus("canceled")).toBe("canceled");
    expect(mapStripeStatus("incomplete")).toBe("none");
  });

  it("reads the six price env vars and defaults the rest to empty", () => {
    const prices = loadPriceTierEnv(env);
    expect(prices.briefMonthly).toBe("p_brief_m");
    expect(prices.deskAnnual).toBe("p_desk_a");
    expect(prices.studioMonthly).toBe("");
  });

  it("picks the price for the requested tier and interval", () => {
    const prices = loadPriceTierEnv(env);
    expect(pickPriceId("brief", "monthly", prices)).toBe("p_brief_m");
    expect(pickPriceId("desk", "annual", prices)).toBe("p_desk_a");
    // An unset price must be falsy so the route raises PRICE_NOT_CONFIGURED
    // rather than sending Stripe an empty price id.
    expect(pickPriceId("studio", "annual", prices)).toBe("");
  });

  it("builds the env var name that appears in the PRICE_NOT_CONFIGURED message", () => {
    expect(priceEnvKey("desk", "annual")).toBe("STRIPE_PRICE_DESK_ANNUAL");
    expect(priceEnvKey("brief", "monthly")).toBe("STRIPE_PRICE_BRIEF_MONTHLY");
  });

  it("never matches an empty price id against an unset env var", () => {
    const prices = loadPriceTierEnv(env);
    expect(pickPriceId("studio", "monthly", prices)).toBe("");
  });
});

describe("settingsBillingReturnUrl", () => {
  it("always carries tab=billing and adds checkout only when asked", () => {
    expect(settingsBillingReturnUrl("https://digithings.ai")).toBe(
      "https://digithings.ai/dashboard/settings/?tab=billing",
    );
    expect(settingsBillingReturnUrl("https://digithings.ai", "success")).toBe(
      "https://digithings.ai/dashboard/settings/?tab=billing&checkout=success",
    );
  });

  it("strips a trailing slash and a known base suffix", () => {
    expect(settingsBillingReturnUrl("https://digithings.ai/dashboard/")).toBe(
      "https://digithings.ai/dashboard/settings/?tab=billing",
    );
  });

  it("throws when the app URL is unset, as the edge helper did", () => {
    expect(() => settingsBillingReturnUrl("")).toThrowError("APP_URL unset");
  });
});