import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const here = __dirname;
const repoRoot = path.resolve(here, "../../../..");

describe("generated design tokens", () => {
  it("matches tokens.css", () => {
    execFileSync("node", ["scripts/gen-design-tokens.mjs", "--check"], {
      cwd: repoRoot,
      stdio: "pipe",
    });
  });

  it("publishes the dark ink as hex and a 24-bit value", () => {
    const source = readFileSync(path.join(repoRoot, "packages/design/tokens.ts"), "utf8");
    expect(source).toContain('"ink": {');
    expect(source).toContain('"hex": "#ECEEF0"');
    expect(source).toContain('"rgb24": 15527664');
  });
});
