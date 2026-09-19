import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the public custom-domain routes declared in wrangler.toml — both
 * directions:
 *
 *  - every host src/ports.ts routes must have an enabled `[[routes]]` entry
 *    (a host mapped in code but not routed 404s at the edge while the deploy
 *    still comes up green), and
 *  - the enabled set must be exactly the three approved public backends.
 *
 * The exclusivity half is a deliberate tripwire on public exposure: routes are
 * how this Worker reaches the internet, so enabling one is a human-gated
 * decision (see the HUMAN GATE comments in wrangler.toml). Re-enabling the
 * parked `mcp.digithings.ai` route — whose MCP tools are unauthenticated
 * localhost today — must fail this test rather than silently ship ingress.
 * Commented-out blocks are filtered out before parsing; when a new public route
 * is genuinely approved, update the expected set in the same PR.
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
  it("enables exactly the approved custom domains and nothing else", () => {
    expect(enabledCustomDomainPatterns(config).sort()).toEqual([
      "graph.digithings.ai",
      "key.digithings.ai",
      "search.digithings.ai",
    ]);
  });
});
