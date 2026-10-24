import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { describe, expect, it } from "vitest";
import { toDigichatClientConfig } from "./deploy-config/client-projection";
import { expandDigichatDocument } from "./deploy-config/loader";
import { parseDigichatConfig } from "./deploy-config/schema";
import { toolControlFor } from "./tool-control";

function clientFrom(rel: string, host?: string) {
  const raw = readFileSync(resolve(__dirname, "../../config", rel), "utf8");
  const cfg = parseDigichatConfig(expandDigichatDocument(loadYaml(raw)), rel);
  const dep = host ? cfg.hosts?.[host] : cfg.deployment;
  if (!dep) throw new Error(`missing deployment in ${rel}`);
  return toDigichatClientConfig(dep);
}

function foundryClient() {
  const dir = resolve(__dirname, "../../config");
  for (const name of readdirSync(dir)) {
    if (!name.endsWith(".yaml")) continue;
    const client = clientFrom(name);
    if (client.backendType === "foundry") return client;
  }
  throw new Error("no foundry deployment");
}

describe("toolControlFor", () => {
  it("treats a foundry host as agent-owned even when toggling is allowed", () => {
    expect(
      toolControlFor({ backendType: "foundry", allowUserToggle: true, lockSessionControls: true }),
    ).toBe("agent");
    const client = foundryClient();
    expect(client.backendType).toBe("foundry");
    expect(client.tools.allowUserToggle).toBe(false);
    expect(client.tools.catalog).toHaveLength(1);
    const tools = client.tools.catalog[0]?.tools ?? [];
    expect(tools).toHaveLength(42);
    expect(new Set(tools.map((tool) => tool.id)).size).toBe(42);
    expect(tools.every((tool) => tool.group && tool.label)).toBe(true);
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
    const ids = client.mcp.servers.map((server) => server.id);
    expect(ids).toHaveLength(3);
    expect(ids).toContain("digisearch");
    expect(ids).toContain("digivault");
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
