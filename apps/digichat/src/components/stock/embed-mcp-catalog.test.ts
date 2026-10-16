import { describe, expect, it } from "vitest";
import {
  applyWellKnownMcp,
  filterWellKnownMcps,
  isWellKnownMcpGroup,
  WELL_KNOWN_MCP_GROUPS,
  WELL_KNOWN_MCP_SERVERS,
  WELL_KNOWN_MCP_SUGGEST_MAX,
  WELL_KNOWN_MCP_SUGGEST_PER_GROUP,
  wellKnownMcpById,
  wellKnownMcpGrouped,
  wellKnownMcpHost,
  wellKnownMcpIds,
  wellKnownMcpSuggestions,
} from "./embed-mcp-catalog";
import { emptyMcpConfig, isMcpAuthKind, MCP_ID_RE } from "./embed-mcp-flow";

describe("WELL_KNOWN_MCP_SERVERS", () => {
  it("keeps every id a unique lowercase MCP slug with a known group", () => {
    expect(WELL_KNOWN_MCP_SERVERS.length).toBeGreaterThanOrEqual(20);
    expect(WELL_KNOWN_MCP_SERVERS.length).toBeLessThanOrEqual(40);
    const ids = WELL_KNOWN_MCP_SERVERS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const row of WELL_KNOWN_MCP_SERVERS) {
      expect(row.id).toMatch(MCP_ID_RE);
      expect(row.id).toBe(row.id.toLowerCase());
      expect(row.label.trim()).not.toBe("");
      expect(row.url.startsWith("https://")).toBe(true);
      expect(isMcpAuthKind(row.auth)).toBe(true);
      expect(isWellKnownMcpGroup(row.group)).toBe(true);
    }
    expect(WELL_KNOWN_MCP_GROUPS.every((g) => WELL_KNOWN_MCP_SERVERS.some((s) => s.group === g))).toBe(
      true,
    );
  });

  it("looks up Linear, GitHub, and context7 from official remote URLs", () => {
    expect(wellKnownMcpById("linear")).toEqual({
      id: "linear",
      label: "Linear",
      url: "https://mcp.linear.app/mcp",
      auth: "oauth",
      group: "productivity",
    });
    expect(wellKnownMcpById("GitHub")?.url).toBe("https://api.githubcopilot.com/mcp/");
    expect(wellKnownMcpById("github")?.auth).toBe("oauth");
    expect(wellKnownMcpById("context7")).toEqual({
      id: "context7",
      label: "Context7",
      url: "https://mcp.context7.com/mcp",
      auth: "bearer",
      group: "chat",
    });
    expect(wellKnownMcpById("not-a-server")).toBeUndefined();
    expect(wellKnownMcpIds()).toEqual(WELL_KNOWN_MCP_SERVERS.map((s) => s.id));
  });
});

describe("wellKnownMcpGrouped", () => {
  it("buckets the catalog by group order and skips empty groups", () => {
    const groups = wellKnownMcpGrouped();
    expect(groups.map((g) => g.group)).toEqual([...WELL_KNOWN_MCP_GROUPS]);
    expect(groups.flatMap((g) => g.servers)).toHaveLength(WELL_KNOWN_MCP_SERVERS.length);
    expect(wellKnownMcpGrouped([]).length).toBe(0);
    expect(wellKnownMcpGrouped([wellKnownMcpById("slack")!]).map((g) => g.group)).toEqual(["social"]);
  });
});

describe("filterWellKnownMcps / wellKnownMcpSuggestions", () => {
  it("filters by id or label substring and keeps custom ids unforced", () => {
    const lin = filterWellKnownMcps("lin");
    expect(lin.some((s) => s.id === "linear")).toBe(true);
    expect(lin.every((s) => s.id.includes("lin") || s.label.toLowerCase().includes("lin"))).toBe(true);
    expect(filterWellKnownMcps("LINEAR").some((s) => s.id === "linear")).toBe(true);
    expect(filterWellKnownMcps("my-mcp")).toEqual([]);
    expect(filterWellKnownMcps("").length).toBe(WELL_KNOWN_MCP_SERVERS.length);
    expect(wellKnownMcpHost("https://mcp.linear.app/mcp")).toBe("mcp.linear.app");
  });

  it("caps the empty-id catalog per group and overall", () => {
    const empty = wellKnownMcpSuggestions("");
    expect(empty.length).toBeGreaterThan(0);
    expect(empty.length).toBeLessThanOrEqual(WELL_KNOWN_MCP_SUGGEST_MAX);
    for (const group of WELL_KNOWN_MCP_GROUPS) {
      expect(empty.filter((s) => s.group === group).length).toBeLessThanOrEqual(
        WELL_KNOWN_MCP_SUGGEST_PER_GROUP,
      );
    }
    expect(wellKnownMcpSuggestions("lin").some((s) => s.id === "linear")).toBe(true);
    expect(wellKnownMcpSuggestions("lin").length).toBe(filterWellKnownMcps("lin").length);
  });
});

describe("applyWellKnownMcp", () => {
  it("autofills a session draft from the catalog and keeps a custom id", () => {
    const filled = applyWellKnownMcp(emptyMcpConfig(), "Linear");
    expect(filled).toMatchObject({
      id: "linear",
      label: "Linear",
      url: "https://mcp.linear.app/mcp",
      auth: "oauth",
      token: "",
      source: "session",
    });
    const custom = applyWellKnownMcp(
      { ...emptyMcpConfig(), url: "https://mine.example/mcp", label: "Mine" },
      "my-mcp",
    );
    expect(custom.id).toBe("my-mcp");
    expect(custom.url).toBe("https://mine.example/mcp");
    expect(custom.label).toBe("Mine");
  });

  it("keeps a typed token on the same server and clears it when switching", () => {
    const withToken = applyWellKnownMcp(
      { ...emptyMcpConfig(), id: "linear", token: "keep-me" },
      "linear",
    );
    expect(withToken.token).toBe("keep-me");
    const switched = applyWellKnownMcp(
      { ...emptyMcpConfig(), id: "linear", token: "keep-me" },
      "github",
    );
    expect(switched.id).toBe("github");
    expect(switched.token).toBe("");
    expect(switched.url).toBe("https://api.githubcopilot.com/mcp/");
  });

  it("does not let the catalog steal operator id or url", () => {
    const operator = {
      ...emptyMcpConfig(),
      id: "datatap",
      label: "DataTap",
      url: "",
      source: "operator" as const,
      token: "op-tok",
    };
    expect(applyWellKnownMcp(operator, "linear")).toEqual(operator);
  });
});
