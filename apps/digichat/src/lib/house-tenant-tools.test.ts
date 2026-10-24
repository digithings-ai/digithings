import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { connectedTools } from "@/components/stock/embed-mcp-flow";
import { toEmbedClientConfig } from "@/lib/embed-client-config";
import { resolveEmbedUiFlags } from "@/lib/embed-ui-flags";
import { parseEmbedTenants } from "@/lib/embed-tenants";
import { resolveRouteClientConfig } from "@/lib/route-client-config";
import { catalogToolsFromClient } from "@digithings/ui/chat/stock";

type Overlay = { DIGICHAT_EMBED_TENANTS: Record<string, Record<string, unknown>> };

// The staged prod overlay merged onto a stand-in live row (no real token).
function houseTenant() {
  const path = resolve(
    __dirname,
    "../../../../infra/digichat-release/DIG-3556-staged-prod-tenant-config.json",
  );
  if (!existsSync(path)) {
    throw new Error(`house overlay not found at ${path}`);
  }
  const overlay = JSON.parse(readFileSync(path, "utf8")) as Overlay;
  const row = overlay.DIGICHAT_EMBED_TENANTS["digithings.ai"];
  const live = {
    "digithings.ai": {
      slug: "digithings",
      gateMode: "ungated",
      webSearch: true,
      ...row,
      token: "test-only",
      backend: {
        type: "digigraph",
        digisearchIndex: "digithings_docs",
        vaultPathPrefix: "clients/digithings",
      },
    },
  };
  const tenant = parseEmbedTenants(JSON.stringify(live)).get("digithings.ai");
  if (!tenant) throw new Error("house tenant did not parse");
  return tenant;
}

describe("house chat /tools", () => {
  it("lists web search, digisearch and digivault by backend id", () => {
    // The chain the embed page runs, end to end: the registry row becomes the
    // client config the embed serves, the route projects it into the stock
    // client config, and the connected-tool rows are built from that. The
    // suite pins the rows the house tenant really shows, not a re-derivation
    // of the overlay.
    const tenant = houseTenant();
    const client = toEmbedClientConfig(tenant);
    const stockClient = resolveRouteClientConfig({ mode: "embed", tenant: client });
    const uiFlags = resolveEmbedUiFlags(client);
    const catalog = stockClient.tools.catalog;
    const catalogTools = catalogToolsFromClient(stockClient);
    const rows = connectedTools({
      hasDigisearch: catalog.some((e) => e.id === "digisearch"),
      hasVault: catalog.some((e) => e.id === "digivault"),
      tenantAllowsWeb: uiFlags.webSearch,
      catalogTools,
      mcpServers: [],
      mcpCustom: [],
    });
    expect(rows.map((r) => r.slash)).toEqual(["digisearch", "digivault", "websearch"]);
    expect(rows.map((r) => r.label)).toEqual(["digisearch", "digivault", "Web search"]);
  });
});
