import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  EMBED_MONITOR_TOKEN_HEADER,
  MIN_MONITOR_TOKEN_LENGTH,
  isAllowlistedMonitorToken,
} from "@/lib/embed-monitor-token";

const SECRET = "monitor-secret-0123456789abcdef0123456789abcdef";

describe("isAllowlistedMonitorToken", () => {
  beforeEach(() => {
    process.env.DIGICHAT_MONITOR_TOKENS = SECRET;
  });

  afterEach(() => {
    delete process.env.DIGICHAT_MONITOR_TOKENS;
  });

  it("uses a header name that is neither the published embed token nor the chat token", () => {
    // The tenant token (X-Embed-Token) is a Stripe-style publishable key: it is
    // rendered into the embedding page by design (DIG-619), so a bypass keyed
    // on it would be a public bypass. The chat token belongs to the consumeUrl
    // path. The monitor must have a header of its own.
    expect(EMBED_MONITOR_TOKEN_HEADER).toBe("x-embed-monitor-token");
    expect(EMBED_MONITOR_TOKEN_HEADER).not.toBe("x-embed-token");
    expect(EMBED_MONITOR_TOKEN_HEADER).not.toBe("x-embed-chat-token");
  });

  it("accepts the exact secret", () => {
    expect(isAllowlistedMonitorToken(SECRET)).toBe(true);
  });

  it("fails open when no allowlist is configured, so the gate behaves exactly as before", () => {
    delete process.env.DIGICHAT_MONITOR_TOKENS;
    expect(isAllowlistedMonitorToken(SECRET)).toBe(false);
  });

  it("fails open when the allowlist is only whitespace", () => {
    process.env.DIGICHAT_MONITOR_TOKENS = "   ";
    expect(isAllowlistedMonitorToken(SECRET)).toBe(false);
  });

  it("rejects a missing header", () => {
    expect(isAllowlistedMonitorToken(null)).toBe(false);
    expect(isAllowlistedMonitorToken("")).toBe(false);
    expect(isAllowlistedMonitorToken("   ")).toBe(false);
  });

  it("rejects a wrong secret", () => {
    expect(isAllowlistedMonitorToken(`${SECRET}x`)).toBe(false);
    expect(isAllowlistedMonitorToken(SECRET.slice(0, -1))).toBe(false);
  });

  it("rejects a substring or prefix of the secret rather than matching loosely", () => {
    expect(isAllowlistedMonitorToken(SECRET.slice(0, 12))).toBe(false);
    expect(isAllowlistedMonitorToken(`prefix-${SECRET}`)).toBe(false);
  });

  it("trims whitespace on the presented value and on each allowlist entry", () => {
    process.env.DIGICHAT_MONITOR_TOKENS = `  ${SECRET}  `;
    expect(isAllowlistedMonitorToken(`  ${SECRET}  `)).toBe(true);
    expect(isAllowlistedMonitorToken(SECRET)).toBe(true);
  });

  it("accepts any entry in a comma-separated allowlist, so a rotation can overlap", () => {
    const next = "monitor-secret-fedcba9876543210fedcba9876543210";
    process.env.DIGICHAT_MONITOR_TOKENS = `${SECRET},${next}`;
    expect(isAllowlistedMonitorToken(SECRET)).toBe(true);
    expect(isAllowlistedMonitorToken(next)).toBe(true);
    expect(isAllowlistedMonitorToken("monitor-secret-nope")).toBe(false);
  });

  it("ignores an empty entry in a comma-separated allowlist", () => {
    process.env.DIGICHAT_MONITOR_TOKENS = `,${SECRET},`;
    expect(isAllowlistedMonitorToken(SECRET)).toBe(true);
    expect(isAllowlistedMonitorToken("")).toBe(false);
  });

  it("refuses a configured secret too short to be a secret", () => {
    // A short value would make the bypass guessable. Rather than fail closed
    // and block everyone, such an entry is ignored and the gate keeps its
    // normal behaviour for everyone.
    process.env.DIGICHAT_MONITOR_TOKENS = "short";
    expect(isAllowlistedMonitorToken("short")).toBe(false);
  });

  it("refuses a short presented value even against a valid allowlist", () => {
    expect(isAllowlistedMonitorToken("a".repeat(MIN_MONITOR_TOKEN_LENGTH - 1))).toBe(false);
    expect(isAllowlistedMonitorToken("a".repeat(MIN_MONITOR_TOKEN_LENGTH))).toBe(false);
  });

  it("ignores a too-short entry but still honours a valid sibling entry", () => {
    process.env.DIGICHAT_MONITOR_TOKENS = `short,${SECRET}`;
    expect(isAllowlistedMonitorToken("short")).toBe(false);
    expect(isAllowlistedMonitorToken(SECRET)).toBe(true);
  });
});