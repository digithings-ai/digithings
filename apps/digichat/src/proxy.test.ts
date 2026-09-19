import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";
import { resetEmbedTenantRegistryForTests } from "./lib/embed-tenants";

describe("proxy embed CSP", () => {
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
});
