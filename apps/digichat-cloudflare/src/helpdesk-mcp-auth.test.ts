/**
 * The helpdesk MCP gate, executed (DIG-3585).
 *
 * Keys are generated per run with WebCrypto; the JWKS is served by a stub, so
 * nothing leaves the process.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import {
  HELPDESK_MCP_SCOPE,
  HELPDESK_MCP_TENANTS,
  _resetHelpdeskJwksCacheForTests,
  authorizeHelpdeskMcp,
  helpdeskJwtOnly,
  type HelpdeskMcpOptions,
} from "./helpdesk-mcp-auth";
import { MCP_KEY_HEADER } from "./mcp-gate";

const here = path.dirname(fileURLToPath(import.meta.url));
const EDGE_KEY = "edge-test-value";
const ISS = "https://key.digithings.ai";
const AUD = "digi-ecosystem";
const TENANT = [...HELPDESK_MCP_TENANTS][0]!;

type KeyPair = { privateKey: CryptoKey; jwk: JsonWebKey & { kid: string } };

async function makeKey(kid: string): Promise<KeyPair> {
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
  return { privateKey: pair.privateKey, jwk: { ...jwk, kid, use: "sig", alg: "RS256" } };
}

function b64url(bytes: Uint8Array | string): string {
  const raw = typeof bytes === "string" ? new TextEncoder().encode(bytes) : bytes;
  let bin = "";
  for (const b of raw) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sign(
  key: KeyPair,
  claims: Record<string, unknown>,
  header: Record<string, unknown> = {},
): Promise<string> {
  const h = b64url(JSON.stringify({ alg: "RS256", typ: "JWT", kid: key.jwk.kid, ...header }));
  const p = b64url(JSON.stringify(claims));
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key.privateKey,
    new TextEncoder().encode(`${h}.${p}`),
  );
  return `${h}.${p}.${b64url(new Uint8Array(sig))}`;
}

function claims(over: Record<string, unknown> = {}): Record<string, unknown> {
  const now = Math.floor(Date.now() / 1000);
  return {
    sub: "chat-identity",
    iss: ISS,
    aud: AUD,
    iat: now,
    exp: now + 300,
    jti: "j1",
    scopes: [HELPDESK_MCP_SCOPE],
    scope: HELPDESK_MCP_SCOPE,
    principal_kind: "api_key",
    tenant_slug: "house",
    ...over,
  };
}

const MCP = "https://digithings.ai/api/mcp/zammad/mcp";

function req(headers: Record<string, string> = {}, url = MCP): Request {
  return new Request(url, { method: "POST", headers });
}

let signing: KeyPair;
let rotated: KeyPair;
let served: JsonWebKey[];
let fetchJwks: ReturnType<typeof vi.fn<NonNullable<HelpdeskMcpOptions["fetchJwks"]>>>;
let opts: HelpdeskMcpOptions;

beforeAll(async () => {
  signing = await makeKey("k1");
  rotated = await makeKey("k2");
});

beforeEach(() => {
  _resetHelpdeskJwksCacheForTests();
  served = [signing.jwk];
  fetchJwks = vi.fn<NonNullable<HelpdeskMcpOptions["fetchJwks"]>>(async () =>
    Response.json({ keys: served }),
  );
  opts = { fetchJwks };
  vi.spyOn(console, "log").mockImplementation(() => {});
});

const keyOn = { ZAMMAD_EDGE_KEY: EDGE_KEY };
const jwtOnly = { ZAMMAD_EDGE_KEY: EDGE_KEY, ZAMMAD_MCP_JWT_ONLY: "1" };

async function bearer(over: Record<string, unknown> = {}, key = signing) {
  return { authorization: `Bearer ${await sign(key, claims(over))}` };
}

describe("default mode (flag unset): nothing breaks before the cutover", () => {
  it("still opens on the edge key, on both spellings", async () => {
    for (const url of [MCP, "https://digithings.ai/chat/api/mcp/zammad/mcp"]) {
      const gate = await authorizeHelpdeskMcp(
        req({ [MCP_KEY_HEADER]: EDGE_KEY }, url),
        new URL(url).pathname,
        keyOn,
        opts,
      );
      expect(gate).toEqual({ kind: "authorized", via: "key" });
    }
    expect(fetchJwks).not.toHaveBeenCalled();
  });

  it("also opens on a valid scoped token", async () => {
    const gate = await authorizeHelpdeskMcp(
      req(await bearer()),
      "/api/mcp/zammad/mcp",
      keyOn,
      opts,
    );
    expect(gate).toEqual({ kind: "authorized", via: "jwt" });
  });

  it("refuses no credential and a wrong key", async () => {
    expect(await authorizeHelpdeskMcp(req(), "/api/mcp/zammad", keyOn, opts)).toMatchObject({
      kind: "unauthorized",
      status: 401,
      reason: "no_credential",
    });
    expect(
      await authorizeHelpdeskMcp(req({ [MCP_KEY_HEADER]: "nope" }), "/api/mcp/zammad", keyOn, opts),
    ).toMatchObject({ kind: "unauthorized", status: 401, reason: "invalid_key" });
  });

  it("leaves other paths alone", async () => {
    expect(await authorizeHelpdeskMcp(req(), "/chat", keyOn, opts)).toEqual({ kind: "not-mcp" });
    expect(await authorizeHelpdeskMcp(req(), "/api/mcp/other", keyOn, opts)).toEqual({
      kind: "not-mcp",
    });
  });
});

describe("ZAMMAD_MCP_JWT_ONLY=1: only the invite-gated chat's token opens it", () => {
  it("reads the flag strictly", () => {
    expect(helpdeskJwtOnly({ ZAMMAD_MCP_JWT_ONLY: "1" })).toBe(true);
    expect(helpdeskJwtOnly({ ZAMMAD_MCP_JWT_ONLY: " 1 " })).toBe(true);
    for (const v of [undefined, "", "0", "true", "yes"]) {
      expect(helpdeskJwtOnly({ ZAMMAD_MCP_JWT_ONLY: v })).toBe(false);
    }
  });

  it("refuses the correct edge key", async () => {
    const gate = await authorizeHelpdeskMcp(
      req({ [MCP_KEY_HEADER]: EDGE_KEY }),
      "/api/mcp/zammad/mcp",
      jwtOnly,
      opts,
    );
    expect(gate).toMatchObject({ kind: "unauthorized", status: 401, reason: "static_key_refused" });
  });

  it("refuses the edge key on the base-path spelling too", async () => {
    const gate = await authorizeHelpdeskMcp(
      req({ [MCP_KEY_HEADER]: EDGE_KEY }, "https://digithings.ai/chat/api/mcp/zammad/mcp"),
      "/chat/api/mcp/zammad/mcp",
      jwtOnly,
      opts,
    );
    expect(gate.kind).toBe("unauthorized");
  });

  it("opens on the chat identity's scoped token (api_key principal)", async () => {
    const gate = await authorizeHelpdeskMcp(
      req(await bearer()),
      "/api/mcp/zammad/mcp",
      jwtOnly,
      opts,
    );
    expect(gate).toEqual({ kind: "authorized", via: "jwt" });
  });

  it("opens on an invite-gated tenant's session token, and only that tenant's", async () => {
    const ok = await authorizeHelpdeskMcp(
      req(await bearer({ principal_kind: "bff_session", tenant_slug: TENANT })),
      "/api/mcp/zammad/mcp",
      jwtOnly,
      opts,
    );
    expect(ok).toEqual({ kind: "authorized", via: "jwt" });
    for (const tenant_slug of ["digithings", "", undefined]) {
      const gate = await authorizeHelpdeskMcp(
        req(await bearer({ principal_kind: "bff_session", tenant_slug })),
        "/api/mcp/zammad/mcp",
        jwtOnly,
        opts,
      );
      expect(gate).toMatchObject({ kind: "unauthorized", status: 403, reason: "wrong_tenant" });
    }
  });

  it("needs the exact scope: no scope, a neighbour's scope and wildcards are refused", async () => {
    for (const scopes of [[], ["mcp:digisearch"], ["*"], ["mcp:*"], ["mcp:zammad:write"]]) {
      const gate = await authorizeHelpdeskMcp(
        req(await bearer({ scopes, scope: scopes.join(" ") })),
        "/api/mcp/zammad/mcp",
        jwtOnly,
        opts,
      );
      expect(gate).toMatchObject({ kind: "unauthorized", status: 403, reason: "missing_scope" });
    }
  });

  it("accepts the scope from the space-delimited claim when the array is absent", async () => {
    const gate = await authorizeHelpdeskMcp(
      req(await bearer({ scopes: undefined, scope: `mcp:digisearch ${HELPDESK_MCP_SCOPE}` })),
      "/api/mcp/zammad/mcp",
      jwtOnly,
      opts,
    );
    expect(gate.kind).toBe("authorized");
  });

  it("refuses other principals", async () => {
    for (const principal_kind of ["service", "user", "", undefined]) {
      const gate = await authorizeHelpdeskMcp(
        req(await bearer({ principal_kind })),
        "/api/mcp/zammad/mcp",
        jwtOnly,
        opts,
      );
      expect(gate).toMatchObject({ kind: "unauthorized", status: 403, reason: "wrong_principal" });
    }
  });

  it("refuses expired, future, wrong issuer and wrong audience tokens", async () => {
    const now = Math.floor(Date.now() / 1000);
    const cases: [Record<string, unknown>, string][] = [
      [{ exp: now - 120 }, "expired"],
      [{ exp: undefined }, "malformed_token"],
      [{ nbf: now + 600 }, "not_yet_valid"],
      [{ iss: "https://evil.example" }, "wrong_issuer"],
      [{ aud: "other" }, "wrong_audience"],
    ];
    for (const [over, reason] of cases) {
      const gate = await authorizeHelpdeskMcp(
        req(await bearer(over)),
        "/api/mcp/zammad",
        jwtOnly,
        opts,
      );
      expect(gate).toMatchObject({ kind: "unauthorized", status: 401, reason });
    }
  });

  it("refuses a token signed by a key digikey does not publish", async () => {
    const gate = await authorizeHelpdeskMcp(
      req(await bearer({}, rotated)),
      "/api/mcp/zammad",
      jwtOnly,
      opts,
    );
    expect(gate).toMatchObject({ kind: "unauthorized", reason: "unknown_kid" });
  });

  it("refuses a forged signature under a published kid", async () => {
    const forged = await sign(rotated, claims(), { kid: signing.jwk.kid });
    const gate = await authorizeHelpdeskMcp(
      req({ authorization: `Bearer ${forged}` }),
      "/api/mcp/zammad",
      jwtOnly,
      opts,
    );
    expect(gate).toMatchObject({ kind: "unauthorized", reason: "bad_signature" });
  });

  it("refuses alg none and HMAC tokens before any key lookup", async () => {
    for (const alg of ["none", "HS256"]) {
      const token = `${b64url(JSON.stringify({ alg, kid: "k1" }))}.${b64url(JSON.stringify(claims()))}.AAAA`;
      const gate = await authorizeHelpdeskMcp(
        req({ authorization: `Bearer ${token}` }),
        "/api/mcp/zammad",
        jwtOnly,
        opts,
      );
      expect(gate).toMatchObject({ kind: "unauthorized", reason: "unsupported_alg" });
    }
    expect(fetchJwks).not.toHaveBeenCalled();
  });

  it("refuses garbage", async () => {
    for (const value of ["Bearer", "Bearer a.b", "Bearer a.b.c", "Basic abc"]) {
      const gate = await authorizeHelpdeskMcp(
        req({ authorization: value }),
        "/api/mcp/zammad",
        jwtOnly,
        opts,
      );
      expect(gate.kind).toBe("unauthorized");
    }
  });

  it("fails closed when the JWKS cannot be read", async () => {
    for (const impl of [
      async () => new Response("down", { status: 503 }),
      async () => {
        throw new Error("network");
      },
      async () => Response.json({ keys: [] }),
    ]) {
      _resetHelpdeskJwksCacheForTests();
      const gate = await authorizeHelpdeskMcp(req(await bearer()), "/api/mcp/zammad", jwtOnly, {
        fetchJwks: vi.fn(impl),
      });
      expect(gate).toMatchObject({ kind: "unauthorized", status: 401, reason: "jwks_unavailable" });
    }
  });

  it("caches the JWKS and refetches once for a rotated kid", async () => {
    await authorizeHelpdeskMcp(req(await bearer()), "/api/mcp/zammad", jwtOnly, opts);
    await authorizeHelpdeskMcp(req(await bearer()), "/api/mcp/zammad", jwtOnly, opts);
    expect(fetchJwks).toHaveBeenCalledTimes(1);
    served = [signing.jwk, rotated.jwk];
    const gate = await authorizeHelpdeskMcp(
      req(await bearer({}, rotated)),
      "/api/mcp/zammad",
      jwtOnly,
      opts,
    );
    expect(gate.kind).toBe("authorized");
    expect(fetchJwks).toHaveBeenCalledTimes(2);
  });

  it("uses the DIGIKEY service binding when it is bound", async () => {
    const binding = { fetch: vi.fn(async () => Response.json({ keys: [signing.jwk] })) };
    const gate = await authorizeHelpdeskMcp(req(await bearer()), "/api/mcp/zammad", {
      ...jwtOnly,
      DIGIKEY: binding,
    });
    expect(gate.kind).toBe("authorized");
    expect(binding.fetch).toHaveBeenCalledWith(
      "https://key.digithings.ai/.well-known/jwks.json",
      expect.anything(),
    );
  });

  it("never logs the token or the key", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const token = await sign(signing, claims());
    await authorizeHelpdeskMcp(
      req({ authorization: `Bearer ${token}` }),
      "/api/mcp/zammad",
      jwtOnly,
      opts,
    );
    await authorizeHelpdeskMcp(
      req({ [MCP_KEY_HEADER]: EDGE_KEY }),
      "/api/mcp/zammad",
      jwtOnly,
      opts,
    );
    const out = log.mock.calls.flat().join("\n");
    expect(out).not.toContain(token.split(".")[2]!);
    expect(out).not.toContain(EDGE_KEY);
  });
});

describe("parity with the app", () => {
  it("the gate's tenants are exactly digichat's invite-only tenants", () => {
    const source = readFileSync(
      path.resolve(here, "../../digichat/src/lib/embed-invite-only.ts"),
      "utf8",
    );
    const block = /INVITE_ONLY_EMBED_HOSTS[^=]*=\s*new Map[^(]*\(\[([\s\S]*?)\]\s*\)/.exec(source);
    expect(block, "INVITE_ONLY_EMBED_HOSTS not found").not.toBeNull();
    const slugs = [...block![1]!.matchAll(/\[\s*"[^"]+"\s*,\s*"([^"]+)"\s*\]/g)].map((m) => m[1]);
    expect(new Set(slugs)).toEqual(new Set(HELPDESK_MCP_TENANTS));
  });
});
