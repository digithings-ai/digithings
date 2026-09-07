import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, acc);
    else if (/\.(ts|tsx)$/.test(name)) acc.push(p);
  }
  return acc;
}

describe("assistant-ui skin isolation", () => {
  it("Next.js skin modules do not import Ink, Expo, or react-native", () => {
    const files = walk(here);
    const banned =
      /from ["']ink["']|from ["']@assistant-ui\/react-ink|from ["']react-native["']|from ["']expo/;
    for (const file of files) {
      const src = readFileSync(file, "utf8");
      expect(src, file).not.toMatch(banned);
    }
  });

  it("mounts first-party digichat via an explicit branch", () => {
    const index = readFileSync(join(here, "index.tsx"), "utf8");
    expect(index).toMatch(/skin === ["']digichat["']/);
    expect(index).toMatch(/DigichatSkin/);
  });
});
