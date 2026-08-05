import { describe, it, expect } from "vitest";
import {
  checkDigivaultIpRateLimit,
  DIGIVAULT_IP_RATE_LIMIT_MAX,
} from "./digivault-ip-rate-limit";

describe("checkDigivaultIpRateLimit", () => {
  it("allows up to 60 requests per IP per window", () => {
    const ip = `203.0.113.${Math.floor(Math.random() * 200)}`;
    for (let i = 0; i < DIGIVAULT_IP_RATE_LIMIT_MAX; i++) {
      expect(checkDigivaultIpRateLimit(ip).allowed).toBe(true);
    }
    const blocked = checkDigivaultIpRateLimit(ip);
    expect(blocked.allowed).toBe(false);
    if (!blocked.allowed) expect(blocked.retryAfterSec).toBeGreaterThan(0);
  });
});
