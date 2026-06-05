import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { isEmbedAllowed, isEmbedReferer, resolveChatTenantContext } from "./chat-route-context";

describe("isEmbedReferer", () => {
  it("returns true when referer path includes /embed", () => {
    const req = new Request("http://localhost/api/chat", {
      headers: { referer: "https://digithings.ai/embed?accent=digithings" },
    });
    expect(isEmbedReferer(req)).toBe(true);
  });

  it("returns false for non-embed referers", () => {
    const req = new Request("http://localhost/api/chat", {
      headers: { referer: "https://digithings.ai/" },
    });
    expect(isEmbedReferer(req)).toBe(false);
  });
});

describe("isEmbedAllowed", () => {
  const env = process.env;

  beforeEach(() => {
    process.env = { ...env };
    delete process.env.DIGICHAT_EMBED_ENABLED;
    delete process.env.DIGICHAT_EMBED_TOKEN;
  });

  afterEach(() => {
    process.env = env;
  });

  it("allows when DIGICHAT_EMBED_ENABLED=1", () => {
    process.env.DIGICHAT_EMBED_ENABLED = "1";
    const req = new Request("http://localhost/api/chat");
    expect(isEmbedAllowed(req)).toBe(true);
  });

  it("allows when X-Embed-Token matches DIGICHAT_EMBED_TOKEN", () => {
    process.env.DIGICHAT_EMBED_TOKEN = "secret-token";
    const req = new Request("http://localhost/api/chat", {
      headers: { "x-embed-token": "secret-token" },
    });
    expect(isEmbedAllowed(req)).toBe(true);
  });

  it("rejects when token is missing or wrong", () => {
    process.env.DIGICHAT_EMBED_TOKEN = "secret-token";
    const req = new Request("http://localhost/api/chat");
    expect(isEmbedAllowed(req)).toBe(false);
  });
});

describe("resolveChatTenantContext", () => {
  const env = process.env;

  beforeEach(() => {
    process.env = { ...env };
    delete process.env.DIGICHAT_EMBED_ENABLED;
    delete process.env.DIGICHAT_EMBED_TOKEN;
  });

  afterEach(() => {
    process.env = env;
  });

  it("returns embed tenant when unauthenticated embed host is allowed", async () => {
    process.env.DIGICHAT_EMBED_ENABLED = "1";
    const auth401 = new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 });
    const req = new Request("http://localhost/api/chat", {
      headers: { "x-embed-host": "https://digithings.ai" },
    });
    const ctx = await resolveChatTenantContext(req, auth401);
    expect(ctx).toEqual({ tenantSlug: "embed", ownerUserSub: "embed:anonymous" });
  });

  it("returns 503 when embed host present but gate closed", async () => {
    const auth401 = new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 });
    const req = new Request("http://localhost/api/chat", {
      headers: { "x-embed-host": "https://digithings.ai" },
    });
    const ctx = await resolveChatTenantContext(req, auth401);
    expect(ctx).toBeInstanceOf(Response);
    expect((ctx as Response).status).toBe(503);
  });

  it("passes through authenticated session context", async () => {
    const req = new Request("http://localhost/api/chat");
    const ctx = await resolveChatTenantContext(req, {
      tenantSlug: "acme",
      ownerUserSub: "user-1",
    });
    expect(ctx).toEqual({ tenantSlug: "acme", ownerUserSub: "user-1" });
  });
});
