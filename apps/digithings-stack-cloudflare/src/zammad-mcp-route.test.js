// Source pins for the secret-gated MCP edge paths (#4174; digisearch +
// digivault): digraph dials https://graph.digithings.ai/_stack/mcp/<id>/mcp
// because the container-internal server names cannot be resolved there
// (/etc/hosts is read-only and the entrypoint alias is skipped). The OCC
// zammad MCP moved out of this stack into the digichat image
// (https://digithings.ai/api/mcp/zammad/mcp), so it is deliberately absent
// here. Every mapped route must stay fail-closed, and each in-container
// program must keep its 0.0.0.0 bind.
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
    expect(source).toContain("digisearch: 8765");
    expect(source).toContain("digivault: 8769");
    // The zammad MCP is no longer a stack server (it runs in the digichat image
    // now, served at /api/mcp/zammad/mcp); a re-added map entry is a regression.
    expect(source).not.toContain("zammad: 8770");
  });

  // DIG-2785 (reverses the DIG-2638 download port): oversized Zammad
  // retrievals are now session-scoped artifacts in the DigiChat artifact store,
  // served by digichat behind its own invite-key gate. Nothing is served off a
  // second port here, so the map must NOT carry one - a regression would reopen
  // the fixed-TTL download this leaf removed.
  it("no longer maps a ticket-download port (DIG-2785)", () => {
    expect(source).not.toContain('"zammad-export"');
    expect(source).not.toContain("8771");
    const mapHead = "const MCP_EDGE_SERVERS: Record<string, number> = {";
    const mapAt = source.indexOf(mapHead);
    expect(mapAt).toBeGreaterThan(-1);
    // Slice from AFTER the head, not from it: the head carries its own colon,
    // so counting colons across it reads one entry too many.
    const mapEnd = source.indexOf("};", mapAt);
    expect(mapEnd).toBeGreaterThan(mapAt);
    const mapBody = source.slice(mapAt + mapHead.length, mapEnd);
    for (const entry of ["digisearch: 8765", "digivault: 8769"]) {
      expect(mapBody).toContain(entry);
    }
    // Count the entries themselves, not every colon: a third server must fail
    // this, and nothing else may be able to.
    expect(mapBody.split("\n").filter((line) => /^\s*\w+\s*:\s*\d+/.test(line))).toHaveLength(2);
  });

  it("routes every mapped prefix fail-closed on a missing or wrong key", () => {
    expect(source).toContain("url.pathname.startsWith(`${MCP_EDGE_PREFIX}/`)");
    expect(source).toContain("workerEnv.MCP_EDGE_KEY?.trim()");
    expect(source).toContain("x-digi-mcp-key");
    expect(source).toContain("if (!expected || !provided || provided !== expected)");
    expect(source).toContain("digithings-stack: unauthorized");
    expect(source).toContain("status: 401");
  });

  it("strips the prefix, forwards the path unchanged, and forwards to the mapped port", () => {
    expect(source).toContain("url.pathname.slice(MCP_EDGE_PREFIX.length + 1)");
    expect(source).toContain("const port = MCP_EDGE_SERVERS[serverId];");
    expect(source).toContain('typeof port === "number"');
    // mcp>=1.26 serves `/mcp` and 307s `/mcp/`; a rewritten path breaks
    // clients that do not replay the body, so the client path is untouched.
    expect(source).toContain('const stripped = slash === -1 ? "/" : rest.slice(slash);');
    expect(source).not.toContain('stripped += "/"');
    expect(source).toContain("switchPort(forwarded, port)");
    // The MCP edge path reaches the shared stack through the single
// stackContainer() helper (DIG-3229), which is where the Container id is
// derived from the deploying commit. Pinning the helper here, not the old
// constant, keeps this guard honest about where the id now comes from.
expect(source).toContain("function stackContainer(workerEnv: Env)");
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

  it("runs no zammad-mcp program: the OCC MCP lives in the digichat image now", () => {
    // Removed from the base platform: the zammad MCP is built into the digichat
    // image (infra/docker/Dockerfile.digichat-cloudflare) and served at
    // https://digithings.ai/api/mcp/zammad/mcp. A re-added supervisord program
    // is a regression.
    expect(supervisor).not.toContain("[program:zammad-mcp]");
    expect(supervisor).not.toContain("scripts.zammad_mcp.server");
    expect(supervisor).not.toContain("ZAMMAD_MCP_HOST");
  });

  it("digisearch-mcp binds 0.0.0.0:8765 under supervisord", () => {
    expect(supervisor).toContain("[program:digisearch-mcp]");
    expect(supervisor).toContain('environment=DIGISEARCH_MCP_HOST="0.0.0.0"');
  });

  it("digivault-mcp binds 0.0.0.0:8769 under supervisord", () => {
    expect(supervisor).toContain("[program:digivault-mcp]");
    expect(supervisor).toContain("python -m digivault.mcp_server --port 8769 --host 0.0.0.0");
  });

  it("runs no ticket-download program: the cut goes to the artifact store (DIG-2785)", () => {
    expect(supervisor).not.toContain("zammad-export");
    expect(supervisor).not.toContain("export_server");
    expect(supervisor).not.toContain("ZAMMAD_EXPORT_DIR");
  });
});

describe("zammad MCP image surface", () => {
  const dockerfile = readFileSync(
    join(stackDir, "..", "..", "scripts", "zammad_mcp", "Dockerfile.mcp"),
    "utf-8",
  );

  it("exposes only the MCP port and still copies the whole module (DIG-2785)", () => {
    expect(dockerfile).toContain("EXPOSE 8770");
    expect(dockerfile).not.toContain("EXPOSE 8771");
    expect(dockerfile).toContain("COPY scripts/zammad_mcp ./scripts/zammad_mcp");
  });

  it("ships no object-store credential to reach the artifact store (DIG-2785)", () => {
    // The oversized cut is written through the DigiChat ingest route, which owns
    // the blob store and re-checks conversation ownership. A storage credential
    // in this image would make zammad a second, ungated writer.
    expect(dockerfile).not.toMatch(/R2_SECRET|S3_SECRET|AWS_SECRET|BUCKET_SECRET|STORAGE_KEY/);
    expect(dockerfile).not.toContain("DIGICHAT_SUPABASE");
  });
});
