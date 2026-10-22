import { describe, expect, it } from "vitest";
import {
  CONTAINER_BASE_PATH,
  containerPathFor,
  shouldProxyToDigiChat,
  withContainerPath,
} from "./paths";

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

  it("does not claim a path that merely starts with the same letters", () => {
    // "/chatfoo" is not under the base path: a prefix match on the string
    // "/chat" alone would claim it and hand it to the container.
    expect(shouldProxyToDigiChat("/chatfoo")).toBe(false);
    expect(shouldProxyToDigiChat("/chatfoo/bar")).toBe(false);
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
    expect(CONTAINER_BASE_PATH).toBe("/chat");
    expect(containerPathFor(CONTAINER_BASE_PATH)).toBe(CONTAINER_BASE_PATH);
  });
});

describe("withContainerPath", () => {
  it("moves the path onto the base path and keeps everything else", async () => {
    const request = new Request("https://digithings.ai/embed?host=occ.digithings.ai", {
      method: "POST",
      headers: { "x-embed-host": "occ.digithings.ai", "content-type": "application/json" },
      body: JSON.stringify({ mode: "embed" }),
    });
    const mapped = withContainerPath(request, "/embed");
    const url = new URL(mapped.url);
    expect(url.pathname).toBe("/chat/embed");
    expect(url.search).toBe("?host=occ.digithings.ai");
    expect(mapped.method).toBe("POST");
    expect(mapped.headers.get("x-embed-host")).toBe("occ.digithings.ai");
    expect(await mapped.text()).toBe(JSON.stringify({ mode: "embed" }));
  });

  it("leaves a path that is already under the base path alone", () => {
    const request = new Request("https://digithings.ai/chat/api/chat?x=1");
    const mapped = withContainerPath(request, "/chat/api/chat");
    expect(new URL(mapped.url).pathname).toBe("/chat/api/chat");
    expect(new URL(mapped.url).search).toBe("?x=1");
  });

  it("keeps the asset prefix and the container-local MCP prefix where they are", () => {
    const assets = withContainerPath(
      new Request("https://digithings.ai/_dtchat/_next/static/x.js"),
      "/_dtchat/_next/static/x.js",
    );
    expect(new URL(assets.url).pathname).toBe("/_dtchat/_next/static/x.js");
    const mcp = withContainerPath(
      new Request("https://digithings.ai/api/mcp/zammad/tickets"),
      "/api/mcp/zammad/tickets",
    );
    expect(new URL(mcp.url).pathname).toBe("/api/mcp/zammad/tickets");
  });
});
