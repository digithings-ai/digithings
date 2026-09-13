import { describe, expect, it, vi } from "vitest";
import {
  buildAuthorizationUrl,
  callbackHtml,
  exchangeAuthorizationCode,
  parseResourceMetadataUrl,
  pkceChallenge,
  pkceVerifier,
  signOAuthState,
  ssrfFetch,
  verifyOAuthState,
} from "./mcp-oauth";

describe("mcp oauth helpers", () => {
  it("parses WWW-Authenticate resource_metadata", () => {
    const rfcParam = ["resource", "metadata"].join("_");
    const altParam = ["as", "uri"].join("_");
    expect(
      parseResourceMetadataUrl(
        `Bearer ${rfcParam}="https://mcp.linear.app/.well-known/oauth-protected-resource"`,
      ),
    ).toBe("https://mcp.linear.app/.well-known/oauth-protected-resource");
    expect(
      parseResourceMetadataUrl(
        `Bearer ${altParam}="https://mcp.linear.app/.well-known/oauth-protected-resource"`,
      ),
    ).toBe("https://mcp.linear.app/.well-known/oauth-protected-resource");
  });

  it("signs and verifies PKCE state", () => {
    const verifier = pkceVerifier();
    expect(pkceChallenge(verifier)).toMatch(/^[A-Za-z0-9_-]+$/);
    const payload = {
      id: "linear",
      verifier,
      tokenEndpoint: "https://auth.example/token",
      clientId: "cid",
      redirectUri: "http://127.0.0.1:3000/api/mcp/oauth/callback",
      nonce: "abc",
      iat: Date.now(),
    };
    const raw = signOAuthState(payload, "secret");
    expect(verifyOAuthState(raw, "secret")?.id).toBe("linear");
    expect(verifyOAuthState(raw, "other")).toBeNull();
  });

  it("callback HTML postMessages without logging extras", () => {
    const html = callbackHtml({
      origin: "http://127.0.0.1:3000",
      id: "linear",
      accessToken: "tok",
    });
    expect(html).toContain("digichat-mcp-oauth");
    expect(html).toContain("tok");
    expect(html).toContain("window.opener.postMessage");
  });

  it("buildAuthorizationUrl uses PKCE S256", () => {
    const url = buildAuthorizationUrl({
      authorizationEndpoint: "https://auth.example/authorize",
      clientId: "cid",
      redirectUri: "http://127.0.0.1:3000/api/mcp/oauth/callback",
      challenge: "abc",
      nonce: "n1",
    });
    expect(url).toContain("code_challenge_method=S256");
    expect(url).toContain("state=n1");
  });

  it("ssrfFetch refuses loopback redirects", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response(null, {
        status: 302,
        headers: { location: "http://127.0.0.1/secret" },
      });
    });
    await expect(
      ssrfFetch("https://mcp.example/mcp", {}, fetchImpl as typeof fetch),
    ).rejects.toThrow("cross_origin_redirect");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("ssrfFetch refuses a cross-origin redirect without re-issuing the request", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response(null, {
        status: 302,
        headers: { location: "https://evil.example/token" },
      });
    });
    await expect(
      ssrfFetch(
        "https://auth.example/token",
        { method: "POST", body: "client_secret=leak" },
        fetchImpl as typeof fetch,
      ),
    ).rejects.toThrow("cross_origin_redirect");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("https://auth.example/token");
  });

  it("ssrfFetch preserves a same-origin redirect", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/token")) {
        return new Response(null, { status: 307, headers: { location: "/token-v2" } });
      }
      return new Response(JSON.stringify({ access_token: "same-origin" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const res = await ssrfFetch(
      "https://auth.example/token",
      { method: "POST", body: "client_secret=keep" },
      fetchImpl as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(fetchImpl.mock.calls[1]?.[0]).toBe("https://auth.example/token-v2");
  });

  it("exchangeAuthorizationCode refuses a cross-origin redirect and never sends the secret there", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response(null, {
        status: 302,
        headers: { location: "https://evil.example/token" },
      });
    });
    const state = {
      id: "linear",
      verifier: "verifier",
      tokenEndpoint: "https://auth.example/token",
      clientId: "cid",
      clientSecret: "s3cr3t",
      redirectUri: "http://127.0.0.1:3000/api/mcp/oauth/callback",
      nonce: "n1",
      iat: Date.now(),
    };
    await expect(
      exchangeAuthorizationCode(state, "code-1", fetchImpl as unknown as typeof fetch),
    ).rejects.toThrow("cross_origin_redirect");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const calledUrls = fetchImpl.mock.calls.map((c) => String(c[0]));
    expect(calledUrls).not.toContain("https://evil.example/token");
  });

  it("exchangeAuthorizationCode still succeeds for the normal exchange", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response(JSON.stringify({ access_token: "token-123" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const state = {
      id: "linear",
      verifier: "verifier",
      tokenEndpoint: "https://auth.example/token",
      clientId: "cid",
      clientSecret: "s3cr3t",
      redirectUri: "http://127.0.0.1:3000/api/mcp/oauth/callback",
      nonce: "n1",
      iat: Date.now(),
    };
    await expect(
      exchangeAuthorizationCode(state, "code-1", fetchImpl as unknown as typeof fetch),
    ).resolves.toBe("token-123");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
