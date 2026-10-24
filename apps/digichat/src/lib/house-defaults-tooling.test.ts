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
  it("keeps the compose hostnames in the shipped default", () => {
    // The document baked into the image is the compose/self-host topology:
    // these hostnames resolve on the compose network and nowhere else. A
    // deployment that is not compose (the Cloudflare container included)
    // overrides this document from its own config source — the KV
    // `config-yaml` key — with that environment's endpoints. Putting the edge
    // URLs here instead would send every self-hosted install at our Worker,
    // where it holds no key.
    const urls = Object.fromEntries(servers.map((entry) => [entry.id, entry.url]));
    expect(urls).toEqual({
      digisearch: "http://digisearch-mcp:8765/mcp",
      digivault: "http://digivault-mcp:8769/mcp",
    });
  });

  it("ships no edge key reference, so a bare install is not pointed at our stack", () => {
    // `tokenEnv` names a container secret and `authHeader` names the header the
    // stack gate reads. Both belong to a deployment that actually talks to the
    // edge; the shipped default must not claim them.
    const wired = servers
      .filter((entry) => entry.tokenEnv !== undefined || entry.authHeader !== undefined)
      .map((entry) => entry.id);
    expect(wired, `shipped default wires an edge credential for: ${wired.join(", ")}`).toEqual([]);
  });
});
