import { describe, expect, it } from "vitest";
import { mcpEdgeTarget } from "./mcp-edge-target";

/**
 * The in-container MCP servers (Python `mcp`) guard their transport against
 * DNS rebinding and answer 421 "Invalid Host header" for a Host they cannot
 * allow-list. The SDK allow-lists loopback names only WITH a port, so the edge
 * must not forward the public host it received.
 */
describe("mcpEdgeTarget", () => {
  it("presents a loopback host with the in-container port", () => {
    const target = mcpEdgeTarget(
      new URL("https://search.digithings.ai/_stack/mcp/digisearch/mcp?x=1"),
      "/mcp",
      8765,
    );
    expect(target.hostname).toBe("127.0.0.1");
    expect(target.port).toBe("8765");
    expect(target.host).toBe("127.0.0.1:8765");
  });

  it("never carries the public hostname the request arrived on", () => {
    const target = mcpEdgeTarget(
      new URL("https://graph.digithings.ai/_stack/mcp/digivault/mcp"),
      "/mcp",
      8769,
    );
    expect(target.toString()).not.toContain("digithings.ai");
  });

  it("keeps the client path and query unchanged", () => {
    const target = mcpEdgeTarget(
      new URL("https://search.digithings.ai/_stack/mcp/digisearch/v1/tools?cursor=abc"),
      "/v1/tools",
      8765,
    );
    expect(target.pathname).toBe("/v1/tools");
    expect(target.search).toBe("?cursor=abc");
  });
});
