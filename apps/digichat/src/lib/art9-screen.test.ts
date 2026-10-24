/**
 * Tests for the Art. 9 transcript screening hop (DIG-1178 leaf 12d).
 *
 * Fail-closed on every path: only a `200` carrying `decision == "allow"`
 * permits the write. Policy refusal (including `mask`), hop failures,
 * transport errors and missing configuration all refuse it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CODE_REFUSED,
  CODE_UNAVAILABLE,
  resolveScreenBaseUrl,
  screenConversationWrite,
} from "./art9-screen";
import { withDigisearchCapability } from "@/lib/ecosystem";

vi.mock("@/lib/digigraph-upstream", () => ({
  resolveDigigraphUpstreamAuth: vi.fn(),
}));

import { resolveDigigraphUpstreamAuth } from "@/lib/digigraph-upstream";

const ENV_URL = "http://127.0.0.1:8002";
const savedEnv: Record<string, string | undefined> = {};

function stubEnv(url: string | undefined, services?: string) {
  if (url === undefined) delete process.env.DIGISEARCH_INTERNAL_URL;
  else process.env.DIGISEARCH_INTERNAL_URL = url;
  if (services === undefined) delete process.env.DIGICHAT_ENABLED_SERVICES;
  else process.env.DIGICHAT_ENABLED_SERVICES = services;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const baseArgs = {
  req: new Request("http://localhost/api/conversations/conv-1", {
    method: "PUT",
    headers: {
      // Tenant-influenced cookie: the screen hop must ignore it (trap 1).
      cookie: "digichat-endpoints=http://decoy-host:9999",
    },
  }),
  tenantSlug: "acme",
  ownerUserSub: "user-1",
  conversationId: "conv-1",
  messages: [{ id: "m1", role: "user", parts: [{ text: "hello" }] }],
};

describe("art9-screen", () => {
  beforeEach(() => {
    for (const k of ["DIGISEARCH_INTERNAL_URL", "DIGICHAT_ENABLED_SERVICES"]) {
      savedEnv[k] = process.env[k];
    }
    stubEnv(ENV_URL);
    vi.mocked(resolveDigigraphUpstreamAuth).mockResolvedValue({
      bearer: "test-bearer",
      litellmProxyApiKey: null,
    });
    vi.stubGlobal("fetch", vi.fn());
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    for (const k of ["DIGISEARCH_INTERNAL_URL", "DIGICHAT_ENABLED_SERVICES"]) {
      if (savedEnv[k] === undefined) delete process.env[k];
      else process.env[k] = savedEnv[k];
    }
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("200 allow permits the write", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, {
        decision: "allow",
        categories: [],
        reason: "art9:clear",
      })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v).toEqual({ allowed: true });
  });

  it("422 refusal blocks the write with ids and reason only", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(422, {
        code: "art9_refused",
        decision: "refuse",
        categories: ["art9:health"],
        reason: "art9:health:field-name",
        exception_ref: null,
      })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
    if (!v.allowed) {
      expect(v.code).toBe(CODE_REFUSED);
      expect(v.categories).toEqual(["art9:health"]);
      expect(v.reason).toBe("art9:health:field-name");
    }
    // Logged with category ids and reason code only.
    const logged = vi
      .mocked(console.warn)
      .mock.calls.map((c) => String(c[0]))
      .join("\n");
    expect(logged).toContain("art9:health");
    expect(logged).toContain("art9:health:field-name");
    expect(logged).not.toContain("hello");
  });

  it("502 hop failure blocks the write", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(502, { code: "art9_screen_unavailable" })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v).toEqual({
      allowed: false,
      code: CODE_UNAVAILABLE,
      categories: [],
      reason: CODE_UNAVAILABLE,
    });
  });

  it("503 blocks the write", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(503, { code: "art9_screen_unavailable" })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.code).toBe(CODE_UNAVAILABLE);
  });

  it("mask counts as refuse: no lawful basis to store it in v1", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(422, {
        code: "art9_refused",
        decision: "mask",
        categories: ["art9:health"],
        reason: "art9:health:field-name",
        exception_ref: null,
      })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.code).toBe(CODE_REFUSED);
  });

  it("transport error blocks the write", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("fetch failed"));
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.code).toBe(CODE_UNAVAILABLE);
  });

  it("unparseable body blocks the write", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("not-json", { status: 200 })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
  });

  it("failed upstream auth exchange blocks the write", async () => {
    vi.mocked(resolveDigigraphUpstreamAuth).mockRejectedValue(
      new Error("digikey bff_session exchange failed")
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.code).toBe(CODE_UNAVAILABLE);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("missing DIGISEARCH_INTERNAL_URL blocks the write without a fetch", async () => {
    stubEnv(undefined);
    expect(resolveScreenBaseUrl()).toBeNull();
    const v = await screenConversationWrite(baseArgs);
    expect(v.allowed).toBe(false);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("cookie URL is never consulted: the request goes to the env URL", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { decision: "allow", categories: [], reason: "art9:clear" })
    );
    await screenConversationWrite(baseArgs);
    expect(vi.mocked(fetch)).toHaveBeenCalledOnce();
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(`${ENV_URL}/internal/art9/screen`);
    expect(String(url)).not.toContain("decoy-host");
  });

  it("capability object is never consulted: screening stays on when the feature is off", async () => {
    // With the digisearch *feature* off, withDigisearchCapability() deletes
    // digisearchUrl — which must not disable *screening*.
    stubEnv(ENV_URL, "digigraph,digiquant,digitrace");
    const capped = withDigisearchCapability({
      digigraphUrl: "http://127.0.0.1:8000",
      digiquantUrl: "http://127.0.0.1:8001",
      digitraceUrl: "http://127.0.0.3:8003",
      digisearchUrl: "http://127.0.0.1:8002",
    });
    expect(capped.digisearchUrl).toBeUndefined();
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { decision: "allow", categories: [], reason: "art9:clear" })
    );
    const v = await screenConversationWrite(baseArgs);
    expect(v).toEqual({ allowed: true });
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(`${ENV_URL}/internal/art9/screen`);
  });

  it("trailing slash in the env URL is stripped", () => {
    stubEnv("http://127.0.0.1:8002/");
    expect(resolveScreenBaseUrl()).toBe(ENV_URL);
  });

  it("outgoing request carries no tenant, no ownerUserSub, no client name", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { decision: "allow", categories: [], reason: "art9:clear" })
    );
    await screenConversationWrite(baseArgs);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(`${ENV_URL}/internal/art9/screen`);
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe("Bearer test-bearer");
    expect(headers.get("x-digichat-tenant")).toBeNull();
    expect(headers.get("x-digi-tenant")).toBeNull();
    expect(headers.get("x-digi-caller")).toBeNull();
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual([
      "conversation_id",
      "messages",
      "surface",
    ]);
    expect(body.surface).toBe("digichat");
    const raw = String(init?.body);
    expect(raw).not.toContain("acme");
    expect(raw).not.toContain("user-1");
  });
});
