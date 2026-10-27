import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the bind host of every shared-stack service the Worker routes to.
 *
 * The Worker proxies to the container network address (e.g. 10.0.0.1:8002),
 * so an edge service that binds loopback is unreachable. #4067 added the
 * search.digithings.ai route but start_digisearch.sh still exec'd uvicorn with
 * `--host 127.0.0.1`, and live requests failed with "The container is not
 * listening in the TCP address 10.0.0.1:8002" (#4071). This test reads the same
 * files the container starts from, so an edge service that keeps (or regains) a
 * loopback bind fails here instead of in production.
 *
 * Loopback-only services (digivault, LiteLLM, redis, the *-mcp programs) are
 * deliberately absent: the Worker does not route to them. The dedicated
 * digiquant-mcp container (DIGIQUANT_MCP_PORT, a different image) used to sit
 * outside the shared stack too; it was deleted in DIG-5558, so its port is
 * pinned as not routed below rather than as a bind to verify.
 *
 * Deliberately plain `.js`, same reason as env-vars-pin.test.js /
 * public-routes.test.js: tsconfig.json scopes `types` to
 * @cloudflare/workers-types only, so node:fs / node:path / node:url have no
 * ambient declarations in a `.ts` file here. vitest still runs it via the
 * `.test.{ts,js}` glob in vitest.config.ts.
 */
const here = dirname(fileURLToPath(import.meta.url));
const stackDir = join(here, "..");

/** ROUTED[portConst] = file whose command starts that service. */
const STARTERS = {
  DIGIGRAPH_PORT: "container/supervisor/supervisord.conf",
  DIGIKEY_PORT: "container/start_digikey.sh",
  DIGISEARCH_PORT: "container/start_digisearch.sh",
};

function routedPorts() {
  const source = readFileSync(join(here, "ports.ts"), "utf-8");
  const ports = new Map();
  for (const [, name, value] of source.matchAll(
    /export const (DIGI[A-Z_]+_PORT) = (\d+);/g,
  )) {
    ports.set(name, Number(value));
  }
  return ports;
}

/** Every `--host H --port P` / `--port P ... --host H` bind for `port`. */
function bindsFor(source, port) {
  const binds = [];
  const hostFirst = new RegExp(`--host\\s+(\\S+)\\s+--port\\s+${port}\\b`, "g");
  const portFirst = new RegExp(`--port\\s+${port}\\b[^\\n]*?--host\\s+(\\S+)`, "g");
  for (const [, host] of source.matchAll(hostFirst)) binds.push(host);
  for (const [, host] of source.matchAll(portFirst)) binds.push(host);
  return binds;
}

describe("container binds for Worker-routed ports", () => {
  const ports = routedPorts();

  it("ports.ts still declares every routed port constant this test pins", () => {
    expect([...ports.keys()].sort()).toEqual(
      expect.arrayContaining(Object.keys(STARTERS)),
    );
  });

  for (const [portConst, relativeFile] of Object.entries(STARTERS)) {
    it(`${portConst} (:${ports.get(portConst)}) binds 0.0.0.0 in ${relativeFile}`, () => {
      const port = ports.get(portConst);
      expect(port).toBeTypeOf("number");
      const binds = bindsFor(
        readFileSync(join(stackDir, relativeFile), "utf-8"),
        port,
      );
      expect(binds.length).toBeGreaterThan(0);
      expect(binds).toEqual(binds.map(() => "0.0.0.0"));
    });
  }

  it("keeps the deleted digiquant-mcp container out of the Worker's routed binds", () => {
    // DIG-5558 deleted DigiQuantMcpContainer and its MCP_STACK binding: the
    // market-data read path is the Worker-native DigiQuantMcpAgent, which reads
    // R2 directly and never proxies to a container port. If the class came back,
    // its dedicated image would need a bind check again — so its absence is
    // pinned here.
    const indexSource = readFileSync(join(here, "index.ts"), "utf-8");
    expect(indexSource).not.toContain("DigiQuantMcpContainer");
    expect(indexSource).not.toContain("DIGIQUANT_MCP_PORT");
  });
});
