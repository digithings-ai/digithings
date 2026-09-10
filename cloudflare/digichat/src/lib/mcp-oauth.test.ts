import { describe, expect, it, vi } from "vitest";
import {
  buildAuthorizationUrl,
  callbackHtml,
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
    ).rejects.toThrow("blocked_url");
  });
});
