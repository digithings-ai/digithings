import { describe, expect, it } from "vitest";
import {
  connectedMcpConfigs,
  connectedTools,
  cycleMcpAuth,
  emptyMcpConfig,
  mcpConfigJson,
  mcpConfigRecord,
  mcpMenuSummaryFromConfigs,
  mcpStatus,
  mcpStatusLabel,
  mcpSessionOverlayHeaderValue,
  parseMcpSeed,
  replaceMcpConfig,
  toolsMenuSummary,
  upsertMcpConfig,
} from "./embed-mcp-flow";

describe("parseMcpSeed", () => {
  it("opens new, an id, or nothing", () => {
    expect(parseMcpSeed("")).toBeUndefined();
    expect(parseMcpSeed("new")).toBe("new");
    expect(parseMcpSeed("add")).toBe("new");
    expect(parseMcpSeed("datatap")).toBe("datatap");
    expect(parseMcpSeed("Nope")).toBe("nope");
    expect(parseMcpSeed("nope!")).toBeUndefined();
  });
});

describe("mcpStatus", () => {
  it("reports disabled, needs auth, or active", () => {
    const base = { ...emptyMcpConfig(), id: "linear" };
    expect(mcpStatus(base, false)).toBe("disabled");
    expect(mcpStatusLabel(mcpStatus({ ...base, auth: "oauth" }, true))).toBe("Needs auth");
    expect(mcpStatus({ ...base, auth: "bearer", token: "sk" }, true)).toBe("active");
  });
});

describe("mcpConfigJson", () => {
  it("omits operator urls and masks tokens", () => {
    const json = mcpConfigJson({
      id: "datatap",
      label: "DataTap",
      url: "https://secret.example/mcp",
      auth: "bearer",
      token: "sk-live",
      extra: { timeout: "30" },
      source: "operator",
    });
    expect(json).toContain('"id": "datatap"');
    expect(json).not.toContain("secret.example");
    expect(json).toContain('"token": "••••"');
    expect(json).toContain('"timeout": "30"');
  });

  it("includes url for session MCP", () => {
    const rec = mcpConfigRecord({
      ...emptyMcpConfig(),
      id: "linear",
      url: "https://mcp.linear.app",
    });
    expect(rec.url).toBe("https://mcp.linear.app");
  });
});

describe("connectedMcpConfigs", () => {
  it("merges operator rows with session overlays and appends new ids", () => {
    const rows = connectedMcpConfigs(
      [{ id: "datatap", label: "DataTap" }],
      [
        {
          id: "datatap",
          label: "DataTap",
          url: "https://ignored.example",
          auth: "bearer",
          token: "abc",
          extra: {},
          source: "session",
        },
        { ...emptyMcpConfig(), id: "linear", label: "Linear" },
      ],
    );
    expect(rows.map((s) => s.id)).toEqual(["datatap", "linear"]);
    expect(rows[0]?.source).toBe("operator");
    expect(rows[0]?.url).toBe("");
    expect(rows[0]?.auth).toBe("bearer");
    expect(rows[1]?.source).toBe("session");
  });
});

describe("upsertMcpConfig", () => {
  it("rejects a bad id, lowercases, and replaces a matching id", () => {
    expect(upsertMcpConfig([], { ...emptyMcpConfig(), id: "Nope!" })).toEqual([]);
    expect(upsertMcpConfig([], { ...emptyMcpConfig(), id: "Nope" })[0]?.id).toBe("nope");
    const once = upsertMcpConfig([], { ...emptyMcpConfig(), id: "linear", label: "A" });
    const twice = upsertMcpConfig(once, { ...emptyMcpConfig(), id: "linear", label: "B" });
    expect(twice).toHaveLength(1);
    expect(twice[0]?.label).toBe("B");
  });
});

describe("replaceMcpConfig", () => {
  it("drops the previous session slug when the id changes", () => {
    const first = replaceMcpConfig([], "", { ...emptyMcpConfig(), id: "l" });
    const renamed = replaceMcpConfig(first, "l", { ...emptyMcpConfig(), id: "linear" });
    expect(renamed.map((s) => s.id)).toEqual(["linear"]);
  });
});

describe("connectedTools", () => {
  it("lists catalog tools then MCP, with websearch as the public name", () => {
    const rows = connectedTools({
      hasDigisearch: true,
      hasVault: true,
      tenantAllowsWeb: true,
      catalogTools: [
        { id: "digisearch", label: "Search" },
        { id: "web_search", label: "Web search" },
      ],
      mcpServers: [{ id: "datatap", label: "DataTap" }],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.slash)).toEqual([
      "digisearch",
      "digivault",
      "websearch",
      "datatap",
    ]);
    expect(rows.find((r) => r.id === "datatap")?.kind).toBe("mcp");
  });
});

describe("summaries", () => {
  it("counts connected tools that are on", () => {
    const rows = connectedTools({
      hasDigisearch: true,
      hasVault: true,
      tenantAllowsWeb: false,
      catalogTools: [],
      mcpServers: [],
      mcpCustom: [],
    });
    expect(toolsMenuSummary(rows, () => false)).toBe("Off");
    expect(toolsMenuSummary(rows, () => true)).toBe("All on");
    expect(toolsMenuSummary(rows, (id) => id === "digisearch")).toBe("Search");
  });

  it("summarizes MCP configs", () => {
    const servers = connectedMcpConfigs([{ id: "datatap", label: "DataTap" }], []);
    expect(mcpMenuSummaryFromConfigs(servers, () => false)).toBe("Off");
    expect(mcpMenuSummaryFromConfigs(servers, () => true)).toBe("DataTap");
  });
});

describe("cycleMcpAuth", () => {
  it("wraps none → bearer → oauth", () => {
    expect(cycleMcpAuth("none", 1)).toBe("bearer");
    expect(cycleMcpAuth("oauth", 1)).toBe("none");
    expect(cycleMcpAuth("none", -1)).toBe("oauth");
  });
});

describe("mcpSessionOverlayHeaderValue", () => {
  it("omits operator URLs and skips session URLs when overlay is off", () => {
    const operator = {
      ...emptyMcpConfig(),
      id: "datatap",
      source: "operator" as const,
      token: "tok",
      auth: "oauth" as const,
    };
    const session = {
      ...emptyMcpConfig(),
      id: "linear",
      url: "https://mcp.linear.app/mcp",
      source: "session" as const,
    };
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, false)).toContain(
      "datatap",
    );
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, false)).not.toContain(
      "mcp.linear.app",
    );
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, true)).toContain(
      "mcp.linear.app",
    );
  });
});
