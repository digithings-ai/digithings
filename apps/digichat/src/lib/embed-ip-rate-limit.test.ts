import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_MAX as SHARED_BUCKET_MAX } from "@/lib/bff-rate-limit";
import {
  checkEmbedIpRateLimit,
  clientIpForRateLimit,
  EMBED_IP_MAX,
} from "@/lib/embed-ip-rate-limit";
import { MemoryGuardrailStore } from "@/lib/guardrails/store";
import { createTurnGuard } from "@/lib/guardrails/turn";

function reqWithHeaders(headers: Record<string, string>): Request {
  return new Request("http://localhost/api/chat", { headers });
}

describe("clientIpForRateLimit", () => {
  afterEach(() => {
    delete process.env.DIGICHAT_TRUSTED_PROXIES;
  });

  it("ignores forwarded headers when no trusted proxy is configured", () => {
    const req = reqWithHeaders({
      "cf-connecting-ip": "198.51.100.1",
      "x-forwarded-for": "203.0.113.9",
      "x-digichat-peer-ip": "192.0.2.10",
    });
    expect(clientIpForRateLimit(req)).toBe("192.0.2.10");
  });

  it("returns 'unknown' when no socket address was captured", () => {
    expect(
      clientIpForRateLimit(
        reqWithHeaders({ "cf-connecting-ip": "198.51.100.1", "x-forwarded-for": "203.0.113.9" }),
      ),
    ).toBe("unknown");
  });

  it("keeps rotating X-Forwarded-For values in one bucket", () => {
    const store = new MemoryGuardrailStore();
    const spend = (xff: string) => {
      const ip = clientIpForRateLimit(
        reqWithHeaders({
          "x-forwarded-for": xff,
          "cf-connecting-ip": xff.split(",")[0]?.trim() ?? "",
          "x-digichat-peer-ip": "203.0.113.7",
        }),
      );
      const guard = createTurnGuard({
        slug: "public",
        guardrails: { tokensPerMinute: { user: 1000 } },
        userId: "embed:anonymous",
        ip,
        store,
        now: () => 1_000,
      });
      guard.recordUsage({ totalTokens: 10 });
      return ip;
    };
    expect(spend("198.51.100.1")).toBe("203.0.113.7");
    expect(spend("198.51.100.2, 10.0.0.1")).toBe("203.0.113.7");
    expect(store.bucketCount()).toBe(1);
    expect(store.read("tpm:user:public:203.0.113.7", 1_000).events).toHaveLength(2);
    expect(store.read("tpm:user:public:198.51.100.1", 1_000).events).toHaveLength(0);
    expect(store.read("tpm:user:public:198.51.100.2", 1_000).events).toHaveLength(0);
  });

  it("ignores forwarded client headers from an untrusted socket peer", () => {
    process.env.DIGICHAT_TRUSTED_PROXIES = "10.0.0.8/29";
    const req = reqWithHeaders({
      "cf-connecting-ip": "198.51.100.1",
      "x-forwarded-for": "198.51.100.2, 10.0.0.1",
      "x-digichat-peer-ip": "203.0.113.7",
    });

    expect(clientIpForRateLimit(req)).toBe("203.0.113.7");
  });

  it("honors Cloudflare's client header from a trusted socket peer", () => {
    process.env.DIGICHAT_TRUSTED_PROXIES = "10.0.0.8/29";
    const req = reqWithHeaders({
      "cf-connecting-ip": "198.51.100.1",
      "x-digichat-peer-ip": "10.0.0.9",
    });

    expect(clientIpForRateLimit(req)).toBe("198.51.100.1");
  });

  it("walks trusted X-Forwarded-For hops from the right", () => {
    process.env.DIGICHAT_TRUSTED_PROXIES = "10.0.0.1, 10.0.0.2";
    const req = reqWithHeaders({
      "x-forwarded-for": "198.51.100.9, 10.0.0.1",
      "x-digichat-peer-ip": "10.0.0.2",
    });

    expect(clientIpForRateLimit(req)).toBe("198.51.100.9");
  });

  it("falls back to the direct peer at a malformed forwarded boundary", () => {
    process.env.DIGICHAT_TRUSTED_PROXIES = "10.0.0.1";
    const req = reqWithHeaders({
      "x-forwarded-for": "198.51.100.9, not-an-ip",
      "x-digichat-peer-ip": "10.0.0.1",
    });

    expect(clientIpForRateLimit(req)).toBe("10.0.0.1");
  });

  it("fails safe when trusted-proxy configuration has no valid networks", () => {
    process.env.DIGICHAT_TRUSTED_PROXIES = "not-an-ip";
    const req = reqWithHeaders({
      "cf-connecting-ip": "198.51.100.1",
      "x-digichat-peer-ip": "203.0.113.7",
    });

    expect(clientIpForRateLimit(req)).toBe("203.0.113.7");
  });

  it("rejects a trusted-proxy CIDR with an empty prefix", () => {
    process.env.DIGICHAT_TRUSTED_PROXIES = "10.0.0.1/";
    const req = reqWithHeaders({
      "cf-connecting-ip": "198.51.100.1",
      "x-digichat-peer-ip": "203.0.113.7",
    });

    expect(clientIpForRateLimit(req)).toBe("203.0.113.7");
  });
});

describe("checkEmbedIpRateLimit", () => {
  it("blocks one IP after its limit without affecting another IP", () => {
    // DIGICHAT_EMBED_IP_RATE_LIMIT_MAX is read once at module import time, so
    // this exercises the real default (EMBED_IP_MAX) rather than overriding it.
    const ipA = `198.51.100.${Date.now() % 200}`;
    const ipB = `198.51.100.${(Date.now() % 200) + 1}`;
    const reqA = reqWithHeaders({ "x-digichat-peer-ip": ipA });
    const reqB = reqWithHeaders({ "x-digichat-peer-ip": ipB });

    for (let i = 0; i < EMBED_IP_MAX; i++) {
      expect(checkEmbedIpRateLimit(reqA).allowed).toBe(true);
    }
    const blockedA = checkEmbedIpRateLimit(reqA);
    const allowedB = checkEmbedIpRateLimit(reqB);

    expect(blockedA.allowed).toBe(false);
    expect(allowedB.allowed).toBe(true);
  });

  it("keeps the per-IP default below the shared bucket default (regression: caught in review, #1251)", () => {
    // If EMBED_IP_MAX >= SHARED_BUCKET_MAX, a single visitor hits the *shared*
    // embed:anonymous bucket's ceiling before ever tripping this per-IP one —
    // the per-IP layer becomes a no-op and the abuse #1251 exists to prevent
    // (one visitor exhausting the shared quota) still happens. The first cut
    // of this file shipped EMBED_IP_MAX=60 against a shared default of 30.
    expect(EMBED_IP_MAX).toBeLessThan(SHARED_BUCKET_MAX);
  });
});
