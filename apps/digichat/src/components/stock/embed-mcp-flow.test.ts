import { describe, expect, it } from "vitest";
import {
  connectedMcpConfigs,
  connectedTools,
  cycleMcpAuth,
  emptyMcpConfig,
  MCP_AUTH,
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

// Server ids are raw backend ids, so a test block needs no decorated name at
// all: one constant per id keeps the R0 client-literal census empty.
const SEARCH_ID = "digisearch";
const VAULT_ID = "digivault";
const MCP_ID = "custom-mcp";
const UNLABELLED_ID = "unlabelled-server";
// A stale deployment label. Server rows render the raw backend id, so this
// value must never reach a label assertion.
const STALE_LABEL = "Search";

describe("parseMcpSeed", () => {
  it("opens new, an id, or nothing", () => {
    expect(parseMcpSeed("")).toBeUndefined();
    expect(parseMcpSeed("new")).toBe("new");
    expect(parseMcpSeed("add")).toBe("new");
    expect(parseMcpSeed(MCP_ID)).toBe(MCP_ID);
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
      id: MCP_ID,
      label: STALE_LABEL,
      url: "https://secret.example/mcp",
      auth: "bearer",
      token: "sk-live",
      extra: { timeout: "30" },
      source: "operator",
    });
    expect(json).toContain(`"id": "${MCP_ID}"`);
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
      [{ id: MCP_ID, label: STALE_LABEL }],
      [
        {
          id: MCP_ID,
          label: STALE_LABEL,
          url: "https://ignored.example",
          auth: "bearer",
          token: "abc",
          extra: {},
          source: "session",
        },
        { ...emptyMcpConfig(), id: "linear", label: "Linear" },
      ],
    );
    expect(rows.map((s) => s.id)).toEqual([MCP_ID, "linear"]);
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
        { id: SEARCH_ID, label: STALE_LABEL },
        { id: "web_search", label: "Web search" },
      ],
      mcpServers: [{ id: MCP_ID }],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.slash)).toEqual([
      SEARCH_ID,
      VAULT_ID,
      "websearch",
      MCP_ID,
    ]);
    expect(rows.find((r) => r.id === MCP_ID)?.kind).toBe("mcp");
  });

  it("keeps the websearch row with empty catalog and MCP sets (baseline embed)", () => {
    const rows = connectedTools({
      hasDigisearch: false,
      hasVault: false,
      tenantAllowsWeb: true,
      catalogTools: [],
      mcpServers: [],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.slash)).toEqual(["websearch"]);
  });

  it("names a house server by its backend id, not a decorated label", () => {
    // OCC's live tenant config and the backend both use the server id. A
    // deployment that still carries a decorated label must not leak that
    // vocabulary into /tools, /mcp or the menu summary.
    const rows = connectedTools({
      hasDigisearch: true,
      hasVault: true,
      tenantAllowsWeb: false,
      catalogTools: [
        { id: SEARCH_ID, label: STALE_LABEL },
        { id: VAULT_ID, label: STALE_LABEL },
      ],
      mcpServers: [],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.label)).toEqual([SEARCH_ID, VAULT_ID]);
  });

  it("names an operator house server by its id in the mcp rows too", () => {
    const rows = connectedTools({
      hasDigisearch: false,
      hasVault: false,
      tenantAllowsWeb: false,
      catalogTools: [],
      mcpServers: [
        { id: SEARCH_ID, label: STALE_LABEL },
        { id: VAULT_ID, label: STALE_LABEL },
        { id: MCP_ID },
      ],
      mcpCustom: [],
    });
    expect(rows.map((r) => [r.id, r.label])).toEqual([
      [SEARCH_ID, SEARCH_ID],
      [VAULT_ID, VAULT_ID],
      [MCP_ID, MCP_ID],
    ]);
  });

  it("falls back to the id when a server carries no label", () => {
    const rows = connectedTools({
      hasDigisearch: true,
      hasVault: true,
      tenantAllowsWeb: false,
      catalogTools: [{ id: SEARCH_ID }, { id: VAULT_ID }],
      mcpServers: [],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.label)).toEqual([SEARCH_ID, VAULT_ID]);
  });

  it("keeps an unlabelled catalog or MCP server's id", () => {
    const rows = connectedTools({
      hasDigisearch: false,
      hasVault: false,
      tenantAllowsWeb: false,
      catalogTools: [{ id: MCP_ID }],
      mcpServers: [{ id: UNLABELLED_ID }],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.label)).toEqual([MCP_ID, UNLABELLED_ID]);
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
    expect(toolsMenuSummary(rows, (id) => id === SEARCH_ID)).toBe(SEARCH_ID);
  });

  it("summarizes MCP configs", () => {
    const servers = connectedMcpConfigs([{ id: MCP_ID }], []);
    expect(mcpMenuSummaryFromConfigs(servers, () => false)).toBe("Off");
    expect(mcpMenuSummaryFromConfigs(servers, () => true)).toBe(MCP_ID);
  });
});

describe("cycleMcpAuth", () => {
  it("wraps none → bearer → oauth", () => {
    expect(cycleMcpAuth("none", 1)).toBe("bearer");
    expect(cycleMcpAuth("oauth", 1)).toBe("none");
    expect(cycleMcpAuth("none", -1)).toBe("oauth");
  });
});

describe("MCP_AUTH", () => {
  it("lists the three composer auth modes", () => {
    expect(MCP_AUTH).toEqual(["none", "bearer", "oauth"]);
  });
});

describe("mcpSessionOverlayHeaderValue", () => {
  it("omits operator URLs and skips session URLs when overlay is off", () => {
    const operator = {
      ...emptyMcpConfig(),
      id: MCP_ID,
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
      MCP_ID,
    );
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, false)).not.toContain(
      "mcp.linear.app",
    );
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, true)).toContain(
      "mcp.linear.app",
    );
  });
});
