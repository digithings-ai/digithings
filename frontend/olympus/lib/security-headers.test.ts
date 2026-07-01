import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OLYMPUS_CSP, OLYMPUS_SECURITY_HEADERS } from "./security-headers.mjs";

// Shipped at the dist root by scripts/build-digiquant.sh — Cloudflare Pages
// ignores _headers files below the output root (#674).
const publicHeaders = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../digiquant-web/public/_headers"),
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

  it("keeps the shipped _headers aligned with OLYMPUS_CSP", () => {
    // Full-string containment: any drift between the canonical CSP and the
    // deployed headers file fails here, not just spot-checked directives.
    expect(publicHeaders).toContain(OLYMPUS_CSP);
  });

  it("scopes the CSP to the dashboard so landing-page Google Fonts keep working", () => {
    expect(publicHeaders).toContain("/olympus*");
    const landingBlock = publicHeaders.split("/olympus*")[0];
    expect(landingBlock).not.toContain("Content-Security-Policy");
  });
});
