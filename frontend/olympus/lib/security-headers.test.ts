import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OLYMPUS_CSP, OLYMPUS_SECURITY_HEADERS } from "./security-headers.mjs";

const publicHeaders = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../public/_headers"),
  "utf8",
);

describe("olympus security-headers", () => {
  it("denies framing and allows Supabase connect", () => {
    expect(OLYMPUS_CSP).toContain("frame-ancestors 'none'");
    expect(OLYMPUS_CSP).toContain("https://*.supabase.co");
  });

  it("exports standard hardening headers", () => {
    expect(OLYMPUS_SECURITY_HEADERS.some((h) => h.key === "X-Frame-Options")).toBe(
      true,
    );
  });

  it("keeps public/_headers aligned with OLYMPUS_CSP", () => {
    expect(publicHeaders).toContain("frame-ancestors 'none'");
    expect(publicHeaders).toContain("https://*.supabase.co");
  });
});
