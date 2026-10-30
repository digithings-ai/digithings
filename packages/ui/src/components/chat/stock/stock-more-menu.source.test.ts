import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The stock skin's "…" menu is portaled to <body> and its `bg-surface-2`
// class has no Tailwind colour behind it in DigiChat (chat-aui.css declares
// no --color-surface-2), so chat-stock-menu.css gives it its background,
// border, shadow and radius. These pin the pieces that rule depends on.
const thread = readFileSync(join(__dirname, "thread.aui.tsx"), "utf8");
const css = readFileSync(join(__dirname, "../../../styles/chat-stock-menu.css"), "utf8");
const MENU = ".aui-action-bar-more-content.bg-surface-2";

function rule(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `rule for ${selector}`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf("}", start));
}

describe("stock skin More menu", () => {
  it("loads the menu stylesheet with the stock thread", () => {
    expect(thread).toMatch(/^import "\.\.\/\.\.\/\.\.\/styles\/chat-stock-menu\.css";$/m);
  });

  it("keeps the class pair the stylesheet keys on", () => {
    const menus = thread.match(/"aui-action-bar-more-content[^"]*"/g) ?? [];
    expect(menus.length).toBeGreaterThan(0);
    for (const cls of menus) expect(cls.split(/\s+/)).toContain("bg-surface-2");
  });

  it("draws a solid, rounded panel from the theme tokens", () => {
    const body = rule(MENU);
    expect(body).toMatch(/background-color:\s*var\(--surface-2,\s*var\(--popover/);
    expect(body).toMatch(/border-radius:\s*calc\(var\(--radius/);
    expect(body).toMatch(/box-shadow:/);
    expect(body).not.toMatch(/transparent/);
  });

  it("stays unlayered so it outranks the rounded-none utility", () => {
    expect(css).not.toMatch(/@layer/);
  });

  it("only targets the stock menu", () => {
    const selectors = css.replace(/\/\*[\s\S]*?\*\//g, "").match(/^[^\s{}][^{}]*(?=\{)/gm) ?? [];
    expect(selectors.length).toBeGreaterThan(0);
    for (const s of selectors) expect(s.trim().startsWith(MENU)).toBe(true);
  });
});
