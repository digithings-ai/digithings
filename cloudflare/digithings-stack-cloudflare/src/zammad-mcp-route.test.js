// Source pins for the secret-gated Zammad MCP edge path (#4174):
// digigraph dials https://graph.digithings.ai/_stack/mcp/zammad/mcp because the
// container-internal `zammad-mcp` name cannot be resolved there (/etc/hosts is
// read-only and the entrypoint alias is skipped). The route must stay
// fail-closed, and the in-container program must keep its 0.0.0.0 bind.
// Deliberately plain `.js`, same reason as env-vars-pin.test.js /
// public-routes.test.js: tsconfig.json scopes `types` to @cloudflare/workers-types
// only, so the vitest runner picks this up without a TS program.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const stackDir = join(here, "..");

describe("zammad MCP edge path", () => {
  const source = readFileSync(join(here, "index.ts"), "utf-8");

  it("declares the public path + dedicated port constants", () => {
    expect(source).toContain('const ZAMMAD_MCP_PUBLIC_PATH = "/_stack/mcp/zammad";');
    expect(source).toContain("const ZAMMAD_MCP_PORT = 8770;");
  });

  it("routes the prefix fail-closed on a missing or wrong key", () => {
    expect(source).toContain("url.pathname === ZAMMAD_MCP_PUBLIC_PATH");
    expect(source).toContain("workerEnv.MCP_EDGE_KEY?.trim()");
    expect(source).toContain("x-digi-mcp-key");
    expect(source).toContain("if (!expected || !provided || provided !== expected)");
    expect(source).toContain("digithings-stack: unauthorized");
    expect(source).toContain("status: 401");
  });

  it("strips the prefix, keeps the trailing slash, and forwards to :8770", () => {
    expect(source).toContain("url.pathname.slice(ZAMMAD_MCP_PUBLIC_PATH.length)");
    expect(source).toContain('if (!stripped.endsWith("/"))');
    expect(source).toContain("switchPort(forwarded, ZAMMAD_MCP_PORT)");
    expect(source).toContain("getContainer(workerEnv.STACK, SHARED_STACK_CONTAINER_ID)");
  });
});

describe("zammad-mcp program bind", () => {
  const supervisor = readFileSync(
    join(stackDir, "container/supervisor/supervisord.conf"),
    "utf-8",
  );

  it("listens on 0.0.0.0:8770 under supervisord", () => {
    expect(supervisor).toContain("[program:zammad-mcp]");
    expect(supervisor).toContain("scripts.zammad_mcp.server --port 8770");
    expect(supervisor).toContain("ZAMMAD_MCP_HOST");
    expect(supervisor).toContain("0.0.0.0");
  });
});
