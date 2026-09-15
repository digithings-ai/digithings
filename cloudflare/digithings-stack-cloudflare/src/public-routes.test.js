import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the public custom-domain routes declared in wrangler.toml against the
 * hostnames src/ports.ts routes. A host the Worker maps in code is unreachable
 * without an enabled `[[routes]]` entry: the deploy comes up green and every
 * request to that host 404s at the edge (unknown host → portForHostname null).
 * Commented-out blocks (e.g. the mcp.digithings.ai HUMAN GATE route) are not
 * enabled ingress and are filtered out before parsing.
 *
 * Deliberately plain `.js`, same reason as env-vars-pin.test.js: tsconfig.json
 * scopes `types` to @cloudflare/workers-types only, so node:fs / node:path /
 * node:url have no ambient declarations in a `.ts` file here. vitest still runs
 * it via the `.test.{ts,js}` glob in vitest.config.ts.
 */
const config = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "wrangler.toml"),
  "utf-8",
);

function enabledCustomDomainPatterns(source) {
  const uncommented = source
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("#"))
    .join("\n");
  return uncommented
    .split(/^\[\[/m)
    .filter((block) => block.startsWith("routes]]") && /custom_domain\s*=\s*true/.test(block))
    .map((block) => block.match(/pattern\s*=\s*"([^"]+)"/)?.[1])
    .filter((pattern) => Boolean(pattern));
}

describe("wrangler.toml public routes", () => {
  it("declares an enabled custom domain for every public stack host", () => {
    const patterns = enabledCustomDomainPatterns(config);
    for (const host of [
      "graph.digithings.ai",
      "key.digithings.ai",
      "search.digithings.ai",
    ]) {
      expect(patterns, `missing enabled custom-domain route for ${host}`).toContain(host);
    }
  });
});
