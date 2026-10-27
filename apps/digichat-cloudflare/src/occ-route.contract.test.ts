import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * Route ownership for the invite-gated OCC shell.
 *
 * DIG-3585 pinned BOTH workers so a cutover or a rollback could not drop the
 * gate. Since 2026-10-19 exactly ONE worker declares the route — the digichat
 * one that also holds OCC_INVITE_KEY. (That day's reason, keeping OCC off the
 * shared platform, was superseded on 2026-10-27: OCC is a tenant of the
 * shared stack, isolated by the gate. The single route owner stands.)
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

  it("the post-deploy smoke checks the page's API calls with only the cookie (G1)", () => {
    const script = readFileSync(join(repoRoot, "scripts/smoke_occ_invite_gate.sh"), "utf8");
    // The cookie must reach /chat/api/*, so it is scoped to /chat.
    expect(script).toMatch(/\$3 == "\/chat"/);
    // Tenant binding: cookie-only from the OCC page is occ; without the
    // cookie, or from a house page, it never is.
    expect(script).toMatch(/\/chat\/api\/embed\/tenant-config/);
    expect(script).toMatch(/!= "occ"/);
    expect(script).toMatch(/= "occ"/);
    // One real turn, through the same cookie jar, never a token.
    expect(script).toMatch(/\/chat\/api\/chat/);
    expect(script).toMatch(/-b "\$jar"[\s\S]*--data "\$msg" "\$TURN_URL"/);
    // The key is read from the environment only and never put on a turn.
    expect(script).not.toMatch(/x-embed-token/i);
  });

  it(`${OCC_ROUTE_OWNER} keeps query strings out of Workers Logs and traces`, () => {
    // The invite link carries the key as ?token= on its first hit, and the
    // legacy /embed door carries it the same way. The invocation log records
    // the request URL, so the query string is redacted for this Worker.
    const toml = readFileSync(join(repoRoot, OCC_ROUTE_OWNER), "utf8");
    const section = toml.match(/^\[observability\]\n([\s\S]*?)(?=^\[)/m);
    expect(section, "[observability] section").not.toBeNull();
    expect(section![1]).toMatch(/^redact_query_string\s*=\s*true\s*$/m);
  });
});
