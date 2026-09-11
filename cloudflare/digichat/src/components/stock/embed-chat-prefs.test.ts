import { describe, expect, it } from "vitest";
import {
  extraOffFromCatalog,
  DEFAULT_EMBED_CHAT_PREFS,
  disabledCatalogIds,
  mcpMenuSummary,
  registeredMcpTools,
} from "./embed-chat-prefs";

describe("disabledCatalogIds", () => {
  it("defaults web search on; the tenant gate still decides whether it sends", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.webSearch).toBe(true);
  });

  it("is empty when search and vault are on", () => {
    expect(disabledCatalogIds(DEFAULT_EMBED_CHAT_PREFS)).toEqual([]);
  });

  it("starts extra MCP tools off when YAML default is false", () => {
    expect(extraOffFromCatalog([{ id: "datatap", default: false }])).toEqual({
      datatap: false,
    });
    expect(extraOffFromCatalog([{ id: "datatap", default: true }])).toEqual({});
    expect(extraOffFromCatalog([{ id: "datatap" }])).toEqual({});
  });

  it("summarizes operator MCP servers for the settings row", () => {
    const servers = [
      { id: "datatap", label: "DataTap" },
      { id: "linear", label: "Linear" },
    ];
    expect(mcpMenuSummary([], () => true)).toBe("None");
    expect(mcpMenuSummary(servers, () => false)).toBe("Off");
    expect(mcpMenuSummary(servers, (id) => id === "datatap")).toBe("DataTap");
    expect(mcpMenuSummary(servers, () => true)).toBe("2 on");
  });

  it("registers enabled MCP servers onto the settings tool list", () => {
    const servers = [
      { id: "datatap", label: "DataTap" },
      { id: "linear", label: "Linear" },
    ];
    expect(registeredMcpTools(servers, () => false)).toEqual([]);
    expect(registeredMcpTools(servers, (id) => id === "datatap")).toEqual([
      { id: "datatap", label: "DataTap" },
    ]);
  });

  it("lists catalog ids that are off", () => {
    expect(
      disabledCatalogIds({
        ...DEFAULT_EMBED_CHAT_PREFS,
        digisearch: false,
        vault: false,
        extra: { datatap: false },
      }),
    ).toEqual(["digisearch", "digivault", "datatap"]);
  });
});
