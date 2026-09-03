import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DASHBOARD_CSP, DASHBOARD_SECURITY_HEADERS } from "./security-headers.mjs";

// Shipped at the dist root by scripts/build-digiquant.sh — Cloudflare Pages
// ignores _headers files below the output root (#674).
const publicHeaders = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../digiquant-web/public/_headers"),
  "utf8",
);

describe("dashboard security-headers", () => {
  it("denies framing and allows Supabase connect", () => {
    expect(DASHBOARD_CSP).toContain("frame-ancestors 'none'");
    expect(DASHBOARD_CSP).toContain("https://*.supabase.co");
    expect(DASHBOARD_CSP).toContain("wss://*.supabase.co");
  });

  it("allows digichat iframe origins for the Desk+ popup (#3422)", () => {
    expect(DASHBOARD_CSP).toContain("frame-src");
    expect(DASHBOARD_CSP).toContain("https://digithings.ai");
    expect(DASHBOARD_CSP).toContain("http://127.0.0.1:3005");
  });

  it("exports standard hardening headers", () => {
    expect(DASHBOARD_SECURITY_HEADERS.some((h) => h.key === "X-Frame-Options")).toBe(
      true,
    );
  });

  it("keeps the shipped _headers aligned with DASHBOARD_CSP", () => {
    // Full-string containment: any drift between the canonical CSP and the
    // deployed headers file fails here, not just spot-checked directives.
    expect(publicHeaders).toContain(DASHBOARD_CSP);
  });

  it("scopes the CSP to the dashboard so landing-page Google Fonts keep working", () => {
    expect(publicHeaders).toContain("/dashboard*");
    const landingBlock = publicHeaders.split("/dashboard*")[0];
    expect(landingBlock).not.toContain("Content-Security-Policy");
  });

  it("does not keep a CSP path for retired /olympus*", () => {
    expect(publicHeaders).not.toContain("/olympus*");
  });
});
