import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { describe, expect, it } from "vitest";
import { toDigichatClientConfig } from "./deploy-config/client-projection";
import { parseDigichatConfig } from "./deploy-config/schema";
import { toolControlFor } from "./tool-control";

function clientFrom(rel: string, host?: string) {
  const raw = readFileSync(resolve(__dirname, "../../config", rel), "utf8");
  const cfg = parseDigichatConfig(loadYaml(raw), rel);
  const dep = host ? cfg.hosts?.[host] : cfg.deployment;
  if (!dep) throw new Error(`missing deployment in ${rel}`);
  return toDigichatClientConfig(dep);
}

describe("toolControlFor", () => {
  it("treats a foundry host as agent-owned even when toggling is allowed", () => {
    expect(
      toolControlFor({ backendType: "foundry", allowUserToggle: true, lockSessionControls: true }),
    ).toBe("agent");
    const client = clientFrom("datatap-trial-foundry.yaml");
    expect(client.backendType).toBe("foundry");
    expect(client.tools.allowUserToggle).toBe(false);
    expect(client.tools.catalog.map((tool) => tool.id)).toEqual(["file_search", "datatap"]);
    expect(client.tools.catalog.find((tool) => tool.id === "datatap")?.tools?.map((tool) => tool.id)).toEqual([
      "datatap__list_connections",
      "datatap__get_item",
    ]);
    expect(
      toolControlFor({
        backendType: client.backendType,
        allowUserToggle: client.tools.allowUserToggle,
        lockSessionControls: client.gate.lockSessionControls,
      }),
    ).toBe("agent");
  });

  it("locks OCC tools and still projects the MCP list", () => {
    const client = clientFrom("examples/occ-embed.yaml", "occ.digithings.ai");
    expect(client.gate.lockSessionControls).toBe(true);
    expect(client.mcp.servers.map((server) => server.id)).toEqual([
      "zammad",
      "digisearch",
      "digivault",
    ]);
    expect(
      toolControlFor({
        backendType: client.backendType,
        allowUserToggle: client.tools.allowUserToggle,
        lockSessionControls: client.gate.lockSessionControls,
      }),
    ).toBe("locked");
  });

  it("locks when the host disallows toggles and toggles otherwise", () => {
    expect(toolControlFor({ allowUserToggle: false })).toBe("locked");
    expect(toolControlFor({ backendType: "digigraph", allowUserToggle: true })).toBe("toggle");
  });
});
