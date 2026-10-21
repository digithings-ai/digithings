import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_MAX as SHARED_BUCKET_MAX } from "@/lib/bff-rate-limit";
import {
  checkEmbedIpRateLimit,
  clientIpForEmbedLimit,
  clientIpForRateLimit,
  EMBED_IP_MAX,
  TRUSTED_PROXIES_UNSET_WARNING,
  warnTrustedProxiesUnset,
} from "@/lib/embed-ip-rate-limit";
import { MemoryGuardrailStore } from "@/lib/guardrails/store";
import { createTurnGuard } from "@/lib/guardrails/turn";
import { trustedProxiesUnsetWarning } from "../../scripts/trusted-proxy-server.mjs";

const STAMP = "test-stamp";

function stamped(peer: string, extra: Record<string, string> = {}): Request {
  return reqWithHeaders({
    "x-digichat-peer-ip": peer,
    "x-digichat-peer-stamp": STAMP,
    ...extra,
  });
}

function reqWithHeaders(headers: Record<string, string>): Request {
  return new Request("http://localhost/api/chat", { headers });
}

describe("clientIpForRateLimit", () => {
  afterEach(() => {
    delete process.env.DIGICHAT_TRUSTED_PROXIES;
    delete process.env.DIGICHAT_PEER_STAMP;
  });

  it("ignores a caller-supplied peer header when no trusted proxy is configured", () => {
    const req = reqWithHeaders({
      "cf-connecting-ip": "198.51.100.1",
      "x-forwarded-for": "203.0.113.9",
      "x-digichat-peer-ip": "192.0.2.10",
    });
    expect(clientIpForRateLimit(req)).toBe("unknown");
  });

  it("returns 'unknown' when no socket address was captured", () => {
    expect(
      clientIpForRateLimit(
        reqWithHeaders({ "cf-connecting-ip": "198.51.100.1", "x-forwarded-for": "203.0.113.9" }),
      ),
    ).toBe("unknown");
  });

  it("keeps rotating caller-supplied peer headers in one guardrail bucket", () => {
    const store = new MemoryGuardrailStore();
    const spend = (peer: string) => {
      const ip = clientIpForRateLimit(
        reqWithHeaders({
          "x-digichat-peer-ip": peer,
          "x-forwarded-for": peer,
          "cf-connecting-ip": peer,
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
    expect(spend("198.51.100.1")).toBe("unknown");
    expect(spend("198.51.100.2")).toBe("unknown");
    expect(store.bucketCount()).toBe(1);
    expect(store.read("tpm:user:public:anonymous", 1_000).events).toHaveLength(2);
    expect(store.read("tpm:user:public:198.51.100.1", 1_000).events).toHaveLength(0);
  });

  it("uses a stamped socket as the client and ignores rotating forwarded headers", () => {
    process.env.DIGICHAT_PEER_STAMP = STAMP;
    const store = new MemoryGuardrailStore();
    const spend = (xff: string) => {
      const ip = clientIpForRateLimit(
        stamped("203.0.113.7", { "x-forwarded-for": xff, "cf-connecting-ip": "203.0.113.7" }),
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

  it("does not let a shared ingress decide a guardrail key", () => {
    process.env.DIGICHAT_PEER_STAMP = STAMP;
    const store = new MemoryGuardrailStore();
    for (const visitor of ["198.51.100.1", "198.51.100.2"]) {
      const ip = clientIpForRateLimit(
        stamped("10.0.0.9", { "cf-connecting-ip": visitor, "x-forwarded-for": visitor }),
      );
      expect(ip).toBe("unknown");
      createTurnGuard({
        slug: "public",
        guardrails: { tokensPerMinute: { user: 1000 } },
        userId: "embed:anonymous",
        ip,
        store,
        now: () => 1_000,
      }).recordUsage({ totalTokens: 10 });
      expect(clientIpForEmbedLimit(stamped("10.0.0.9", { "cf-connecting-ip": visitor }))).toBe(
        visitor,
      );
    }
    expect(store.bucketCount()).toBe(1);
    expect(store.read("tpm:user:public:anonymous", 1_000).events).toHaveLength(2);
  });

  it("logs the unset trusted-proxy warning and matches the entrypoint sentence", () => {
    expect(TRUSTED_PROXIES_UNSET_WARNING).toBe(trustedProxiesUnsetWarning);
    expect(TRUSTED_PROXIES_UNSET_WARNING).toContain("never Cloudflare's edge ranges");
    const lines: string[] = [];
    delete process.env.DIGICHAT_TRUSTED_PROXIES;
    warnTrustedProxiesUnset(process.env, (message) => lines.push(message));
    process.env.DIGICHAT_TRUSTED_PROXIES = "10.0.0.1";
    warnTrustedProxiesUnset(process.env, (message) => lines.push(message));
    expect(lines).toEqual([TRUSTED_PROXIES_UNSET_WARNING]);
  });
});

describe("checkEmbedIpRateLimit", () => {
  afterEach(() => {
    delete process.env.DIGICHAT_PEER_STAMP;
    delete process.env.DIGICHAT_TRUSTED_PROXIES;
  });

  it("blocks one IP after its limit without affecting another IP", () => {
    // DIGICHAT_EMBED_IP_RATE_LIMIT_MAX is read once at module import time, so
    // this exercises the real default (EMBED_IP_MAX) rather than overriding it.
    // No stamp and no allowlist: develop's cf-connecting-ip still splits visitors.
    const n = Date.now() % 150;
    const ipA = `192.0.2.${n + 1}`;
    const ipB = `192.0.2.${n + 51}`;
    const reqA = reqWithHeaders({ "cf-connecting-ip": ipA });
    const reqB = reqWithHeaders({ "cf-connecting-ip": ipB });

    for (let i = 0; i < EMBED_IP_MAX; i++) {
      expect(checkEmbedIpRateLimit(reqA).allowed).toBe(true);
    }
    const blockedA = checkEmbedIpRateLimit(reqA);
    const allowedB = checkEmbedIpRateLimit(reqB);

    expect(blockedA.allowed).toBe(false);
    expect(allowedB.allowed).toBe(true);
    expect(clientIpForRateLimit(reqA)).toBe("unknown");
    expect(clientIpForRateLimit(reqB)).toBe("unknown");
  });

  it("keeps a shared ingress on separate embed buckets and does not fail the trial key open", () => {
    process.env.DIGICHAT_PEER_STAMP = STAMP;
    const ingress = "10.0.0.9";
    const ipA = "198.51.100.41";
    const ipB = "198.51.100.42";
    const reqA = stamped(ingress, { "cf-connecting-ip": ipA });
    const reqB = stamped(ingress, { "cf-connecting-ip": ipB });
    expect(clientIpForRateLimit(reqA)).toBe("unknown");
    expect(clientIpForEmbedLimit(reqA)).toBe(ipA);
    expect(clientIpForEmbedLimit(reqB)).toBe(ipB);
    for (let i = 0; i < EMBED_IP_MAX; i++) {
      expect(checkEmbedIpRateLimit(reqA).allowed).toBe(true);
    }
    expect(checkEmbedIpRateLimit(reqA).allowed).toBe(false);
    expect(checkEmbedIpRateLimit(reqB).allowed).toBe(true);
  });

  it("counts stamped direct sockets separately", () => {
    process.env.DIGICHAT_PEER_STAMP = STAMP;
    const reqA = stamped("203.0.113.21");
    const reqB = stamped("203.0.113.22");
    expect(clientIpForRateLimit(reqA)).toBe("203.0.113.21");
    for (let i = 0; i < EMBED_IP_MAX; i++) {
      expect(checkEmbedIpRateLimit(reqA).allowed).toBe(true);
    }
    expect(checkEmbedIpRateLimit(reqA).allowed).toBe(false);
    expect(checkEmbedIpRateLimit(reqB).allowed).toBe(true);
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
