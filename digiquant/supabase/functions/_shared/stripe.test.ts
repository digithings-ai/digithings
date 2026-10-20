/**
 * Deno tests for the Stripe API base and the real HTTP path of the billing
 * helpers (create-checkout-session, customer-portal).
 *
 * The point of these is that the local self-host stack can drive billing against
 * a stub with no live key and no spend, so the base URL has to be genuinely
 * overridable and the override has to be genuinely wired into the fetch — not
 * just readable from a helper nobody calls. Every network test therefore runs
 * against a loopback stub and asserts the request the stub actually received.
 *
 *   deno task test
 */

import {
  assert,
  assertEquals,
  assertRejects,
  assertStringIncludes,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  createBillingPortalSession,
  createCheckoutSession,
  DEFAULT_STRIPE_API_BASE,
  StripeHttpError,
  stripeApiBase,
} from "./stripe.ts";

interface StubCall {
  method: string;
  path: string;
  auth: string | null;
  contentType: string | null;
  body: string;
}

interface Stub {
  base: string;
  calls: StubCall[];
  close: () => Promise<void>;
}

async function startStub(
  respond: (call: StubCall) => Response,
): Promise<Stub> {
  const calls: StubCall[] = [];
  const ac = new AbortController();
  let announce!: (port: number) => void;
  const listening = new Promise<number>((resolve) => {
    announce = resolve;
  });
  const server = Deno.serve(
    {
      hostname: "127.0.0.1",
      port: 0,
      signal: ac.signal,
      onListen: ({ port }) => announce(port),
    },
    async (req) => {
      const call: StubCall = {
        method: req.method,
        path: new URL(req.url).pathname,
        auth: req.headers.get("Authorization"),
        contentType: req.headers.get("Content-Type"),
        body: await req.text(),
      };
      calls.push(call);
      return respond(call);
    },
  );
  const port = await listening;
  return {
    base: `http://127.0.0.1:${port}`,
    calls,
    close: async () => {
      ac.abort();
      try {
        await server.finished;
      } catch {
        // aborted on purpose
      }
    },
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const noEnv = () => undefined;

Deno.test("stripeApiBase defaults to the production Stripe host", () => {
  assertEquals(stripeApiBase(noEnv), "https://api.stripe.com/v1");
  assertEquals(stripeApiBase(noEnv), DEFAULT_STRIPE_API_BASE);
  assertEquals(stripeApiBase(() => ""), DEFAULT_STRIPE_API_BASE);
  assertEquals(stripeApiBase(() => "   "), DEFAULT_STRIPE_API_BASE);
});

Deno.test("stripeApiBase honours an override and drops trailing slashes", () => {
  assertEquals(
    stripeApiBase((k) => (k === "STRIPE_API_BASE" ? "http://127.0.0.1:9999" : undefined)),
    "http://127.0.0.1:9999",
  );
  assertEquals(
    stripeApiBase(() => "http://127.0.0.1:9999///"),
    "http://127.0.0.1:9999",
  );
});

Deno.test("createCheckoutSession posts the form to the stub, not to Stripe", async () => {
  const stub = await startStub(() =>
    json({ id: "cs_test_123", url: "http://127.0.0.1/checkout/cs_test_123" })
  );
  try {
    const session = await createCheckoutSession("sk_test_local", {
      priceId: "price_desk_monthly",
      workspaceId: "ws_1",
      successUrl: "http://digithings.localhost/success",
      cancelUrl: "http://digithings.localhost/cancel",
    }, stub.base);

    assertEquals(session.id, "cs_test_123");
    assertEquals(session.url, "http://127.0.0.1/checkout/cs_test_123");

    // Non-vacuity: the stub was reached. Without this the assertions below would
    // pass just as well if the helper never made a request at all.
    assertEquals(stub.calls.length, 1);
    const call = stub.calls[0];
    assertEquals(call.method, "POST");
    assertEquals(call.path, "/checkout/sessions");
    assertEquals(call.auth, "Bearer sk_test_local");
    assertStringIncludes(call.contentType ?? "", "application/x-www-form-urlencoded");

    const form = new URLSearchParams(call.body);
    assertEquals(form.get("mode"), "subscription");
    assertEquals(form.get("line_items[0][price]"), "price_desk_monthly");
    assertEquals(form.get("metadata[workspace_id]"), "ws_1");
    assertEquals(form.get("success_url"), "http://digithings.localhost/success");
    assertEquals(form.get("cancel_url"), "http://digithings.localhost/cancel");
    // No customer was supplied, so neither customer field may be invented.
    assertEquals(form.get("customer"), null);
    assertEquals(form.get("customer_email"), null);
  } finally {
    await stub.close();
  }
});

Deno.test("createBillingPortalSession posts to the stub's portal path", async () => {
  const stub = await startStub(() => json({ url: "http://127.0.0.1/portal" }));
  try {
    const portal = await createBillingPortalSession("sk_test_local", {
      customerId: "cus_test_1",
      returnUrl: "http://digithings.localhost/account",
    }, stub.base);

    assertEquals(portal.url, "http://127.0.0.1/portal");
    assertEquals(stub.calls.length, 1);
    assertEquals(stub.calls[0].path, "/billing_portal/sessions");
    const form = new URLSearchParams(stub.calls[0].body);
    assertEquals(form.get("customer"), "cus_test_1");
    assertEquals(form.get("return_url"), "http://digithings.localhost/account");
  } finally {
    await stub.close();
  }
});

Deno.test("the STRIPE_API_BASE env var reaches the fetch, so the local stack needs no code change", async () => {
  const stub = await startStub(() => json({ id: "cs_env", url: null }));
  const previous = Deno.env.get("STRIPE_API_BASE");
  try {
    Deno.env.set("STRIPE_API_BASE", `${stub.base}/`);
    assertEquals(stripeApiBase(), stub.base);

    const session = await createCheckoutSession("sk_test_env", {
      priceId: "price_studio_monthly",
      workspaceId: "ws_2",
      successUrl: "http://digithings.localhost/s",
      cancelUrl: "http://digithings.localhost/c",
    });

    assertEquals(session.id, "cs_env");
    assertEquals(session.url, null);
    assertEquals(stub.calls.length, 1);
    assertEquals(stub.calls[0].path, "/checkout/sessions");
    // Explicit argument wins over the environment, so a caller can pin a base
    // for one call without mutating process-wide state.
    assertEquals(
      await createCheckoutSession("sk_test_env", {
        priceId: "price_studio_monthly",
        workspaceId: "ws_2",
        successUrl: "http://digithings.localhost/s",
        cancelUrl: "http://digithings.localhost/c",
      }, `${stub.base}/explicit`).then(() => stub.calls.length),
      2,
    );
    assertEquals(stub.calls.length, 2);
  } finally {
    if (previous === undefined) Deno.env.delete("STRIPE_API_BASE");
    else Deno.env.set("STRIPE_API_BASE", previous);
    await stub.close();
  }
});

Deno.test("an upstream error becomes STRIPE_UPSTREAM and never echoes the body", async () => {
  const stub = await startStub(() =>
    json({ error: { message: "customer cus_9 in account acct_9" } }, 402)
  );
  try {
    const err = await assertRejects(
      () =>
        createCheckoutSession("sk_test_local", {
          priceId: "price_brief_monthly",
          workspaceId: "ws_3",
          successUrl: "http://digithings.localhost/s",
          cancelUrl: "http://digithings.localhost/c",
        }, stub.base),
      StripeHttpError,
    ) as StripeHttpError;

    assertEquals(err.status, 502);
    assertEquals(err.code, "STRIPE_UPSTREAM");
    assert(!err.message.includes("cus_9"), `message leaked upstream body: ${err.message}`);
    assertEquals(stub.calls.length, 1);
  } finally {
    await stub.close();
  }
});
