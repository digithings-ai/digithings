import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("devkit route isolation", () => {
  it("stays out of the digichat app shell", () => {
    const layout = read("layout.tsx");
    expect(layout).not.toMatch(/import ["'].*globals\.css["']/);
    expect(layout).not.toMatch(/themeInitScript/);
    expect(layout).not.toMatch(/accent-digichat/);
    expect(layout).not.toMatch(/data-theme/);
    expect(layout).not.toMatch(/<Providers/);
    // Shares the baseline assistant-ui template sheet, never app chrome.
    expect(layout).toMatch(/\(baseline\)\/baseline\.css/);
    expect(layout).toMatch(/variable:\s*"--font-geist-mono"/);
  });

  it("is dev-only at the page boundary", () => {
    const page = read("devkit/page.tsx");
    expect(page).toMatch(/NODE_ENV.*production/);
    expect(page).toMatch(/notFound\(\)/);
    expect(page).toMatch(/force-dynamic/);
  });

  it("menu reads from the devkit configs API and stays read-only in P0", () => {
    const client = read("devkit/devkit-client.tsx");
    expect(client).toMatch(/\/api\/devkit\/configs/);
    expect(client).toMatch(/<pre/);
    // No editing affordances yet — textarea/inputs/buttons-that-save land in P1+.
    expect(client).not.toMatch(/<textarea/);
    expect(client).not.toMatch(/\/api\/devkit\/save/);
    expect(client).toContain("read-only");
    expect(client).toMatch(/aria-label="Deployments"/);
  });
});
