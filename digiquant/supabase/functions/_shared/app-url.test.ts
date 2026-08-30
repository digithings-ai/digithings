/**
 * Unit tests for _shared/app-url.ts (no I/O).
 */

import { assertEquals, assertThrows } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  ALPACA_OAUTH_CALLBACK_PATH,
  pinnedAlpacaRedirectUriFromOrigin,
  publicAlpacaOauthClientId,
  publicAppOrigin,
  settingsBillingReturnUrl,
} from "./app-url.ts";

Deno.test("publicAppOrigin strips trailing slash and /olympus", () => {
  assertEquals(publicAppOrigin("https://digiquant.io"), "https://digiquant.io");
  assertEquals(publicAppOrigin("https://digiquant.io/"), "https://digiquant.io");
  assertEquals(publicAppOrigin("https://digiquant.io/olympus"), "https://digiquant.io");
  assertEquals(publicAppOrigin("https://digiquant.io/olympus/"), "https://digiquant.io");
});

Deno.test("Alpaca redirect_uri is origin + /olympus callback", () => {
  assertEquals(
    pinnedAlpacaRedirectUriFromOrigin("https://digiquant.io"),
    "https://digiquant.io/olympus/settings/brokers/callback/",
  );
  assertEquals(
    pinnedAlpacaRedirectUriFromOrigin("https://digiquant.io/olympus"),
    "https://digiquant.io/olympus/settings/brokers/callback/",
  );
  assertEquals(
    ALPACA_OAUTH_CALLBACK_PATH,
    "/olympus/settings/brokers/callback/",
  );
});

Deno.test("billing return URL lands on Settings billing tab", () => {
  assertEquals(
    settingsBillingReturnUrl("https://digiquant.io", "success"),
    "https://digiquant.io/olympus/settings/?tab=billing&checkout=success",
  );
  assertEquals(
    settingsBillingReturnUrl("https://digiquant.io/olympus", "cancel"),
    "https://digiquant.io/olympus/settings/?tab=billing&checkout=cancel",
  );
  assertEquals(
    settingsBillingReturnUrl("https://digiquant.io"),
    "https://digiquant.io/olympus/settings/?tab=billing",
  );
});

Deno.test("empty APP_URL throws", () => {
  assertThrows(() => pinnedAlpacaRedirectUriFromOrigin(""), Error, "APP_URL unset");
  assertThrows(() => settingsBillingReturnUrl("  "), Error, "APP_URL unset");
});

Deno.test("public Alpaca client id trims and never uses the secret", () => {
  assertEquals(publicAlpacaOauthClientId(""), "");
  assertEquals(publicAlpacaOauthClientId("  cid-public  "), "cid-public");
  const previousId = Deno.env.get("ALPACA_OAUTH_CLIENT_ID");
  const previousSecret = Deno.env.get("ALPACA_OAUTH_CLIENT_SECRET");
  Deno.env.set("ALPACA_OAUTH_CLIENT_ID", " from-env ");
  Deno.env.set("ALPACA_OAUTH_CLIENT_SECRET", "must-not-leak");
  try {
    assertEquals(publicAlpacaOauthClientId(), "from-env");
  } finally {
    if (previousId === undefined) Deno.env.delete("ALPACA_OAUTH_CLIENT_ID");
    else Deno.env.set("ALPACA_OAUTH_CLIENT_ID", previousId);
    if (previousSecret === undefined) Deno.env.delete("ALPACA_OAUTH_CLIENT_SECRET");
    else Deno.env.set("ALPACA_OAUTH_CLIENT_SECRET", previousSecret);
  }
});
