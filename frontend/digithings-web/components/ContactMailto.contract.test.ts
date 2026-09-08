/**
 * Contact-link page contracts (digithings-web side). The implementation
 * lives in @digithings/web (components/contact) with its own contract
 * tests; this file guards the call sites: every page contact link goes
 * through the shared ContactMailto (never a raw mailto: anchor, #2220),
 * and every showAddress usage carries non-empty fallback children.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

describe("ContactMailto call sites", () => {
  it("keeps every page contact link on the shared ContactMailto instead of a raw mailto: anchor", () => {
    const pages = [
      "../app/page.tsx",
      "../app/team/page.tsx",
      "../app/services/page.tsx",
      "../app/legal/privacy/page.tsx",
    ];
    for (const rel of pages) {
      const path = fileURLToPath(new URL(rel, import.meta.url));
      const src = readFileSync(path, "utf8");
      expect(src).not.toContain("mailto:");
      expect(src).toContain("<ContactMailto");
      expect(src).toContain('from "@digithings/web"');
    }
  });

  it("gives every showAddress call site non-empty fallback text, not a self-closing tag", () => {
    const pages = [
      "../app/page.tsx",
      "../app/services/page.tsx",
      "../app/legal/privacy/page.tsx",
    ];
    for (const rel of pages) {
      const path = fileURLToPath(new URL(rel, import.meta.url));
      const src = readFileSync(path, "utf8");
      const showAddressUsages = src.match(/<ContactMailto\b[^>]*showAddress[^>]*\/?>/gs) ?? [];
      expect(showAddressUsages.length).toBeGreaterThan(0);
      for (const usage of showAddressUsages) {
        expect(usage.trimEnd().endsWith("/>")).toBe(false);
      }
    }
  });
});
