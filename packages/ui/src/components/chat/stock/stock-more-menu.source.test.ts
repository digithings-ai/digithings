import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The stock skin's "…" menu is portaled to <body>. chat-aui.css emits
// `bg-surface-2` only inside the stock thread and its marked portals, so
// chat-stock-menu.css gives the menu its own background, border, shadow and
// keyboard focus ring. These pin the pieces those rules depend on.
const thread = readFileSync(join(__dirname, "thread.aui.tsx"), "utf8");
const css = readFileSync(join(__dirname, "../../../styles/chat-stock-menu.css"), "utf8");
const bridge = readFileSync(join(__dirname, "../../../styles/chat-aui.css"), "utf8");
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

  it("draws a solid panel from the theme tokens", () => {
    const body = rule(MENU);
    expect(body).toMatch(/background-color:\s*var\(--surface-2,\s*var\(--popover/);
    expect(body).toMatch(/box-shadow:/);
    expect(body).not.toMatch(/transparent/);
  });

  it("uses assistant-ui's menu radii: rounded-xl panel, rounded-lg rows", () => {
    const menu = thread.match(/"aui-action-bar-more-content[^"]*"/)?.[0] ?? "";
    const item = thread.match(/"aui-action-bar-more-item[^"]*"/)?.[0] ?? "";
    expect(menu.split(/\s+/)).toContain("rounded-xl");
    expect(item.split(/\s+/)).toContain("rounded-lg");
    expect(`${menu} ${item}`).not.toContain("rounded-none");
  });

  it("emits bg-surface-2 only inside the stock thread and its portals", () => {
    // Other skins and host chrome reuse stock parts that ask for bg-surface-2
    // and keep their own background; outside the scope the class matches no
    // declaration. Never page-wide (DIG-6110), no theme colour, no :has().
    const theme = bridge.slice(bridge.indexOf("@theme inline {"), bridge.indexOf("}", bridge.indexOf("@theme inline {")));
    expect(theme).not.toMatch(/--color-surface-2/);
    expect(bridge).toMatch(
      /@utility bg-surface-\* \{\s*&:where\(\[data-stock-thread\], \[data-stock-thread\] \*, \[data-stock-portal\], \[data-stock-portal\] \*\) \{\s*--stock-surface-step: --value\("2"\);\s*background-color: var\(--surface-2\);/,
    );
    expect(bridge).not.toMatch(/:has\([^)]*data-stock/);
    expect(thread).toMatch(/aui-thread-root[^"]*"\s*data-stock-thread=""/);
  });

  it("rings the keyboard-focused row, not just a tint", () => {
    const body = rule(`${MENU} .aui-action-bar-more-item:focus-visible`);
    expect(body).toMatch(/outline:\s*2px solid var\(--ink-soft/);
  });

  it("stays unlayered so it outranks the skin's own surface utilities", () => {
    expect(css).not.toMatch(/@layer/);
  });

  it("only targets the stock menu", () => {
    const selectors = css.replace(/\/\*[\s\S]*?\*\//g, "").match(/^[^\s{}][^{}]*(?=\{)/gm) ?? [];
    expect(selectors.length).toBeGreaterThan(0);
    for (const s of selectors) expect(s.trim().startsWith(MENU)).toBe(true);
  });
});
