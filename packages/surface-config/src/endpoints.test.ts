import { readFileSync } from "node:fs";
import { expect, test } from "bun:test";
import { endpoint } from "./endpoints";

// The dashboard ships its own Content-Security-Policy. A local chat origin the
// policy does not name is not framable, whatever the config resolves to.
const CSP_SOURCE = new URL(
  "../../../apps/dashboard/lib/security-headers.mjs",
  import.meta.url,
);
const FRAME_SRC_BLOCK = /DASHBOARD_DIGICHAT_FRAME_SRC\s*=\s*\[([\s\S]*?)\]/;

test("local chat defaults to the published port :3005", () => {
  expect(endpoint("chat", {})).toBe("http://127.0.0.1:3005");
});

test("DIGI_CHAT_URL wins over aliases and defaults", () => {
  expect(
    endpoint("chat", {
      DIGI_CHAT_URL: "http://127.0.0.1:3005/",
      DIGICHAT_DEVKIT_URL: "http://127.0.0.1:3999",
    }),
  ).toBe("http://127.0.0.1:3005");
});

test("DIGICHAT_DEVKIT_URL is a deprecated chat alias", () => {
  expect(endpoint("chat", { DIGICHAT_DEVKIT_URL: "http://127.0.0.1:3005" })).toBe(
    "http://127.0.0.1:3005",
  );
});

test("DQ_API_URL is desk-only and does not set chat", () => {
  expect(endpoint("chat", { DQ_API_URL: "http://127.0.0.1:8788" })).toBe("http://127.0.0.1:3005");
  expect(endpoint("desk", { DQ_API_URL: "http://127.0.0.1:8788/" })).toBe("http://127.0.0.1:8788");
});

test("cloud chat uses digithings.ai; cloud mcp stays unset", () => {
  expect(endpoint("chat", { DIGI_ENV: "cloud" })).toBe("https://digithings.ai");
  expect(() => endpoint("mcp", { DIGI_ENV: "cloud" })).toThrow(/unset/);
});

test("the local chat profile origin is already allowed by the shipped dashboard CSP", () => {
  // This pins the frame-src half of the policy. connect-src names no loopback
  // origin at all, so local fetches are a separate, pre-existing header gap and
  // are not asserted here.
  const origin = new URL(endpoint("chat", {})).origin;
  const block = readFileSync(CSP_SOURCE, "utf8").match(FRAME_SRC_BLOCK);
  expect(block).not.toBeNull();
  const allowed = [...(block as RegExpMatchArray)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  expect(allowed.length).toBeGreaterThan(0);
  expect(allowed).toContain(origin);
});
