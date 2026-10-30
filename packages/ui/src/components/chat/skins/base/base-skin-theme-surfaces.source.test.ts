import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The base and base-assistant-ui skins are the assistant-ui default look on
 * theme tokens, so a tenant or brand theme restyles every surface, including
 * the ones that portal out of the thread (control tooltips, the message
 * timing pane, dialogs). The stock folder is the digichat skin: square
 * corners and its own ink / surface / hair tokens. These checks keep the two
 * apart.
 */
const BASE = __dirname;
const BASE_AUI = path.resolve(__dirname, "../base-assistant-ui");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sources(full);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

/** Stock modules that carry the digichat look; the base path has its own. */
const STOCK_LOOK =
  /from "(?:\.\.\/)+stock\/(?:ui\/[\w-]+|tooltip-icon-button|markdown-text|attachment\.aui)"/;

/** Digichat-skin classes: square corners and the stock ink / surface / hair / danger tokens. */
const DIGICHAT_TOKEN =
  /(?<![\w-])(?:[\w:[\]&>=/-]*:)?(?:bg|text|border|ring|fill)-(?:ink|ink-soft|ink-mute|surface|surface-2|hair|hair-2|danger|on-accent|bg)(?![\w-])|rounded-none/g;

const strip = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

describe("base skin surfaces read the theme, not the digichat skin", () => {
  const files = [...sources(BASE), ...sources(BASE_AUI)];

  it("covers the base path", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it.each(files.map((f) => [path.relative(BASE, f), f]))(
    "%s imports no stock (digichat) primitive",
    (_rel, file) => {
      expect(strip(readFileSync(file, "utf8"))).not.toMatch(STOCK_LOOK);
    },
  );

  it.each(files.map((f) => [path.relative(BASE, f), f]))(
    "%s uses no digichat-skin class",
    (_rel, file) => {
      expect(strip(readFileSync(file, "utf8")).match(DIGICHAT_TOKEN) ?? []).toEqual([]);
    },
  );

  // --accent is the brand fill here (a tenant accent maps onto it), not
  // shadcn's subtle hover tone, so hover / focus / selected fills use --muted.
  it.each(files.map((f) => [path.relative(BASE, f), f]))(
    "%s paints no hover or selected state with the brand accent",
    (_rel, file) => {
      const src = strip(readFileSync(file, "utf8"));
      expect(src.match(/(?<![\w-])(?:[\w[\]=&>.*-]+:)+bg-accent(?![\w-])/g) ?? []).toEqual([]);
    },
  );

  it("the timing pane and control tooltips use the base tooltip", () => {
    const timing = readFileSync(path.join(BASE, "elements/message-timing.aui.tsx"), "utf8");
    expect(timing).toMatch(/from "\.\.\/ui\/tooltip"/);
    const thread = readFileSync(path.join(BASE, "thread.tsx"), "utf8");
    expect(thread).toMatch(/from "\.\/tooltip-icon-button"/);
    const iconButton = readFileSync(path.join(BASE, "tooltip-icon-button.tsx"), "utf8");
    expect(iconButton).toMatch(/from "\.\/ui\/tooltip"/);
    expect(iconButton).toMatch(/from "\.\/ui\/button"/);
  });

  it("the base tooltip is the theme's inverted chip", () => {
    const tooltip = readFileSync(path.join(BASE, "ui/tooltip.tsx"), "utf8");
    expect(tooltip).toContain("rounded-md bg-foreground");
    expect(tooltip).toContain("text-background");
  });
});
