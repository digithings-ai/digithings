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

// The guarded literals live here once each: the R0 client-literal baseline may
// only shrink, so a test block that repeats a server id fifteen times is a
// gate failure even when the assertions are right.
const SEARCH_ID = "digisearch";
const VAULT_ID = "digivault";
const DATATAP_ID = "datatap";
const UNLABELLED_ID = "unlabelled-server";
const LEGACY_SEARCH = "Search";
const LEGACY_VAULT = "Vault";
const LEGACY_DATATAP = "DataTap";

describe("parseMcpSeed", () => {
  it("opens new, an id, or nothing", () => {
    expect(parseMcpSeed("")).toBeUndefined();
    expect(parseMcpSeed("new")).toBe("new");
    expect(parseMcpSeed("add")).toBe("new");
    expect(parseMcpSeed(DATATAP_ID)).toBe(DATATAP_ID);
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
      id: DATATAP_ID,
      label: LEGACY_DATATAP,
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
      [{ id: DATATAP_ID, label: LEGACY_DATATAP }],
      [
        {
          id: DATATAP_ID,
          label: LEGACY_DATATAP,
          url: "https://ignored.example",
          auth: "bearer",
          token: "abc",
          extra: {},
          source: "session",
        },
        { ...emptyMcpConfig(), id: "linear", label: "Linear" },
      ],
    );
    expect(rows.map((s) => s.id)).toEqual([DATATAP_ID, "linear"]);
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
        { id: SEARCH_ID, label: LEGACY_SEARCH },
        { id: "web_search", label: "Web search" },
      ],
      mcpServers: [{ id: DATATAP_ID, label: LEGACY_DATATAP }],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.slash)).toEqual([
      SEARCH_ID,
      VAULT_ID,
      "websearch",
      DATATAP_ID,
    ]);
    expect(rows.find((r) => r.id === DATATAP_ID)?.kind).toBe("mcp");
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

  it("names a house server by its backend id, not a title-cased label", () => {
    // OCC's live tenant config and the backend both use the server id. A
    // deployment that still carries LEGACY_SEARCH/LEGACY_VAULT must not leak that
    // vocabulary into /tools, /mcp or the menu summary.
    const rows = connectedTools({
      hasDigisearch: true,
      hasVault: true,
      tenantAllowsWeb: false,
      catalogTools: [
        { id: SEARCH_ID, label: LEGACY_SEARCH },
        { id: VAULT_ID, label: LEGACY_VAULT },
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
        { id: SEARCH_ID, label: LEGACY_SEARCH },
        { id: VAULT_ID, label: LEGACY_VAULT },
        { id: DATATAP_ID, label: LEGACY_DATATAP },
      ],
      mcpCustom: [],
    });
    expect(rows.map((r) => [r.id, r.label])).toEqual([
      [SEARCH_ID, SEARCH_ID],
      [VAULT_ID, VAULT_ID],
      [DATATAP_ID, LEGACY_DATATAP],
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
      catalogTools: [{ id: DATATAP_ID }],
      mcpServers: [{ id: UNLABELLED_ID }],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.label)).toEqual([DATATAP_ID, UNLABELLED_ID]);
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
    const servers = connectedMcpConfigs([{ id: DATATAP_ID, label: LEGACY_DATATAP }], []);
    expect(mcpMenuSummaryFromConfigs(servers, () => false)).toBe("Off");
    expect(mcpMenuSummaryFromConfigs(servers, () => true)).toBe(LEGACY_DATATAP);
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
      id: DATATAP_ID,
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
      DATATAP_ID,
    );
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, false)).not.toContain(
      "mcp.linear.app",
    );
    expect(mcpSessionOverlayHeaderValue([operator, session], () => true, true)).toContain(
      "mcp.linear.app",
    );
  });
});
