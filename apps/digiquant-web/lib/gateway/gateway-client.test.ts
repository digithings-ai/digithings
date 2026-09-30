/**
 * Tests for the browser-side local gateway URL/config client utility.
 *
 * The gateway runs at 127.0.0.1:8792 (local only). The utility reads
 * NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL, validates the URL, checks the current
 * page hostname, and exposes typed fetch functions that never throw to callers.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  validateGatewayUrl,
  resolveGatewayState,
  fetchHealthz,
  fetchLuxalgoSearch,
  type ProbeEnvelope,
} from "./gateway-client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

// ─── validateGatewayUrl ────────────────────────────────────────────────────

describe("validateGatewayUrl", () => {
  it("returns false for an empty string", () => {
    expect(validateGatewayUrl("")).toBe(false);
  });

  it("returns false for a whitespace-only string", () => {
    expect(validateGatewayUrl("   ")).toBe(false);
  });

  it("returns false for a non-URL string", () => {
    expect(validateGatewayUrl("not-a-url")).toBe(false);
  });

  it("returns false for HTTPS (must be plain HTTP)", () => {
    expect(validateGatewayUrl("https://localhost:8792")).toBe(false);
  });

  it("returns false when a username is present", () => {
    expect(validateGatewayUrl("http://user@localhost:8792")).toBe(false);
  });

  it("returns false when a password is present", () => {
    expect(validateGatewayUrl("http://user:pass@localhost:8792")).toBe(false);
  });

  it("returns false when a query string is present", () => {
    expect(validateGatewayUrl("http://localhost:8792?foo=bar")).toBe(false);
  });

  it("returns false when a hash fragment is present", () => {
    expect(validateGatewayUrl("http://localhost:8792#section")).toBe(false);
  });

  it("returns false when a path is present", () => {
    expect(validateGatewayUrl("http://localhost:8792/proxy")).toBe(false);
  });

  it("returns false for a non-loopback hostname", () => {
    expect(validateGatewayUrl("http://example.com:8792")).toBe(false);
  });

  it("returns false for 0.0.0.0 (not loopback)", () => {
    expect(validateGatewayUrl("http://0.0.0.0:8792")).toBe(false);
  });

  it("returns false for a public IP", () => {
    expect(validateGatewayUrl("http://192.168.1.1:8792")).toBe(false);
  });

  it("returns true for http://localhost with a port", () => {
    expect(validateGatewayUrl("http://localhost:8792")).toBe(true);
  });

  it("returns true for http://localhost without a port", () => {
    expect(validateGatewayUrl("http://localhost")).toBe(true);
  });

  it("returns true for http://127.0.0.1 with a port", () => {
    expect(validateGatewayUrl("http://127.0.0.1:8792")).toBe(true);
  });

  it("returns true for http://[::1] with a port (IPv6 loopback)", () => {
    expect(validateGatewayUrl("http://[::1]:8792")).toBe(true);
  });

  it("accepts a trailing slash in the path (allowed by URL spec)", () => {
    // A path slash is not a query or hash; the validator should accept it.
    expect(validateGatewayUrl("http://localhost:8792/")).toBe(true);
  });
});

// ─── resolveGatewayState ───────────────────────────────────────────────────

describe("resolveGatewayState", () => {
  it('returns { available: false, reason: "unset" } when env var is not set', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "");
    const state = resolveGatewayState("localhost");
    expect(state).toEqual({ available: false, reason: "unset" });
  });

  it('returns { available: false, reason: "unset" } when env var is whitespace only', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "   ");
    const state = resolveGatewayState("localhost");
    expect(state).toEqual({ available: false, reason: "unset" });
  });

  it('returns { available: false, reason: "unsafe" } for an HTTPS URL', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "https://localhost:8792");
    const state = resolveGatewayState("localhost");
    expect(state).toEqual({ available: false, reason: "unsafe" });
  });

  it('returns { available: false, reason: "unsafe" } for a non-loopback gateway URL', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://example.com:8792");
    const state = resolveGatewayState("localhost");
    expect(state).toEqual({ available: false, reason: "unsafe" });
  });

  it('returns { available: false, reason: "nonlocal-page" } when the page is not on loopback', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const state = resolveGatewayState("digiquant.io");
    expect(state).toEqual({ available: false, reason: "nonlocal-page" });
  });

  it('returns { available: false, reason: "nonlocal-page" } when pageHostname is 0.0.0.0', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const state = resolveGatewayState("0.0.0.0");
    expect(state).toEqual({ available: false, reason: "nonlocal-page" });
  });

  it("returns available=true with trimmed baseUrl for a valid URL and localhost page", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const state = resolveGatewayState("localhost");
    expect(state).toEqual({ available: true, baseUrl: "http://127.0.0.1:8792" });
  });

  it("returns available=true for a 127.0.0.1 page hostname", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://localhost:8792");
    const state = resolveGatewayState("127.0.0.1");
    expect(state).toEqual({ available: true, baseUrl: "http://localhost:8792" });
  });

  it("returns available=true for a ::1 page hostname (IPv6 loopback)", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://localhost:8792");
    const state = resolveGatewayState("::1");
    expect(state).toEqual({ available: true, baseUrl: "http://localhost:8792" });
  });

  it("strips a trailing slash from the env var before returning baseUrl", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://localhost:8792/");
    const state = resolveGatewayState("localhost");
    expect(state).toEqual({ available: true, baseUrl: "http://localhost:8792" });
  });

  it('returns "nonlocal-page" when no pageHostname is passed and window is not defined (node/SSR)', () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://localhost:8792");
    // No pageHostname argument — in node, window is not defined → nonlocal-page
    const state = resolveGatewayState();
    expect(state).toEqual({ available: false, reason: "nonlocal-page" });
  });
});

// ─── fetchHealthz ──────────────────────────────────────────────────────────

describe("fetchHealthz", () => {
  it("returns { ok: false, error: 'unset' } when the env var is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "");
    const result = await fetchHealthz("localhost");
    expect(result).toEqual({ ok: false, error: "unset" });
  });

  it("returns { ok: false, error: 'unsafe' } when the URL is unsafe", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "https://localhost:8792");
    const result = await fetchHealthz("localhost");
    expect(result).toEqual({ ok: false, error: "unsafe" });
  });

  it("returns { ok: false, error: 'nonlocal-page' } for a public-page hostname", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://localhost:8792");
    const result = await fetchHealthz("digiquant.io");
    expect(result).toEqual({ ok: false, error: "nonlocal-page" });
  });

  it("returns { ok: true } when /healthz responds 200", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(url);
        return { ok: true, status: 200, json: async () => ({ ok: true }) };
      }),
    );
    const result = await fetchHealthz("localhost");
    expect(result).toEqual({ ok: true });
    expect(urls[0]).toBe("http://127.0.0.1:8792/healthz");
  });

  it("rejects a 200 response that is not the gateway health shape", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: false }) })),
    );
    expect(await fetchHealthz("localhost")).toEqual({
      ok: false,
      error: "unexpected health response",
    });
  });

  it("returns { ok: false, error } on a non-200 response", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })),
    );
    const result = await fetchHealthz("localhost");
    expect(result).toMatchObject({ ok: false });
    expect((result as { ok: false; error: string }).error).toMatch(/503/);
  });

  it("returns { ok: false, error } on a network failure without throwing", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );
    const result = await fetchHealthz("localhost");
    expect(result).toMatchObject({ ok: false });
    expect((result as { ok: false; error: string }).error).toContain("network down");
  });
});

// ─── fetchLuxalgoSearch ────────────────────────────────────────────────────

describe("fetchLuxalgoSearch", () => {
  it("returns { ok: false, error: 'unset' } when env var is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "");
    const result = await fetchLuxalgoSearch("SPY", 10, "localhost");
    expect(result).toEqual({ ok: false, error: "unset" });
  });

  it("returns { ok: false, error: 'nonlocal-page' } for a public-page hostname", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://localhost:8792");
    const result = await fetchLuxalgoSearch("SPY", 10, "digiquant.io");
    expect(result).toEqual({ ok: false, error: "nonlocal-page" });
  });

  it("builds the correct URL with query and limit params", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const urls: string[] = [];
    const envelope: ProbeEnvelope = {
      id: "luxalgoSearch",
      tool: "luxalgo_search",
      args: {},
      ok: true,
      latencyMs: 42,
      cached: false,
      fetchedAt: "2026-09-30T00:00:00Z",
      attribution: ["LuxAlgo"],
      delayNote: null,
      empty: null,
      data: { results: [] },
      error: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(url);
        return { ok: true, status: 200, json: async () => envelope };
      }),
    );
    await fetchLuxalgoSearch("SPY momentum", 5, "127.0.0.1");
    expect(urls[0]).toBe(
      "http://127.0.0.1:8792/v1/probe/luxalgoSearch?query=SPY+momentum&limit=5",
    );
  });

  it("returns { ok: true, envelope } on a successful probe", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const envelope: ProbeEnvelope = {
      id: "luxalgoSearch",
      tool: "luxalgo_search",
      args: { query: "SPY", limit: 10 },
      ok: true,
      latencyMs: 30,
      cached: false,
      fetchedAt: "2026-09-30T00:00:00Z",
      attribution: ["LuxAlgo — free tier"],
      delayNote: "delayed 15 min",
      empty: null,
      data: { results: [{ name: "SPY Indicator" }] },
      error: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => envelope })),
    );
    const result = await fetchLuxalgoSearch("SPY", 10, "localhost");
    expect(result).toEqual({ ok: true, envelope });
  });

  it("returns { ok: false, error } when the probe envelope has ok: false", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const envelope: ProbeEnvelope = {
      id: "luxalgoSearch",
      tool: "luxalgo_search",
      args: {},
      ok: false,
      latencyMs: 10,
      cached: false,
      fetchedAt: "2026-09-30T00:00:00Z",
      attribution: [],
      delayNote: null,
      empty: null,
      data: null,
      error: { code: "upstream_error", message: "tool timed out" },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => envelope })),
    );
    const result = await fetchLuxalgoSearch("SPY", 10, "localhost");
    expect(result).toMatchObject({ ok: false, error: "tool timed out" });
  });

  it("returns { ok: false, error } with a fallback message when probe error is null", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    const envelope: ProbeEnvelope = {
      id: "luxalgoSearch",
      tool: null,
      args: {},
      ok: false,
      latencyMs: 0,
      cached: false,
      fetchedAt: "2026-09-30T00:00:00Z",
      attribution: [],
      delayNote: null,
      empty: null,
      data: null,
      error: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => envelope })),
    );
    const result = await fetchLuxalgoSearch("SPY", 10, "localhost");
    expect(result).toMatchObject({ ok: false });
    expect((result as { ok: false; error: string }).error).toBeTruthy();
  });

  it("returns { ok: false, error } on HTTP non-200 without throwing", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 502, json: async () => ({}) })),
    );
    const result = await fetchLuxalgoSearch("SPY", 10, "localhost");
    expect(result).toMatchObject({ ok: false });
    expect((result as { ok: false; error: string }).error).toMatch(/502/);
  });

  it("returns { ok: false, error } on a network failure without throwing", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL", "http://127.0.0.1:8792");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connection refused");
      }),
    );
    const result = await fetchLuxalgoSearch("SPY", 10, "localhost");
    expect(result).toMatchObject({ ok: false });
    expect((result as { ok: false; error: string }).error).toContain("connection refused");
  });
});
