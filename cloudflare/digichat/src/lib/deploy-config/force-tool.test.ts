import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG } from "./client-projection";
import {
  allowedForceTools,
  filterDisabledToolsHeader,
  filterForceToolHeader,
  omitForcedCatalogIds,
} from "./force-tool";
import type { DigichatDeployment } from "./schema";

const dep = {
  slug: "embed",
  tools: {
    allowUserToggle: true,
    catalog: [
      { id: "digisearch", default: true },
      { id: "digivault", default: true },
      { id: "web_search", default: true },
    ],
  },
} as DigichatDeployment;

describe("filterDisabledToolsHeader", () => {
  it("allowlists catalog search/vault and drops unknown tokens", () => {
    expect(filterDisabledToolsHeader(dep, "digisearch,digivault,web_search,rm -rf")).toEqual([
      "digisearch",
      "digivault",
    ]);
  });

  it("maps aliases and ignores empty input", () => {
    expect(filterDisabledToolsHeader(dep, "search, vault")).toEqual(["digisearch", "digivault"]);
    expect(filterDisabledToolsHeader(dep, "")).toEqual([]);
    // Fail-closed (#3806): empty catalog denies builtins.
    expect(filterDisabledToolsHeader(null, "digisearch")).toEqual([]);
    expect(filterDisabledToolsHeader(null, "rm -rf")).toEqual([]);
  });

  it("forwards catalog ids unexpanded — digigraph expands them upstream (#3807)", () => {
    expect(filterDisabledToolsHeader(dep, "digisearch")).toEqual(["digisearch"]);
    expect(filterDisabledToolsHeader(dep, "digivault")).toEqual(["digivault"]);
  });

  it("denies force-tools on an empty catalog but still allows MCP ids (#3806)", () => {
    expect(filterForceToolHeader(null, "digisearch")).toBeUndefined();
    expect(filterForceToolHeader(null, "digivault")).toBeUndefined();
    expect(allowedForceTools(null)).toEqual([]);
    const mcpOnly = {
      slug: "mcp-only",
      mcp: { servers: [{ id: "datatap", url: "https://mcp.datatap.example/mcp" }] },
    } as DigichatDeployment;
    expect(filterForceToolHeader(mcpOnly, "digisearch")).toBeUndefined();
    expect(filterForceToolHeader(mcpOnly, "datatap")).toBe("datatap");
    expect(allowedForceTools(mcpOnly)).toEqual(["datatap"]);
    expect(filterDisabledToolsHeader(mcpOnly, "digisearch,datatap")).toEqual(["datatap"]);
  });
});

describe("filterForceToolHeader", () => {
  it("forwards catalog force-tools only", () => {
    expect(filterForceToolHeader(dep, "digisearch")).toBe("digisearch");
    expect(filterForceToolHeader(dep, "digivault")).toBe("digivault");
    expect(filterForceToolHeader(dep, "not-a-tool")).toBeUndefined();
  });

  it("allowlists extra operator MCP ids", () => {
    const mcpDep = {
      ...dep,
      mcp: { servers: [{ id: "datatap", url: "https://mcp.datatap.example/mcp" }] },
    } as DigichatDeployment;
    expect(filterForceToolHeader(mcpDep, "datatap")).toBe("datatap");
    expect(filterDisabledToolsHeader(mcpDep, "datatap,evil")).toEqual(["datatap"]);
    expect(omitForcedCatalogIds(["datatap", "digisearch"], "datatap")).toEqual(["digisearch"]);
  });
});

describe("omitForcedCatalogIds", () => {
  it("keeps a forced catalog id out of the disabled list", () => {
    expect(omitForcedCatalogIds(["digisearch", "digivault"], "digisearch")).toEqual([
      "digivault",
    ]);
  });
});

void DEFAULT_CLIENT_CONFIG;
