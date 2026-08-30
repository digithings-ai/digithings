/**
 * Account reference copy is a layout catalog, not a task brief.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const accountRef = join(here, "../../../../reference/components/account");
const accountPage = join(here, "../../../../reference/app/account/page.tsx");

const FORBIDDEN = [
  /reply\s*[abc]/i,
  /pick a sign-in/i,
  /olympus kicker/i,
  /oauth-first \(olympus\)/i,
  /oauth first \(olympus\)/i,
  /not selected/i,
  /· selected/i,
  /is selected/i,
  /selected login/i,
  /product card/i,
  /data-proposal/i,
  /data-selected/i,
  /letter:\s*"A"/,
  /\bincumbent\b/i,
  /owner pick/i,
  /owner hop/i,
  /dashboard import waits/i,
  /rejected specimen/i,
  /live here first/i,
  /chosen product/i,
  /\btoday\b/i,
];

function load(file: string): string {
  const path = file.startsWith("/") ? file : join(accountRef, file);
  return readFileSync(path, "utf8");
}

describe("account auth catalog copy", () => {
  it("catalog uses quiet layout names and no task brief", () => {
    const src = load("auth-card-proposals.tsx");
    expect(src).toContain('"compact"');
    expect(src).toContain('"icons-first"');
    expect(src).toContain('"desk"');
    expect(src).toContain("{`// ${id}`}");
    expect(src).toContain('mode="signin"');
    expect(src).toContain('mode="signup"');
    expect(src).toContain("Three layouts, one card.");
    for (const pattern of FORBIDDEN) {
      expect(src).not.toMatch(pattern);
    }
  });

  it("account page hero is a family catalog, not a sprint note", () => {
    const src = load(accountPage);
    expect(src).toContain("three layouts");
    expect(src).not.toContain("selected login");
    for (const pattern of FORBIDDEN) {
      expect(src).not.toMatch(pattern);
    }
  });

  it("login and sign-up specimen labels omit the olympus task tag", () => {
    const login = load("login-card.tsx");
    const signup = load("signup-card.tsx");
    expect(login).toContain("// oauth first");
    expect(signup).toContain("// oauth first");
    expect(login).not.toMatch(/oauth first \(olympus\)/i);
    expect(signup).not.toMatch(/oauth first \(olympus\)/i);
    expect(login).not.toMatch(/oauth-first \(olympus\)/i);
    expect(signup).not.toMatch(/incumbent/i);
    expect(login).not.toMatch(/\bolympus\b/i);
    expect(signup).not.toMatch(/\bolympus\b/i);
    const session = load("session-card.tsx");
    expect(session).not.toMatch(/\bolympus\b/i);
  });
});
