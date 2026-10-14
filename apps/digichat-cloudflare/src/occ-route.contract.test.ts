import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..");

/** Workers that can own digithings.ai paths. A deploy of either without this route drops the gate. */
const ROUTE_FILES = [
  "apps/digichat-cloudflare/wrangler.toml",
  "apps/digithings-stack-cloudflare/wrangler.toml",
];

describe("OCC invite route contract (DIG-3585)", () => {
  for (const rel of ROUTE_FILES) {
    it(`${rel} declares digithings.ai/chat/occ*`, () => {
      const text = readFileSync(join(repoRoot, rel), "utf8");
      expect(text).toMatch(/pattern\s*=\s*"digithings\.ai\/chat\/occ\*"/);
    });
  }

  it("the post-deploy smoke refuses a chat shell on a non-404", () => {
    const script = readFileSync(join(repoRoot, "scripts/smoke_occ_invite_gate.sh"), "utf8");
    expect(script).toMatch(/404/);
    expect(script).toMatch(/ChatPageShell/);
    expect(script).toMatch(/dc-chat-main/);
    expect(script).toMatch(/\/chat\/occ\//);
  });
});
