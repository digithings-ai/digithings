import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const here = __dirname;
const designDir = path.resolve(here, "../../../design");
const tokens = readFileSync(path.join(designDir, "tokens.css"), "utf8");

function themeBlock(theme: "dark" | "light"): string {
  const start = tokens.indexOf(`:root[data-theme="${theme}"]`);
  if (start === -1) throw new Error(`missing ${theme} block`);
  const open = tokens.indexOf("{", start);
  const close = tokens.indexOf("\n}", open);
  return tokens.slice(open, close);
}

const STATUS = ["open", "add", "trim", "exit", "closed"] as const;

describe("semantic status tokens", () => {
  for (const theme of ["dark", "light"] as const) {
    it(`declares every status role in the ${theme} theme`, () => {
      const block = themeBlock(theme);
      for (const role of STATUS) {
        expect(block, role).toMatch(new RegExp(`--status-${role}\\s*:\\s*#[0-9A-Fa-f]{6}`));
      }
    });

    it(`keeps OPEN/ADD/CLOSED distinct from --accent in ${theme}`, () => {
      const block = themeBlock(theme);
      const accent = /--accent:\s*(#[0-9A-Fa-f]{6})/.exec(block)?.[1];
      expect(accent).toBeTruthy();
      for (const role of ["open", "add", "closed"] as const) {
        const value = new RegExp(`--status-${role}:\\s*(#[0-9A-Fa-f]{6})`).exec(block)?.[1];
        expect(value, role).toBeTruthy();
        expect(value, role).not.toBe(accent);
      }
    });
  }
});

describe("additive duration scales", () => {
  it("declares the interaction and settle scales without touching motion.json's trio", () => {
    expect(tokens).toMatch(/--dur-tap:\s*120ms;/);
    expect(tokens).toMatch(/--dur-arrive:\s*600ms;/);
    // The generated three remain the motion.json mirror.
    expect(tokens).toMatch(/--dur-fast:\s*120ms;/);
    expect(tokens).toMatch(/--dur:\s*240ms;/);
    expect(tokens).toMatch(/--dur-slow:\s*600ms;/);
  });
});
