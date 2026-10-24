import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { describe, expect, it } from "vitest";

/**
 * Pins the house document's tool/MCP naming and endpoints (`config/defaults.yaml`).
 *
 * Two defects landed together here:
 * - `mcp.servers[].url` named the docker-compose services
 *   (`http://digisearch-mcp:8765/mcp`). Those only resolve inside the compose
 *   network, so the Cloudflare deployment answered "unavailable". The public
 *   digithings-stack routes are `/_stack/mcp/<id>/*` on search./graph.
 * - `label` invented a vocabulary ("Search", "Vault") the backend does not use.
 *   The `/tools` and `/mcp` rows are named by the server id, so the document's
 *   labels repeat the id (`digisearch`, `digivault`) and no menu can drift to a
 *   title-cased display name.
 */
type Entry = { id?: string; label?: string; url?: string; tokenEnv?: string; authHeader?: string };

const doc = loadYaml(
  readFileSync(resolve(__dirname, "../../config/defaults.yaml"), "utf8"),
) as {
  deployment?: {
    tools?: { catalog?: Entry[] };
    mcp?: { servers?: Entry[] };
  };
};

const catalog = doc.deployment?.tools?.catalog ?? [];
const servers = doc.deployment?.mcp?.servers ?? [];

describe("house document tool/MCP naming", () => {
  it("labels every catalog entry with its backend id", () => {
    expect(catalog.length, "no tools.catalog entries parsed from defaults.yaml").toBeGreaterThan(0);
    const renamed = catalog
      .filter((entry) => entry.id !== undefined && entry.label !== entry.id)
      .map((entry) => `${entry.id ?? "?"}: ${entry.label ?? "(no label)"}`);
    expect(renamed, `catalog label(s) that differ from the id: ${renamed.join(", ")}`).toEqual([]);
  });

  it("labels every MCP server with its backend id", () => {
    expect(servers.length, "no mcp.servers entries parsed from defaults.yaml").toBeGreaterThan(0);
    const renamed = servers
      .filter((entry) => entry.id !== undefined && entry.label !== entry.id)
      .map((entry) => `${entry.id ?? "?"}: ${entry.label ?? "(no label)"}`);
    expect(renamed, `MCP label(s) that differ from the id: ${renamed.join(", ")}`).toEqual([]);
  });
});

describe("house document MCP endpoints", () => {
  it("points digisearch and digivault at the stack edge routes", () => {
    const urls = Object.fromEntries(servers.map((entry) => [entry.id, entry.url]));
    expect(urls).toEqual({
      digisearch: "https://search.digithings.ai/_stack/mcp/digisearch/mcp",
      digivault: "https://graph.digithings.ai/_stack/mcp/digivault/mcp",
    });
  });

  it("names no compose hostname", () => {
    // `digisearch-mcp:8765` resolves only inside the compose network; a URL of
    // that shape reaches the Cloudflare deployment as "unavailable".
    const compose = servers
      .filter((entry) => /^[a-z]+:\/\/[a-z0-9-]+-mcp:\d+/.test(entry.url ?? ""))
      .map((entry) => `${entry.id ?? "?"} → ${entry.url ?? ""}`);
    expect(compose, `compose-only hostname(s) in the house document: ${compose.join(", ")}`).toEqual(
      [],
    );
  });

  it("sends the edge key from DIGICHAT_MCP_EDGE_KEY as x-digi-mcp-key", () => {
    // The edge answers 401 without the key. `tokenEnv` names the container
    // secret (the value is never in the document) and `authHeader` is the name
    // digithings-stack's gate reads; without both the forwarded key is inert.
    const wired = servers.map((entry) => ({
      id: entry.id,
      tokenEnv: entry.tokenEnv,
      authHeader: entry.authHeader,
    }));
    expect(wired).toEqual([
      { id: "digisearch", tokenEnv: "DIGICHAT_MCP_EDGE_KEY", authHeader: "x-digi-mcp-key" },
      { id: "digivault", tokenEnv: "DIGICHAT_MCP_EDGE_KEY", authHeader: "x-digi-mcp-key" },
    ]);
  });
});
