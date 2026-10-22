import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { connectedTools } from "@/components/stock/embed-mcp-flow";
import { parseEmbedTenants } from "./embed-tenants";

// The staged prod overlay merged onto a stand-in live row (no real token).
function houseTenant() {
  const overlay = JSON.parse(
    readFileSync(
      resolve(__dirname, "../../../../infra/digichat-release/DIG-3556-staged-prod-tenant-config.json"),
      "utf8",
    ),
  ) as { DIGICHAT_EMBED_TENANTS: Record<string, Record<string, unknown>> };
  const row = overlay.DIGICHAT_EMBED_TENANTS["digithings.ai"];
  const live = {
    "digithings.ai": {
      slug: "digithings",
      gateMode: "ungated",
      webSearch: true,
      ...row,
      token: "test-only",
      backend: { type: "digigraph", digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
    },
  };
  const tenant = parseEmbedTenants(JSON.stringify(live)).get("digithings.ai");
  if (!tenant) throw new Error("house tenant did not parse");
  return tenant;
}

describe("house chat /tools", () => {
  it("lists web search, DigiSearch and DigiVault", () => {
    const tenant = houseTenant();
    const catalog = tenant.tools?.catalog ?? [];
    const rows = connectedTools({
      hasDigisearch: catalog.some((e) => e.id === "digisearch"),
      hasVault: catalog.some((e) => e.id === "digivault"),
      tenantAllowsWeb: tenant.webSearch === true,
      catalogTools: catalog,
      mcpServers: [],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.slash)).toEqual(["digisearch", "digivault", "websearch"]);
    expect(rows.map((r) => r.label)).toEqual(["DigiSearch", "DigiVault", "Web search"]);
  });
});
