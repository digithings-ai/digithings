import { describe, expect, it } from "vitest";
import nextConfig from "../../../next.config";
import { DIGICHAT_APP_SECURITY_HEADERS } from "../../../src/lib/security-headers-bake";

type HeaderRule = {
  source: string;
  headers: { key: string; value: string }[];
};

async function headerRules(): Promise<HeaderRule[]> {
  const headers = nextConfig.headers;
  if (!headers) return [];
  return (await headers()) as HeaderRule[];
}

/**
 * Next prefixes every custom-route source with the basePath at build time
 * (next/dist/lib/load-custom-routes.js:350): the source "/" becomes the base
 * path itself, every other source gets the base path in front of it.
 */
function effectiveSource(source: string, basePath?: string): string {
  if (!basePath) return source;
  return source === "/" ? basePath : `${basePath}${source}`;
}

/**
 * DIG-5121: the app is served under a base path (/chat) on digithings.ai.
 * Under that base path the global rule's source becomes
 * "/chat/((?!embed$|embed/).*)" — whose compiled regex does not match the
 * canonical root "/chat" (Next redirects "/chat/" → "/chat") — so the explicit
 * root rule is what keeps CSP, X-Frame-Options and the rest of the app
 * hardening on the public chat URL.
 */
describe("app security headers cover the app root", () => {
  it("serves the app security headers on the root path", async () => {
    const rules = await headerRules();
    const root = rules.find((rule) => rule.source === "/");
    expect(root).toBeDefined();
    expect(root?.headers.some((h) => h.key === "Content-Security-Policy")).toBe(true);
    expect(root?.headers.some((h) => h.key === "X-Frame-Options")).toBe(true);
    // The root carries the FULL app header set, not a subset: the global rule
    // is the reference, and the root rule exists because the global rule does
    // not match the canonical path under a base path.
    expect(root?.headers).toEqual([...DIGICHAT_APP_SECURITY_HEADERS]);
  });

  it("keeps the global rule for every other non-embed path", async () => {
    const rules = await headerRules();
    const global = rules.find((rule) => rule.source === "/((?!embed$|embed/).*)");
    expect(global).toBeDefined();
    expect(global?.headers.some((h) => h.key === "Content-Security-Policy")).toBe(true);
    expect(global?.headers).toEqual([...DIGICHAT_APP_SECURITY_HEADERS]);
  });

  it("keeps the embed arms on the fail-closed baked embed headers", async () => {
    const rules = await headerRules();
    const embedRules = rules.filter((rule) => rule.source.startsWith("/embed"));
    expect(embedRules.length).toBe(2);
    for (const rule of embedRules) {
      expect(rule.headers.some((h) => h.key === "Content-Security-Policy")).toBe(true);
      // The embed arms are meant to be framed (the proxy allows marketing
      // origins at runtime), so they must not carry the app's DENY.
      expect(rule.headers.some((h) => h.key === "X-Frame-Options")).toBe(false);
    }
  });

  it("puts the root rule exactly on the canonical path under a base path", async () => {
    const rules = await headerRules();
    const root = rules.find((rule) => rule.source === "/");
    expect(root).toBeDefined();
    // The app has a single route (the root), so under a base path the
    // canonical path IS the base path — the root rule covers it.
    expect(effectiveSource(root?.source ?? "", "/chat")).toBe("/chat");
    // The global rule needs at least one path segment after the base path, so
    // it never covers the canonical root on its own.
    const global = rules.find((rule) => rule.source === "/((?!embed$|embed/).*)");
    expect(effectiveSource(global?.source ?? "", "/chat")).not.toBe("/chat");
  });
});
