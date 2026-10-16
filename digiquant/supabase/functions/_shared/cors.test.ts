/**
 * Deno tests for browser CORS helpers (Settings / billing Edge Functions).
 *
 *   deno test --allow-env _shared/cors.test.ts
 */

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { CORS_HEADERS, corsPreflight, withCors } from "./cors.ts";

Deno.test("corsPreflight returns 204 with Allow-* headers", () => {
  const res = corsPreflight();
  assertEquals(res.status, 204);
  assertEquals(res.headers.get("Access-Control-Allow-Origin"), "*");
  assertEquals(
    res.headers.get("Access-Control-Allow-Methods"),
    CORS_HEADERS["Access-Control-Allow-Methods"],
  );
  assertEquals(
    res.headers.get("Access-Control-Allow-Headers"),
    CORS_HEADERS["Access-Control-Allow-Headers"],
  );
});

Deno.test("withCors preserves status/body and adds CORS", async () => {
  const inner = new Response(JSON.stringify({ code: "TIER_FORBIDDEN" }), {
    status: 403,
    headers: { "Content-Type": "application/json", "X-Test": "1" },
  });
  const res = withCors(inner);
  assertEquals(res.status, 403);
  assertEquals(res.headers.get("Content-Type"), "application/json");
  assertEquals(res.headers.get("X-Test"), "1");
  assertEquals(res.headers.get("Access-Control-Allow-Origin"), "*");
  const body = await res.json();
  assertEquals(body.code, "TIER_FORBIDDEN");
});
