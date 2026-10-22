import { describe, expect, it } from "vitest";
import { CONTAINER_BASE_PATH, containerPathFor, shouldProxyToDigiChat } from "./paths";

describe("shouldProxyToDigiChat", () => {
  it("proxies embed and digichat API paths", () => {
    expect(shouldProxyToDigiChat("/embed")).toBe(true);
    expect(shouldProxyToDigiChat("/embed/")).toBe(true);
    expect(shouldProxyToDigiChat("/api/chat")).toBe(true);
    expect(shouldProxyToDigiChat("/api/chat/stream")).toBe(true);
    expect(shouldProxyToDigiChat("/api/embed/tenant-config")).toBe(true);
    expect(shouldProxyToDigiChat("/api/byok/test")).toBe(true);
    expect(shouldProxyToDigiChat("/api/plan-proof")).toBe(true);
    expect(shouldProxyToDigiChat("/api/plan-proof/mint")).toBe(true);
    expect(shouldProxyToDigiChat("/api/health")).toBe(true);
    expect(shouldProxyToDigiChat("/healthz")).toBe(true);
    expect(shouldProxyToDigiChat("/_dtchat/_next/static/x.js")).toBe(true);
  });

  it("proxies the canonical /chat surface (DIG-5121)", () => {
    expect(shouldProxyToDigiChat("/chat")).toBe(true);
    expect(shouldProxyToDigiChat("/chat/")).toBe(true);
    expect(shouldProxyToDigiChat("/chat/api/chat")).toBe(true);
    expect(shouldProxyToDigiChat("/chat/_next/static/x.js")).toBe(true);
  });

  it("leaves Pages marketing and the gated OCC shell alone", () => {
    expect(shouldProxyToDigiChat("/")).toBe(false);
    expect(shouldProxyToDigiChat("/chat/occ")).toBe(false);
    expect(shouldProxyToDigiChat("/chat/occ/")).toBe(false);
    expect(shouldProxyToDigiChat("/docs")).toBe(false);
    expect(shouldProxyToDigiChat("/_next/static/x.js")).toBe(false);
  });
});

describe("containerPathFor", () => {
  it("passes a /chat path through unchanged — the base path is never doubled", () => {
    expect(containerPathFor("/chat")).toBe("/chat");
    expect(containerPathFor("/chat/")).toBe("/chat/");
    expect(containerPathFor("/chat/api/chat")).toBe("/chat/api/chat");
    expect(containerPathFor("/chat/_next/static/x.js")).toBe("/chat/_next/static/x.js");
  });

  it("moves the legacy compatibility routes under the base path", () => {
    expect(containerPathFor("/embed")).toBe("/chat/embed");
    expect(containerPathFor("/embed/")).toBe("/chat/embed/");
    expect(containerPathFor("/api/chat")).toBe("/chat/api/chat");
    expect(containerPathFor("/api/chat/stream")).toBe("/chat/api/chat/stream");
    expect(containerPathFor("/api/embed/tenant-config")).toBe("/chat/api/embed/tenant-config");
    expect(containerPathFor("/api/byok/test")).toBe("/chat/api/byok/test");
    expect(containerPathFor("/api/plan-proof")).toBe("/chat/api/plan-proof");
    expect(containerPathFor("/api/plan-proof/mint")).toBe("/chat/api/plan-proof/mint");
    expect(containerPathFor("/api/health")).toBe("/chat/api/health");
    expect(containerPathFor("/healthz")).toBe("/chat/healthz");
  });

  it("leaves the asset prefix and the container-local MCP prefix alone", () => {
    expect(containerPathFor("/_dtchat/_next/static/x.js")).toBe("/_dtchat/_next/static/x.js");
    expect(containerPathFor("/api/mcp/zammad")).toBe("/api/mcp/zammad");
    expect(containerPathFor("/api/mcp/zammad/tickets")).toBe("/api/mcp/zammad/tickets");
  });

  it("is the identity on the base path itself", () => {
    expect(containerPathFor(CONTAINER_BASE_PATH)).toBe(CONTAINER_BASE_PATH);
  });
});
