// Source pins for the secret-gated MCP edge paths (#4174; extended to the
// digisearch + digivault MCP servers): digraph dials
// https://graph.digithings.ai/_stack/mcp/zammad/mcp because the container-internal
// `zammad-mcp` name cannot be resolved there (/etc/hosts is read-only and the
// entrypoint alias is skipped). Every mapped route must stay fail-closed, and each
// in-container program must keep its 0.0.0.0 bind.
// Deliberately plain `.js`, same reason as env-vars-pin.test.js /
// public-routes.test.js: tsconfig.json scopes `types` to @cloudflare/workers-types
// only, so the vitest runner picks this up without a TS program.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const stackDir = join(here, "..");

describe("MCP edge paths", () => {
  const source = readFileSync(join(here, "index.ts"), "utf-8");

  it("declares the prefix + server → port map", () => {
    expect(source).toContain('const MCP_EDGE_PREFIX = "/_stack/mcp";');
    expect(source).toContain("const MCP_EDGE_SERVERS: Record<string, number> = {");
    expect(source).toContain("zammad: 8770");
    expect(source).toContain("digisearch: 8765");
    expect(source).toContain("digivault: 8769");
  });

  it("routes every mapped prefix fail-closed on a missing or wrong key", () => {
    expect(source).toContain("url.pathname.startsWith(`${MCP_EDGE_PREFIX}/`)");
    expect(source).toContain("workerEnv.MCP_EDGE_KEY?.trim()");
    expect(source).toContain("x-digi-mcp-key");
    expect(source).toContain("if (!expected || !provided || provided !== expected)");
    expect(source).toContain("digithings-stack: unauthorized");
    expect(source).toContain("status: 401");
  });

  it("strips the prefix, keeps the trailing slash, and forwards to the mapped port", () => {
    expect(source).toContain("url.pathname.slice(MCP_EDGE_PREFIX.length + 1)");
    expect(source).toContain("const port = MCP_EDGE_SERVERS[serverId];");
    expect(source).toContain('typeof port === "number"');
    expect(source).toContain('if (!stripped.endsWith("/"))');
    expect(source).toContain("switchPort(forwarded, port)");
    expect(source).toContain("getContainer(workerEnv.STACK, SHARED_STACK_CONTAINER_ID)");
  });

  it("supports per-server edge keys with the shared key as fallback", () => {
    expect(source).toContain("MCP_EDGE_KEYS");
    expect(source).toContain(
      "function mcpEdgeKeyFor(serverId: string, workerEnv: Env): string {",
    );
    expect(source).toContain("const expected = mcpEdgeKeyFor(serverId, workerEnv);");
  });
});

describe("in-container MCP program binds", () => {
  const supervisor = readFileSync(
    join(stackDir, "container/supervisor/supervisord.conf"),
    "utf-8",
  );

  it("zammad-mcp listens on 0.0.0.0:8770 under supervisord", () => {
    expect(supervisor).toContain("[program:zammad-mcp]");
    expect(supervisor).toContain("scripts.zammad_mcp.server --port 8770");
    expect(supervisor).toContain("ZAMMAD_MCP_HOST");
    expect(supervisor).toContain("0.0.0.0");
  });

  it("digisearch-mcp binds 0.0.0.0:8765 under supervisord", () => {
    expect(supervisor).toContain("[program:digisearch-mcp]");
    expect(supervisor).toContain('environment=DIGISEARCH_MCP_HOST="0.0.0.0"');
  });

  it("digivault-mcp binds 0.0.0.0:8769 under supervisord", () => {
    expect(supervisor).toContain("[program:digivault-mcp]");
    expect(supervisor).toContain("python -m digivault.mcp_server --port 8769 --host 0.0.0.0");
  });
});
