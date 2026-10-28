/**
 * Identity at the MCP edge: digikey JWT verification plus the static-key
 * compat path, driven through `authorizeMcpEdge` (the decision index.ts makes
 * for `/_stack/mcp/<id>/…`).
 *
 * Every test is discriminating: it fails if the behaviour it names is removed.
 * The tokens here are signed by a keypair generated in the test and the JWKS
 * is a stubbed `fetch`, so there is no network and no fixture credential.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MCP_EDGE_JWKS_KV_KEY,
  MCP_EDGE_JWKS_TTL_MS,
  MCP_EDGE_MAX_INSPECT_BYTES,
  _resetMcpEdgeJwksCacheForTests,
  authorizeMcpEdge,
  mcpScopeForServer,
  mcpWriteScopeForTool,
  scopeGrants,
  verifyDigikeyJwt,
} from "./mcp-edge-auth";

const ISSUER = "https://key.digithings.ai";
const AUDIENCE = "digi-ecosystem";
const JWKS_URL = "https://key.digithings.ai/.well-known/jwks.json";

type Keypair = { kid: string; privateKey: CryptoKey; jwk: JsonWebKey };

function b64url(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function makeKeypair(kid: string): Promise<Keypair> {
  const pair = (await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const jwk = (await crypto.subtle.exportKey("jwk", pair.publicKey)) as JsonWebKey;
  return { kid, privateKey: pair.privateKey, jwk };
}

async function signJwt(
  key: Keypair,
  claims: Record<string, unknown>,
  header: Record<string, unknown> = {},
): Promise<string> {
  const head = b64url(
    new TextEncoder().encode(JSON.stringify({ alg: "RS256", typ: "JWT", kid: key.kid, ...header })),
  );
  const payload = b64url(new TextEncoder().encode(JSON.stringify(claims)));
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key.privateKey,
    new TextEncoder().encode(`${head}.${payload}`),
  );
  return `${head}.${payload}.${b64url(new Uint8Array(signature))}`;
}

function claimsFor(scope: string, overrides: Record<string, unknown> = {}) {
  return {
    iss: ISSUER,
    aud: AUDIENCE,
    sub: "bff:digithings-ai",
    tenant_slug: "digithings-ai",
    principal_kind: "bff_session",
    scope,
    exp: Math.floor(Date.now() / 1000) + 600,
    iat: Math.floor(Date.now() / 1000),
    ...overrides,
  };
}

/** A stubbed JWKS endpoint. `calls` counts fetches so rotation is observable. */
function stubJwks(keys: Keypair[]) {
  const fetchStub = vi.fn(async () => {
    return new Response(
      JSON.stringify({
        keys: keys.map((k) => ({ ...k.jwk, kid: k.kid, use: "sig", alg: "RS256" })),
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

const ENV = {
  DIGIKEY_JWKS_URL: JWKS_URL,
  DIGIKEY_ISSUER: ISSUER,
  DIGIKEY_AUDIENCE: AUDIENCE,
};

const STATIC_KEY = "edge-static-key-for-tests";

function req(headers: Record<string, string>): Request {
  return new Request("https://stack.test/_stack/mcp/digisearch/mcp", { headers });
}

function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

let primary: Keypair;

beforeEach(async () => {
  _resetMcpEdgeJwksCacheForTests();
  primary = await makeKeypair("kid-1");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  _resetMcpEdgeJwksCacheForTests();
});

describe("scope strings", () => {
  it("maps each edge server to its own mcp:<id> scope", () => {
    expect(mcpScopeForServer("digisearch")).toBe("mcp:digisearch");
    expect(mcpScopeForServer("digivault")).toBe("mcp:digivault");
    expect(mcpScopeForServer("digiquant")).toBe("digiquant:backtest");
    expect(mcpScopeForServer("unknown")).toBe("");
  });

  it("grants exact, wildcard-component and global scopes only", () => {
    expect(scopeGrants(["mcp:digisearch"], "mcp:digisearch")).toBe(true);
    expect(scopeGrants(["mcp:*"], "mcp:digisearch")).toBe(true);
    expect(scopeGrants(["*"], "mcp:digivault")).toBe(true);
    // A narrower grant never covers a different server, and never a prefix.
    expect(scopeGrants(["mcp:digisearch"], "mcp:digivault")).toBe(false);
    expect(scopeGrants(["mcp"], "mcp:digisearch")).toBe(false);
    expect(scopeGrants([], "mcp:digisearch")).toBe(false);
  });
});

describe("a valid, scoped digikey JWT", () => {
  it("is allowed on the server its scope names", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const decision = await authorizeMcpEdge({
      request: req(bearer(token)),
      serverId: "digisearch",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: true, via: "jwt", scope: "mcp:digisearch" });
  });

  it("is refused with 403 (not 401) on the other server", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const decision = await authorizeMcpEdge({
      request: req(bearer(token)),
      serverId: "digivault",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 403, reason: "missing_scope" });
  });

  it("accepts an mcp:* grant on both servers", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:*"));
    for (const serverId of ["digisearch", "digivault"]) {
      const decision = await authorizeMcpEdge({
        request: req(bearer(token)),
        serverId,
        expectedKey: "",
        env: ENV,
      });
      expect(decision.ok).toBe(true);
    }
  });

  it("reads a `scopes` array as well as the `scope` string", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, {
      ...claimsFor(""),
      scope: undefined,
      scopes: ["digigraph:chat", "mcp:digivault"],
    });
    const decision = await authorizeMcpEdge({
      request: req(bearer(token)),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision.ok).toBe(true);
  });
});

describe("fail closed", () => {
  async function refusal(
    token: string,
    opts: { serverId?: string; env?: typeof ENV; expectedKey?: string } = {},
  ) {
    return authorizeMcpEdge({
      request: req(bearer(token)),
      serverId: opts.serverId ?? "digisearch",
      expectedKey: opts.expectedKey ?? STATIC_KEY,
      env: opts.env ?? ENV,
    });
  }

  it("refuses an expired token", async () => {
    stubJwks([primary]);
    const token = await signJwt(
      primary,
      claimsFor("mcp:digisearch", { exp: Math.floor(Date.now() / 1000) - 3600 }),
    );
    expect(await refusal(token)).toEqual({ ok: false, status: 401, reason: "expired" });
  });

  it("refuses a token whose exp is inside the skew but already past", async () => {
    stubJwks([primary]);
    const token = await signJwt(
      primary,
      claimsFor("mcp:digisearch", { exp: Math.floor(Date.now() / 1000) - 61 }),
    );
    const decision = await refusal(token);
    expect(decision.ok).toBe(false);
    expect(decision).toMatchObject({ status: 401, reason: "expired" });
  });

  it("refuses a bad signature: right kid, different key", async () => {
    stubJwks([primary]);
    const impostor = await makeKeypair("kid-1");
    const token = await signJwt(impostor, claimsFor("mcp:digisearch"));
    expect(await refusal(token)).toEqual({ ok: false, status: 401, reason: "bad_signature" });
  });

  it("refuses a token signed with alg none", async () => {
    stubJwks([primary]);
    const head = b64url(
      new TextEncoder().encode(JSON.stringify({ alg: "none", typ: "JWT", kid: "kid-1" })),
    );
    const payload = b64url(new TextEncoder().encode(JSON.stringify(claimsFor("mcp:digisearch"))));
    // An empty signature is the classic alg:none token.
    expect(await refusal(`${head}.${payload}.`)).toMatchObject({
      ok: false,
      status: 401,
      reason: "malformed_token",
    });
    expect(await refusal(`${head}.${payload}.AAAA`)).toMatchObject({
      ok: false,
      status: 401,
      reason: "unsupported_alg",
    });
  });

  it("refuses a token from a different issuer", async () => {
    stubJwks([primary]);
    const token = await signJwt(
      primary,
      claimsFor("mcp:digisearch", { iss: "https://evil.example" }),
    );
    expect(await refusal(token)).toEqual({ ok: false, status: 401, reason: "wrong_issuer" });
  });

  it("refuses a token minted for a different audience", async () => {
    stubJwks([primary]);
    const token = await signJwt(
      primary,
      claimsFor("mcp:digisearch", { aud: "some-other-api" }),
    );
    expect(await refusal(token)).toEqual({ ok: false, status: 401, reason: "wrong_audience" });
  });

  it("refuses when no JWKS URL is configured (verification cannot run)", async () => {
    const fetchStub = stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    expect(await refusal(token, { env: { ...ENV, DIGIKEY_JWKS_URL: "" } })).toEqual({
      ok: false,
      status: 401,
      reason: "jwks_not_configured",
    });
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("refuses when the JWKS is unreachable", async () => {
    const fetchStub = vi.fn(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    vi.stubGlobal("fetch", fetchStub);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    expect(await refusal(token)).toEqual({
      ok: false,
      status: 401,
      reason: "jwks_unavailable",
    });
  });

  it("refuses when the JWKS answers a non-200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("nope", { status: 503 })),
    );
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    expect(await refusal(token)).toMatchObject({ ok: false, reason: "jwks_unavailable" });
  });

  it("refuses a request with no credential at all", async () => {
    stubJwks([primary]);
    const decision = await authorizeMcpEdge({
      request: new Request("https://stack.test/_stack/mcp/digisearch/mcp"),
      serverId: "digisearch",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 401, reason: "no_credential" });
  });

  it("never treats an unconfigured edge key as matching an empty header", async () => {
    stubJwks([primary]);
    const decision = await authorizeMcpEdge({
      request: req({ "x-digi-mcp-key": "" }),
      serverId: "digisearch",
      expectedKey: "",
      env: ENV,
    });
    expect(decision.ok).toBe(false);
    expect(decision).toMatchObject({ status: 401 });
  });
});

describe("key rotation and JWKS caching", () => {
  it("refetches exactly once on an unknown kid, then accepts the rotated key", async () => {
    const rotated = await makeKeypair("kid-2");
    // The stub serves whatever is in `served`, so the first request primes the
    // cache with kid-1 and the unknown-kid path is what picks kid-2 up.
    const served: Keypair[] = [primary];
    const fetchStub = vi.fn(async () =>
      new Response(
        JSON.stringify({
          keys: served.map((k) => ({ ...k.jwk, kid: k.kid, use: "sig", alg: "RS256" })),
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchStub);

    const before = await signJwt(primary, claimsFor("mcp:digisearch"));
    expect((await verifyDigikeyJwt(before, ENV)).ok).toBe(true);
    expect(fetchStub).toHaveBeenCalledTimes(1);

    // Rotation: the JWKS now serves kid-2 only.
    served.length = 0;
    served.push(rotated);
    const after = await signJwt(rotated, claimsFor("mcp:digisearch"));
    const decision = await verifyDigikeyJwt(after, ENV);
    expect(decision.ok).toBe(true);
    // One cached read, one refetch — exactly the single refetch a rotation may cost.
    expect(fetchStub).toHaveBeenCalledTimes(2);

    // And the new key is now cached: no further fetch.
    expect((await verifyDigikeyJwt(after, ENV)).ok).toBe(true);
    expect(fetchStub).toHaveBeenCalledTimes(2);
  });

  it("refuses an unknown kid after one refetch, and does not loop", async () => {
    const fetchStub = stubJwks([primary]);
    const stranger = await makeKeypair("kid-unknown");
    const token = await signJwt(stranger, claimsFor("mcp:digisearch"));
    const decision = await verifyDigikeyJwt(token, ENV);
    expect(decision).toEqual({ ok: false, reason: "unknown_kid" });
    // Initial fetch + the one refetch, not one fetch per attempt.
    expect(fetchStub).toHaveBeenCalledTimes(2);

    expect(await verifyDigikeyJwt(token, ENV)).toMatchObject({ ok: false, reason: "unknown_kid" });
    expect(fetchStub).toHaveBeenCalledTimes(3);
  });

  it("serves repeat requests from cache inside the TTL", async () => {
    const fetchStub = stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    for (let i = 0; i < 5; i += 1) {
      expect((await verifyDigikeyJwt(token, ENV)).ok).toBe(true);
    }
    expect(fetchStub).toHaveBeenCalledTimes(1);
  });

  it("joins a single in-flight fetch instead of one per concurrent request", async () => {
    const releasers: Array<() => void> = [];
    const gate = new Promise<void>((resolve) => {
      releasers.push(resolve);
    });
    const fetchStub = vi.fn(async () => {
      await gate;
      return new Response(
        JSON.stringify({
          keys: [{ ...primary.jwk, kid: primary.kid, use: "sig", alg: "RS256" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchStub);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const pending = Promise.all([
      verifyDigikeyJwt(token, ENV),
      verifyDigikeyJwt(token, ENV),
      verifyDigikeyJwt(token, ENV),
    ]);
    releasers[0]?.();
    const results = await pending;
    expect(results.every((r) => r.ok)).toBe(true);
    expect(fetchStub).toHaveBeenCalledTimes(1);
  });

  it("expires the cache after the TTL", async () => {
    const fetchStub = stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    expect((await verifyDigikeyJwt(token, ENV)).ok).toBe(true);
    const realNow = Date.now();
    const spy = vi.spyOn(Date, "now").mockReturnValue(realNow + MCP_EDGE_JWKS_TTL_MS + 1_000);
    try {
      expect((await verifyDigikeyJwt(token, ENV)).ok).toBe(true);
    } finally {
      spy.mockRestore();
    }
    expect(fetchStub).toHaveBeenCalledTimes(2);
  });
});

describe("the static key keeps working", () => {
  it("allows a request with only x-digi-mcp-key, no JWKS fetch", async () => {
    const fetchStub = stubJwks([primary]);
    const decision = await authorizeMcpEdge({
      request: req({ "x-digi-mcp-key": STATIC_KEY }),
      serverId: "digisearch",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: true, via: "key" });
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("wins over a broken bearer token when both are present", async () => {
    stubJwks([primary]);
    const decision = await authorizeMcpEdge({
      request: req({ "x-digi-mcp-key": STATIC_KEY, ...bearer("not-a-jwt") }),
      serverId: "digivault",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: true, via: "key" });
  });

  it("refuses a wrong key", async () => {
    stubJwks([primary]);
    const decision = await authorizeMcpEdge({
      request: req({ "x-digi-mcp-key": "wrong" }),
      serverId: "digisearch",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 401, reason: "invalid_key" });
  });

  it("does not fall back to the key when the JWT is valid but unscoped", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const decision = await authorizeMcpEdge({
      request: req({ "x-digi-mcp-key": "wrong", ...bearer(token) }),
      serverId: "digivault",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 403, reason: "missing_scope" });
  });
});

describe("no secret in the log", () => {
  it("logs the decision and the scope, never the token or the key", async () => {
    stubJwks([primary]);
    const lines: string[] = [];
    vi.spyOn(console, "log").mockImplementation((...args: unknown[]) => {
      lines.push(args.map((a) => String(a)).join(" "));
    });
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    await authorizeMcpEdge({
      request: req(bearer(token)),
      serverId: "digisearch",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    await authorizeMcpEdge({
      request: req({ "x-digi-mcp-key": STATIC_KEY }),
      serverId: "digivault",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    const joined = lines.join("\n");
    expect(joined).toContain("mcp_edge_auth");
    expect(joined).toContain("mcp:digisearch");
    expect(joined).not.toContain(token);
    // No prefix of the token either: the first 16 characters are not logged.
    expect(joined).not.toContain(token.slice(0, 16));
    expect(joined).not.toContain(STATIC_KEY);
  });
});

describe("JWKS sources", () => {
  const body = (k: Keypair): string =>
    JSON.stringify({ keys: [{ ...k.jwk, kid: k.kid, use: "sig", alg: "RS256" }] });

  it("reads the JWKS from KV and never touches the network", async () => {
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const fetchStub = vi.fn(async () => {
      throw new Error("network must not be used when KV has the keys");
    });
    vi.stubGlobal("fetch", fetchStub);
    const env = {
      ...ENV,
      TENANT_CONFIG: { get: async () => body(primary), put: async () => {} },
    };
    expect((await verifyDigikeyJwt(token, env)).ok).toBe(true);
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("fetches through the DIGIKEY_SELF binding, not the global fetch", async () => {
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    // key.digithings.ai is this Worker's own route: a global fetch cannot reach
    // it from inside, so the binding is the only working path.
    const fetchStub = vi.fn(async () => {
      throw new Error("global fetch must not be used when the binding is bound");
    });
    vi.stubGlobal("fetch", fetchStub);
    const bound = vi.fn(async () => new Response(body(primary), { status: 200 }));
    const env = { ...ENV, DIGIKEY_SELF: { fetch: bound } };
    expect((await verifyDigikeyJwt(token, env)).ok).toBe(true);
    expect(bound).toHaveBeenCalledTimes(1);
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("caches a fetched JWKS back to KV for the next cold isolate", async () => {
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const put = vi.fn(async () => {});
    const bound = vi.fn(async () => new Response(body(primary), { status: 200 }));
    const env = {
      ...ENV,
      DIGIKEY_SELF: { fetch: bound },
      TENANT_CONFIG: { get: async () => null, put },
    };
    expect((await verifyDigikeyJwt(token, env)).ok).toBe(true);
    expect(put).toHaveBeenCalledWith(MCP_EDGE_JWKS_KV_KEY, expect.stringContaining("kid-1"));
  });

  it("prefers the stack's own STACK_CACHE over TENANT_CONFIG when both are bound", async () => {
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network must not be used when KV has the keys");
      }),
    );
    const tenantGet = vi.fn(async () => body(primary));
    const tenantPut = vi.fn(async () => {});
    const env = {
      ...ENV,
      TENANT_CONFIG: { get: tenantGet, put: tenantPut },
      STACK_CACHE: { get: async () => body(primary), put: async () => {} },
    };
    expect((await verifyDigikeyJwt(token, env)).ok).toBe(true);
    expect(tenantGet).not.toHaveBeenCalled();
    expect(tenantPut).not.toHaveBeenCalled();
  });

  it("writes a fetched JWKS to STACK_CACHE, never to the tenant namespace", async () => {
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const stackPut = vi.fn(async () => {});
    const tenantPut = vi.fn(async () => {});
    const bound = vi.fn(async () => new Response(body(primary), { status: 200 }));
    const env = {
      ...ENV,
      DIGIKEY_SELF: { fetch: bound },
      TENANT_CONFIG: { get: async () => body(primary), put: tenantPut },
      STACK_CACHE: { get: async () => null, put: stackPut },
    };
    expect((await verifyDigikeyJwt(token, env)).ok).toBe(true);
    expect(stackPut).toHaveBeenCalledWith(MCP_EDGE_JWKS_KV_KEY, expect.stringContaining("kid-1"));
    expect(tenantPut).not.toHaveBeenCalled();
  });

  it("refuses when neither KV nor the network yields keys", async () => {
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    const env = {
      ...ENV,
      TENANT_CONFIG: { get: async () => null, put: async () => {} },
    };
    expect((await verifyDigikeyJwt(token, env)).ok).toBe(false);
  });
});

/**
 * `mcp:<serverId>` is read-only (DIG-5723). The tool name only exists in the
 * JSON-RPC body, so these tests drive the real request shape a client sends:
 * a POST to `/_stack/mcp/digivault/mcp` with `tools/call`.
 */
describe("write tools need their own scope", () => {
  function toolCall(
    body: unknown,
    token: string,
    serverId = "digivault",
    method = "POST",
  ): Request {
    return new Request(`https://stack.test/_stack/mcp/${serverId}/mcp`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: method === "POST" ? JSON.stringify(body) : undefined,
    });
  }

  function rpc(tool: string, id = 1) {
    return {
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: { name: tool, arguments: {} },
    };
  }

  it("maps the one mutating digivault tool to its write scope", () => {
    expect(mcpWriteScopeForTool("digivault", "create_note")).toBe("mcp:digivault:write");
    // Reads need nothing beyond the server scope.
    expect(mcpWriteScopeForTool("digivault", "search_notes")).toBe("");
    expect(mcpWriteScopeForTool("digivault", "search_tag")).toBe("");
    // The static-key-only servers keep their historical surface.
    expect(mcpWriteScopeForTool("digisearch", "websets_create")).toBe("");
    expect(mcpWriteScopeForTool("unknown", "create_note")).toBe("");
  });

  it("lets mcp:digivault run a read tool", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault"));
    const decision = await authorizeMcpEdge({
      request: toolCall(rpc("search_notes"), token),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision).toEqual({ ok: true, via: "jwt", scope: "mcp:digivault" });
  });

  it("refuses create_note with 403 for mcp:digivault alone", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault"));
    const decision = await authorizeMcpEdge({
      request: toolCall(rpc("create_note"), token),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 403, reason: "missing_scope" });
  });

  it("refuses a write tool inside a JSON-RPC batch", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault"));
    const decision = await authorizeMcpEdge({
      request: toolCall(
        [{ jsonrpc: "2.0", id: 0, method: "initialize", params: {} }, rpc("create_note")],
        token,
      ),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 403, reason: "missing_scope" });
  });

  it("allows create_note when the token carries the write scope too", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault mcp:digivault:write"));
    const decision = await authorizeMcpEdge({
      request: toolCall(rpc("create_note"), token),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision.ok).toBe(true);
  });

  it("does not let a write scope stand in for the read scope", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault:write"));
    const decision = await authorizeMcpEdge({
      request: toolCall(rpc("create_note"), token),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 403, reason: "missing_scope" });
  });

  it("keeps the static-key compat path unchanged", async () => {
    stubJwks([primary]);
    const request = new Request("https://stack.test/_stack/mcp/digivault/mcp", {
      method: "POST",
      headers: { "x-digi-mcp-key": STATIC_KEY, "content-type": "application/json" },
      body: JSON.stringify(rpc("create_note")),
    });
    const decision = await authorizeMcpEdge({
      request,
      serverId: "digivault",
      expectedKey: STATIC_KEY,
      env: ENV,
    });
    expect(decision).toEqual({ ok: true, via: "key" });
  });

  it("ignores a GET, which opens the stream and calls no tool", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault"));
    const decision = await authorizeMcpEdge({
      request: toolCall(null, token, "digivault", "GET"),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision.ok).toBe(true);
  });

  it("refuses a JWT-authenticated body it cannot inspect", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault"));
    const decision = await authorizeMcpEdge({
      request: new Request("https://stack.test/_stack/mcp/digivault/mcp", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: "{not json",
      }),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 400, reason: "uninspectable_body" });
  });

  it("refuses an oversized body rather than passing it uninspected", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digivault"));
    const decision = await authorizeMcpEdge({
      request: new Request("https://stack.test/_stack/mcp/digivault/mcp", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "content-length": String(MCP_EDGE_MAX_INSPECT_BYTES + 1),
        },
        body: "{}",
      }),
      serverId: "digivault",
      expectedKey: "",
      env: ENV,
    });
    expect(decision).toEqual({ ok: false, status: 400, reason: "uninspectable_body" });
  });

  it("leaves the digisearch surface alone", async () => {
    stubJwks([primary]);
    const token = await signJwt(primary, claimsFor("mcp:digisearch"));
    const decision = await authorizeMcpEdge({
      request: toolCall(rpc("websets_create"), token, "digisearch"),
      serverId: "digisearch",
      expectedKey: "",
      env: ENV,
    });
    expect(decision.ok).toBe(true);
  });
});
