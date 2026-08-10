import { describe, expect, it } from "vitest";
import { shouldProxyToDigiChat } from "./paths";

describe("shouldProxyToDigiChat", () => {
  it("proxies embed and digichat API paths", () => {
    expect(shouldProxyToDigiChat("/embed")).toBe(true);
    expect(shouldProxyToDigiChat("/embed/")).toBe(true);
    expect(shouldProxyToDigiChat("/api/chat")).toBe(true);
    expect(shouldProxyToDigiChat("/api/chat/stream")).toBe(true);
    expect(shouldProxyToDigiChat("/api/embed/tenant-config")).toBe(true);
    expect(shouldProxyToDigiChat("/api/byok/test")).toBe(true);
    expect(shouldProxyToDigiChat("/api/health")).toBe(true);
    expect(shouldProxyToDigiChat("/_dtchat/_next/static/x.js")).toBe(true);
  });

  it("leaves Pages marketing and chat shells alone", () => {
    expect(shouldProxyToDigiChat("/")).toBe(false);
    expect(shouldProxyToDigiChat("/chat")).toBe(false);
    expect(shouldProxyToDigiChat("/chat/occ")).toBe(false);
    expect(shouldProxyToDigiChat("/docs")).toBe(false);
    expect(shouldProxyToDigiChat("/_next/static/x.js")).toBe(false);
  });
});
