import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";
import { resetEmbedTenantRegistryForTests } from "./lib/embed-tenants";

describe("proxy per-mode security headers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetEmbedTenantRegistryForTests();
  });

  it("sets frame-ancestors from runtime DIGICHAT_EMBED_HOSTS", async () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "client.example.com");
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const req = new NextRequest("http://127.0.0.1:3000/embed?host=client.example.com");
    const res = proxy(req);
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain("https://client.example.com");
    expect(csp).not.toContain("frame-ancestors *");
    expect(csp).not.toBe("frame-ancestors 'none';");
  });

  it("does not open * when hosts unset", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const req = new NextRequest("http://127.0.0.1:3000/embed");
    const res = proxy(req);
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).not.toContain("frame-ancestors *");
    expect(csp).toContain("https://digithings.ai");
  });

  it("opens tenant framing + no-store for /?mode=embed and strips baked DENY", async () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "client.example.com");
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const req = new NextRequest(
      "http://127.0.0.1:3000/?mode=embed&host=client.example.com",
    );
    const res = proxy(req);
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain("https://client.example.com");
    expect(csp).not.toContain("frame-ancestors *");
    // Baked X-Frame-Options: DENY would win over the CSP allowlist in
    // browsers, so the proxy must strip it on the embed-mode route.
    expect(res.headers.get("X-Frame-Options")).toBeNull();
    // Per-tenant HTML must never cache.
    expect(res.headers.get("Cache-Control")).toBe("no-store");
  });

  it("leaves / (menu) and product/catalog modes to the baked app headers", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    for (const url of [
      "http://127.0.0.1:3000/",
      "http://127.0.0.1:3000/?mode=product",
      "http://127.0.0.1:3000/?mode=catalog",
    ]) {
      const res = proxy(new NextRequest(url));
      expect(res.headers.get("Content-Security-Policy")).toBeNull();
      expect(res.headers.get("X-Frame-Options")).toBeNull();
      expect(res.headers.get("Cache-Control")).toBeNull();
    }
  });

  it("strips ?token= from /embed into an x-embed-token request header (DIG-3523)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const res = proxy(
      new NextRequest(
        "http://127.0.0.1:3000/embed?token=SECRET&host=client.example.com",
      ),
    );
    // Internal rewrite target carries every param except the secret.
    const target = res.headers.get("x-middleware-rewrite") ?? "";
    expect(target).toContain("host=client.example.com");
    expect(target).not.toContain("token=");
    expect(target).not.toContain("SECRET");
    // The secret travels to the render as a request header instead.
    expect(res.headers.get("x-middleware-request-x-embed-token")).toBe(
      "SECRET",
    );
    // Embed framing + no-store still applied on the rewrite response.
    expect(res.headers.get("Content-Security-Policy")).toContain(
      "frame-ancestors",
    );
    expect(res.headers.get("Cache-Control")).toBe("no-store");
  });

  it("strips ?token= on /?mode=embed and keeps the mode param (DIG-3523)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const res = proxy(
      new NextRequest("http://127.0.0.1:3000/?mode=embed&token=SECRET"),
    );
    const target = res.headers.get("x-middleware-rewrite") ?? "";
    expect(target).toContain("mode=embed");
    expect(target).not.toContain("SECRET");
    expect(res.headers.get("x-middleware-request-x-embed-token")).toBe(
      "SECRET",
    );
  });

  it("leaves tokenless embed requests as plain next() with framing intact", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const res = proxy(
      new NextRequest("http://127.0.0.1:3000/embed?host=client.example.com"),
    );
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
    expect(res.headers.get("x-middleware-request-x-embed-token")).toBeNull();
    expect(res.headers.get("Content-Security-Policy")).toContain(
      "frame-ancestors",
    );
    expect(res.headers.get("Cache-Control")).toBe("no-store");
  });
});
