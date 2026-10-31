/**
 * The chat's own MCP identity: a digikey JWT minted server-side, scoped to the
 * server it is for, reused until near expiry, and never falling back to a
 * static key.
 *
 * The digikey exchange is stubbed at `fetch`, so these tests assert the wire
 * body (including `requested_scopes`) and the caching behaviour without a
 * digikey and without a fixture credential.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mcpUpstreamHeaderValue, type McpUpstreamServer } from "@/lib/deploy-config/mcp-servers";
import { INVITE_ONLY_EMBED_HOSTS } from "@/lib/embed-invite-only";
import {
  MCP_EDGE_SCOPES,
  MCP_EDGE_TOKEN_EXPIRY_SKEW_MS,
  _resetMcpEdgeTokenCacheForTests,
  mcpEdgeScopeFor,
  mcpEdgeScopeForTenant,
  mintMcpEdgeToken,
  readMcpEdgeIdentityFromEnv,
  withMcpEdgeIdentity,
  type McpEdgeIdentity,
} from "@/lib/mcp-edge-token";

function b64url(json: object): string {
  return btoa(JSON.stringify(json)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** A JWT-shaped string with a readable `exp`. Never a real token. */
function fakeJwt(expSeconds: number, marker = "tok"): string {
  return `${b64url({ alg: "RS256", kid: "k1" })}.${b64url({ exp: expSeconds, sub: marker })}.sig`;
}

const NOW_SEC = () => Math.floor(Date.now() / 1000);

function stubDigikey(opts: { token?: string; status?: number; reason?: string }) {
  const fetchStub = vi.fn(async () => {
    if (opts.status && opts.status >= 400) {
      return new Response(JSON.stringify({ detail: opts.reason ?? "nope" }), {
        status: opts.status,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({
        access_token: opts.token ?? fakeJwt(NOW_SEC() + 900),
        token_type: "Bearer",
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

const BFF_IDENTITY: McpEdgeIdentity = {
  digikeyUrl: "http://digikey.test",
  bffToken: "bff-secret",
  tenantSlug: "digithings-ai",
  subject: "bff:visitor-1",
};

const API_KEY_ONLY_IDENTITY: McpEdgeIdentity = {
  digikeyUrl: "http://digikey.test",
  apiKey: "dgk_live_identity",
  tenantSlug: "digithings-ai",
  subject: "bff:visitor-1",
};

function jwtRows(): McpUpstreamServer[] {
  return [
    {
      id: "digisearch",
      url: "https://graph.digithings.ai/_stack/mcp/digisearch/mcp",
      authScheme: "jwt",
    },
    {
      id: "digivault",
      url: "https://graph.digithings.ai/_stack/mcp/digivault/mcp",
      authScheme: "jwt",
    },
  ];
}

beforeEach(() => {
  _resetMcpEdgeTokenCacheForTests();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  _resetMcpEdgeTokenCacheForTests();
  delete process.env.DIGIKEY_URL;
  delete process.env.DIGIKEY_BFF_TOKEN;
  delete process.env.DIGICHAT_MCP_IDENTITY_KEY;
});

describe("scope mapping", () => {
  it("maps each server id to its own mcp:<id> scope", () => {
    expect(mcpEdgeScopeFor("digisearch")).toBe("mcp:digisearch");
    expect(mcpEdgeScopeFor("digivault")).toBe("mcp:digivault");
    expect(mcpEdgeScopeFor("unknown")).toBe("");
    expect(Object.values(MCP_EDGE_SCOPES).sort()).toEqual(["mcp:digisearch", "mcp:digivault"]);
  });
});

describe("withMcpEdgeIdentity", () => {
  it("mints one token for both servers and puts it on every jwt row", async () => {
    const token = fakeJwt(NOW_SEC() + 900);
    const fetchStub = stubDigikey({ token });

    const rows = await withMcpEdgeIdentity(jwtRows(), { identity: BFF_IDENTITY });

    expect(fetchStub).toHaveBeenCalledTimes(1);
    expect(rows.map((r) => r.token)).toEqual([token, token]);
    // Both scopes requested at once: one exchange, not one per server.
    const body = JSON.parse(String(fetchStub.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(body.requested_scopes).toEqual(["mcp:digisearch", "mcp:digivault"]);
    expect(body.grant_type).toBe("bff_session");
  });

  it("leaves static rows exactly as they were", async () => {
    stubDigikey({ token: fakeJwt(NOW_SEC() + 900) });
    const rows: McpUpstreamServer[] = [
      { id: "digisearch", url: "http://digisearch-mcp:8765/mcp", authScheme: "jwt" },
      {
        id: "desk",
        url: "http://desk-mcp:8770/mcp",
        token: "Token abc",
        authHeader: "Authorization",
      },
    ];
    const out = await withMcpEdgeIdentity(rows, { identity: BFF_IDENTITY });
    expect(out[1]).toEqual({
      id: "desk",
      url: "http://desk-mcp:8770/mcp",
      token: "Token abc",
      authHeader: "Authorization",
    });
  });

  it("does nothing (and mints nothing) when no row asks for a JWT", async () => {
    const fetchStub = stubDigikey({});
    const out = await withMcpEdgeIdentity(
      [{ id: "digisearch", url: "http://digisearch-mcp:8765/mcp", token: "static" }],
      { identity: BFF_IDENTITY },
    );
    expect(fetchStub).not.toHaveBeenCalled();
    expect(out[0]?.token).toBe("static");
  });

  it("puts the token where the MCP client sends Authorization: Bearer", async () => {
    const token = fakeJwt(NOW_SEC() + 900);
    stubDigikey({ token });
    const rows = await withMcpEdgeIdentity(jwtRows(), { identity: BFF_IDENTITY });
    const header = mcpUpstreamHeaderValue(rows);
    expect(header).toBeDefined();
    const wireRows = JSON.parse(header ?? "[]") as Record<string, string>[];
    expect(wireRows).toHaveLength(2);
    for (const row of wireRows) {
      // Rows marked jwt carry the token and no authHeader, so digigraph's own
      // rule applies (digigraph/orchestration/mcp_client.py, mcp_http_headers):
      // no authHeader -> `Authorization: Bearer <token>`.
      expect(row.token).toBe(token);
      expect(row.authHeader).toBeUndefined();
      // The scheme is a chat-side concept; digigraph never sees it.
      expect(row.authScheme).toBeUndefined();
      const headers = row.authHeader
        ? { [row.authHeader]: row.token }
        : { Authorization: `Bearer ${row.token}` };
      expect(headers.Authorization).toBe(`Bearer ${token}`);
    }
  });

  it("fails closed when minting fails: no token, no static fallback", async () => {
    stubDigikey({ status: 401 });
    const rows = await withMcpEdgeIdentity(
      [
        {
          id: "digisearch",
          url: "https://graph.digithings.ai/_stack/mcp/digisearch/mcp",
          authScheme: "jwt",
          token: "the-static-key",
          authHeader: "x-digi-mcp-key",
        },
      ],
      { identity: BFF_IDENTITY },
    );
    expect(rows[0]?.token).toBeUndefined();
    expect(rows[0]?.authHeader).toBeUndefined();
  });

  it("fails closed when no identity is configured", async () => {
    const fetchStub = stubDigikey({});
    const rows = await withMcpEdgeIdentity(jwtRows(), { identity: null });
    expect(fetchStub).not.toHaveBeenCalled();
    expect(rows.every((r) => r.token === undefined)).toBe(true);
  });

  it("fails closed for a server whose id has no known scope", async () => {
    const fetchStub = stubDigikey({});
    const rows = await withMcpEdgeIdentity(
      [{ id: "atlassian", url: "https://mcp.atlassian.com/v1/sse", authScheme: "jwt" }],
      { identity: BFF_IDENTITY },
    );
    expect(fetchStub).not.toHaveBeenCalled();
    expect(rows[0]?.token).toBeUndefined();
  });
});

describe("minting and caching", () => {
  it("mints once and reuses the token until near expiry", async () => {
    const token = fakeJwt(NOW_SEC() + 900);
    const fetchStub = stubDigikey({ token });

    const first = await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: ["mcp:digisearch"] });
    const second = await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: ["mcp:digisearch"] });
    expect(first).toEqual({ ok: true, token });
    expect(second).toEqual({ ok: true, token });
    expect(fetchStub).toHaveBeenCalledTimes(1);

    // One second inside the skew window: the token is still valid upstream but
    // is re-minted here, so a request never races its own expiry.
    vi.useFakeTimers();
    vi.setSystemTime((NOW_SEC() + 900) * 1000 - MCP_EDGE_TOKEN_EXPIRY_SKEW_MS + 1_000);
    const third = await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: ["mcp:digisearch"] });
    expect(third.ok).toBe(true);
    expect(fetchStub).toHaveBeenCalledTimes(2);
  });

  it("keys the cache by scope set, so a wider request is its own token", async () => {
    const fetchStub = stubDigikey({ token: fakeJwt(NOW_SEC() + 900) });
    await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: ["mcp:digisearch"] });
    await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: ["mcp:digisearch", "mcp:digivault"] });
    expect(fetchStub).toHaveBeenCalledTimes(2);
  });

  it("refuses a scope outside the mcp:<id> allowlist", async () => {
    const fetchStub = stubDigikey({});
    for (const scope of ["*", "digigraph:chat", "mcp:"] as const) {
      expect(await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: [scope] })).toEqual({
        ok: false,
        reason: "bad_scope",
      });
    }
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("isolates a thrown exchange to the jwt rows instead of the whole header", async () => {
    // Static rows and jwt rows share one upstream header. A network failure in
    // the mint must not propagate, or the route's catch drops the header and a
    // desk-only tenant loses its tools because digikey blinked.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("getaddrinfo ENOTFOUND digikey");
      }),
    );
    const rows = await withMcpEdgeIdentity(
      [
        { id: "digisearch", url: "https://edge/mcp", authScheme: "jwt" },
        { id: "desk", url: "http://desk-mcp:8770/mcp", token: "Token abc" },
      ],
      { identity: API_KEY_ONLY_IDENTITY },
    );
    expect(rows[0]?.token).toBeUndefined();
    expect(rows[1]).toEqual({ id: "desk", url: "http://desk-mcp:8770/mcp", token: "Token abc" });
  });

  it("mints with the turn's tenant over the API-key identity when both are configured", async () => {
    // An API-key token carries the key row's tenant, not the turn's. The
    // services behind the edge scope tenant indexes on that claim, so the BFF
    // session (which names the turn's tenant) must win.
    const token = fakeJwt(NOW_SEC() + 900);
    const fetchStub = stubDigikey({ token });
    const out = await mintMcpEdgeToken({
      identity: { ...BFF_IDENTITY, tenantSlug: "invite-tenant", apiKey: "dgk_live_identity" },
      scopes: ["mcp:digisearch"],
    });
    expect(out).toEqual({ ok: true, token });
    expect(fetchStub).toHaveBeenCalledTimes(1);
    const [, init] = fetchStub.mock.calls[0] ?? [];
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      grant_type: "bff_session",
      tenant_slug: "invite-tenant",
      subject: "bff:visitor-1",
      requested_scopes: ["mcp:digisearch"],
    });
    expect(body.api_key).toBeUndefined();
  });

  it("mints a separate token per tenant, never reusing another tenant's", async () => {
    const fetchStub = stubDigikey({ token: fakeJwt(NOW_SEC() + 900) });
    const identity = { ...BFF_IDENTITY, apiKey: "dgk_live_identity" };
    await mintMcpEdgeToken({ identity, scopes: ["mcp:digisearch"] });
    await mintMcpEdgeToken({
      identity: { ...identity, tenantSlug: "invite-tenant" },
      scopes: ["mcp:digisearch"],
    });
    expect(fetchStub).toHaveBeenCalledTimes(2);
    const tenants = fetchStub.mock.calls.map(
      (c) => (JSON.parse(String(c[1]?.body)) as Record<string, unknown>).tenant_slug,
    );
    expect(tenants).toEqual(["digithings-ai", "invite-tenant"]);
  });

  it("does not fall back to the API key when the BFF exchange is refused", async () => {
    const fetchStub = stubDigikey({ status: 400, reason: "requested_scopes not allowed for bff session" });
    const out = await mintMcpEdgeToken({
      identity: { ...BFF_IDENTITY, apiKey: "dgk_live_identity" },
      scopes: ["mcp:digisearch"],
    });
    expect(out).toEqual({ ok: false, reason: "rejected" });
    for (const call of fetchStub.mock.calls) {
      const body = JSON.parse(String(call[1]?.body)) as Record<string, unknown>;
      expect(body.grant_type).toBe("bff_session");
    }
  });

  it("uses the API-key identity only when there is no BFF credential", async () => {
    const token = fakeJwt(NOW_SEC() + 900);
    const fetchStub = stubDigikey({ token });
    const out = await mintMcpEdgeToken({
      identity: API_KEY_ONLY_IDENTITY,
      scopes: ["mcp:digivault"],
    });
    expect(out).toEqual({ ok: true, token });
    const [url, init] = fetchStub.mock.calls[0] ?? [];
    expect(url).toBe("http://digikey.test/v1/oauth/token");
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      grant_type: "api_key",
      api_key: "dgk_live_identity",
      requested_scopes: ["mcp:digivault"],
    });
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("reports a refusal from digikey as rejected", async () => {
    // 400 is digikey refusing the request — e.g. the credential does not grant
    // the requested mcp: scopes. The retryable `unreachable` classification is
    // the exchange's own behaviour and is covered in digikey-exchange.test.ts.
    stubDigikey({ status: 400, reason: "requested_scopes not allowed for bff session" });
    const out = await mintMcpEdgeToken({ identity: BFF_IDENTITY, scopes: ["mcp:digisearch"] });
    expect(out).toEqual({ ok: false, reason: "rejected" });
  });
});

describe("identity from the environment", () => {
  it("returns null when digikey is not configured", () => {
    expect(readMcpEdgeIdentityFromEnv("acme", "u1")).toBeNull();
    process.env.DIGIKEY_URL = "http://digikey.test";
    expect(readMcpEdgeIdentityFromEnv("acme", "u1")).toBeNull();
  });

  it("uses DIGIKEY_BFF_TOKEN by default and the dedicated key when set", () => {
    process.env.DIGIKEY_URL = "http://digikey.test";
    process.env.DIGIKEY_BFF_TOKEN = "bff-secret";
    expect(readMcpEdgeIdentityFromEnv("acme", "u1")).toEqual({
      digikeyUrl: "http://digikey.test",
      bffToken: "bff-secret",
      tenantSlug: "acme",
      subject: "u1",
    });
    process.env.DIGICHAT_MCP_IDENTITY_KEY = "dgk_live_identity";
    expect(readMcpEdgeIdentityFromEnv("acme", "u1")).toEqual({
      digikeyUrl: "http://digikey.test",
      bffToken: "bff-secret",
      apiKey: "dgk_live_identity",
      tenantSlug: "acme",
      subject: "u1",
    });
  });
});

describe("tenant-private servers (DIG-3585)", () => {
  // The tenant behind an invite link; read from the app's own map so no
  // tenant name is written here.
  const INVITE_TENANT = [...INVITE_ONLY_EMBED_HOSTS.values()][0]!;
  const INVITE_IDENTITY: McpEdgeIdentity = {
    digikeyUrl: "http://digikey.test",
    apiKey: "dgk_live_identity",
    tenantSlug: INVITE_TENANT,
    subject: "bff:visitor-1",
  };
  const privateRow: McpUpstreamServer = {
    id: "helpdesk",
    url: "https://digithings.ai/api/mcp/helpdesk/mcp",
    authScheme: "jwt",
  };

  function scopesOf(call: unknown[] | undefined): unknown {
    const init = call?.[1] as RequestInit | undefined;
    return (JSON.parse(String(init?.body)) as Record<string, unknown>).requested_scopes;
  }

  it("scopes a private row only on an invite-gated tenant's turn", () => {
    expect(INVITE_TENANT).toBeTruthy();
    expect(mcpEdgeScopeForTenant("helpdesk", INVITE_TENANT)).toBe("mcp:helpdesk");
    for (const tenant of ["digithings-ai", "", null, undefined]) {
      expect(mcpEdgeScopeForTenant("helpdesk", tenant)).toBe("");
    }
    // Shared servers keep their scope everywhere.
    expect(mcpEdgeScopeForTenant("digisearch", "digithings-ai")).toBe("mcp:digisearch");
    expect(mcpEdgeScopeForTenant("digivault", INVITE_TENANT)).toBe("mcp:digivault");
  });

  it("never builds a scope outside the mcp:<id> allowlist", () => {
    for (const id of ["*", "a b", "../x", "UPPER:x", "", "x".repeat(65)]) {
      expect(mcpEdgeScopeForTenant(id, INVITE_TENANT)).toBe("");
    }
  });

  it("mints the private scope in its own token, apart from the shared one", async () => {
    let n = 0;
    const fetchStub = vi.fn(async () =>
      Response.json({ access_token: fakeJwt(NOW_SEC() + 900, `t${++n}`), token_type: "Bearer" }),
    );
    vi.stubGlobal("fetch", fetchStub);

    const rows = await withMcpEdgeIdentity([...jwtRows(), privateRow], {
      identity: INVITE_IDENTITY,
    });

    expect(fetchStub).toHaveBeenCalledTimes(2);
    expect(scopesOf(fetchStub.mock.calls[0])).toEqual(["mcp:digisearch", "mcp:digivault"]);
    expect(scopesOf(fetchStub.mock.calls[1])).toEqual(["mcp:helpdesk"]);
    const [search, vault, helpdesk] = rows;
    expect(search?.token).toBeTruthy();
    expect(vault?.token).toBe(search?.token);
    expect(helpdesk?.token).toBeTruthy();
    expect(helpdesk?.token).not.toBe(search?.token);
    expect(helpdesk?.authHeader).toBeUndefined();
  });

  it("asks for nothing private on any other tenant, and the row gets no token", async () => {
    const fetchStub = stubDigikey({});
    const rows = await withMcpEdgeIdentity([...jwtRows(), privateRow], {
      identity: { ...INVITE_IDENTITY, tenantSlug: "digithings-ai" },
    });
    expect(fetchStub).toHaveBeenCalledTimes(1);
    expect(scopesOf(fetchStub.mock.calls[0])).toEqual(["mcp:digisearch", "mcp:digivault"]);
    expect(rows[2]?.token).toBeUndefined();
    expect(rows[2]?.authHeader).toBeUndefined();
  });

  it("drops a static credential on a private row instead of keeping it", async () => {
    stubDigikey({});
    const rows = await withMcpEdgeIdentity(
      [{ ...privateRow, token: "static-edge-value", authHeader: "x-digi-mcp-key" }],
      { identity: { ...INVITE_IDENTITY, tenantSlug: "digithings-ai" } },
    );
    expect(rows[0]?.token).toBeUndefined();
    expect(rows[0]?.authHeader).toBeUndefined();
  });

  it("keeps the shared servers working when digikey refuses the private scope", async () => {
    const fetchStub = vi.fn(async (_url: string, init?: RequestInit) => {
      const scopes = (JSON.parse(String(init?.body)) as { requested_scopes: string[] })
        .requested_scopes;
      if (scopes.includes("mcp:helpdesk")) {
        return Response.json(
          { detail: "requested_scopes not allowed for this key" },
          { status: 400 },
        );
      }
      return Response.json({ access_token: fakeJwt(NOW_SEC() + 900), token_type: "Bearer" });
    });
    vi.stubGlobal("fetch", fetchStub);

    const rows = await withMcpEdgeIdentity([...jwtRows(), privateRow], {
      identity: INVITE_IDENTITY,
    });
    expect(rows[0]?.token).toBeTruthy();
    expect(rows[1]?.token).toBeTruthy();
    expect(rows[2]?.token).toBeUndefined();
  });

  it("caches the private token per tenant, never across tenants", async () => {
    const fetchStub = stubDigikey({});
    await withMcpEdgeIdentity([privateRow], { identity: INVITE_IDENTITY });
    await withMcpEdgeIdentity([privateRow], { identity: INVITE_IDENTITY });
    expect(fetchStub).toHaveBeenCalledTimes(1);
    const rows = await withMcpEdgeIdentity([privateRow], {
      identity: { ...INVITE_IDENTITY, tenantSlug: "digithings-ai" },
    });
    expect(fetchStub).toHaveBeenCalledTimes(1);
    expect(rows[0]?.token).toBeUndefined();
  });
});
