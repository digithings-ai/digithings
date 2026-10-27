import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * Route ownership for the invite-gated OCC shell.
 *
 * DIG-3585 pinned BOTH workers so a cutover or a rollback could not drop the
 * gate. Chris reversed the cutover on 2026-10-19: OCC is client work and must
 * not ride the base digithings platform, so exactly ONE worker declares the
 * route — the digichat one that also holds OCC_INVITE_KEY.
 */
const OCC_ROUTE_OWNER = "apps/digichat-cloudflare/wrangler.toml";
const BASE_PLATFORM = "apps/digithings-stack-cloudflare/wrangler.toml";
const OCC_PATTERN = /pattern\s*=\s*"digithings\.ai\/chat\/occ\*"/;

describe("OCC invite route contract (DIG-3585, separation 2026-10-19)", () => {
  it(`${OCC_ROUTE_OWNER} declares digithings.ai/chat/occ*`, () => {
    expect(readFileSync(join(repoRoot, OCC_ROUTE_OWNER), "utf8")).toMatch(OCC_PATTERN);
  });

  it(`${BASE_PLATFORM} does NOT declare it — the client surface stays off the base platform`, () => {
    expect(readFileSync(join(repoRoot, BASE_PLATFORM), "utf8")).not.toMatch(OCC_PATTERN);
  });

  it("the post-deploy smoke refuses a chat shell on a non-404", () => {
    const script = readFileSync(join(repoRoot, "scripts/smoke_occ_invite_gate.sh"), "utf8");
    expect(script).toMatch(/404/);
    // The marker the app itself renders (dc-embed-shell), not the deleted
    // Pages shell's wrapper: the smoke must look for what is really served.
    expect(script).toMatch(/dc-embed-shell/);
    // Both halves of the gate: the rejected request and the accepted one.
    expect(script).toMatch(/OCC_INVITE_KEY/);
    expect(script).toMatch(/iframe/);
    expect(script).toMatch(/\/chat\/occ\//);
  });
});
