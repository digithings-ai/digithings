import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "bun:test";
import { ACCENT, BG, DANGER, DOWN, HAIR, HAIR_STRONG, INK, MUTE, SOFT, UP, WASH, hairOnBlack } from "./theme";

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      out.push(...sources(path));
      continue;
    }
    if (name.endsWith(".test.ts")) continue;
    if (name.endsWith(".ts") || name.endsWith(".tsx")) out.push(path);
  }
  return out;
}

test("terminal colors are the web desk tokens", () => {
  const tokens = readFileSync(new URL("../../../packages/design/tokens.css", import.meta.url), "utf8");
  const globals = readFileSync(new URL("../../../apps/digiquant-web/app/globals.css", import.meta.url), "utf8");
  const dark = tokens.slice(tokens.indexOf(':root[data-theme="dark"]'), tokens.indexOf(':root[data-theme="light"]'));
  expect(dark).toMatch(/--ink:\s+#ECEEF0/);
  expect(dark).toMatch(/--ink-soft:\s+#9AA0A6/);
  expect(dark).toMatch(/--ink-mute:\s+#7D8389/);
  expect(dark).toMatch(/--accent:\s+#3DD6C4/);
  expect(dark).toMatch(/--down:\s+#E5533E/);
  expect(dark).toMatch(/--danger:\s+#E94959/);
  expect(dark).toMatch(/--hair:\s+rgba\(255,\s*255,\s*255,\s*0\.09\)/);
  expect(dark).toMatch(/--hair-2:\s+rgba\(255,\s*255,\s*255,\s*0\.15\)/);
  expect(globals).toContain("--bg: #000");
  expect(dark).toMatch(/--term-fill:\s+rgba\(255,\s*255,\s*255,\s*0\.05\)/);
  expect(INK).toBe("#ECEEF0");
  expect(SOFT).toBe("#9AA0A6");
  expect(MUTE).toBe("#7D8389");
  expect(ACCENT).toBe("#3DD6C4");
  expect(UP).toBe("#3DD6C4");
  expect(DOWN).toBe("#E5533E");
  expect(DANGER).toBe("#E94959");
  expect(BG).toBe("#000000");
  expect(HAIR).toBe(hairOnBlack(0.09));
  expect(HAIR_STRONG).toBe(hairOnBlack(0.15));
  expect(WASH).toBe(hairOnBlack(0.05));
  expect(HAIR).toBe("#171717");
  expect(HAIR_STRONG).toBe("#262626");
  expect(WASH).toBe("#0D0D0D");
});

test("the terminal does not keep a second palette", () => {
  const forbidden = ["#14120f", "#e7e1d6", "#8a8175", "#3a342c", "#d4b483", "#c47a6a", "#7d9a78"];
  const root = new URL(".", import.meta.url);
  for (const path of sources(root.pathname)) {
    const text = readFileSync(path, "utf8").toLowerCase();
    for (const hex of forbidden) {
      expect(text.includes(hex), `${path} still uses ${hex}`).toBe(false);
    }
  }
});
