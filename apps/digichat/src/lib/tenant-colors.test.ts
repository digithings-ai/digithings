import { describe, expect, it } from "vitest";

import { parseTenantColors, tenantColorVars, tenantColorsCss } from "./tenant-colors";
import { TENANT_HEADING_FONT_CSS } from "./tenant-fonts";

const LIGHT = {
  background: "#ffffff",
  surface: "#f4f4f4",
  text: "#222222",
  muted: "#666666",
  border: "#e0e0e0",
  accent: "#0a66c2",
  onAccent: "#ffffff",
  link: "#0a58a8",
  userBubble: "#e8f1fb",
  userBubbleText: "#222222",
  focusRing: "#0a58a8",
};

describe("tenant colors", () => {
  it("is absent when the tenant sets none", () => {
    expect(parseTenantColors(undefined, "t")).toBeUndefined();
    expect(tenantColorsCss(null)).toBe("");
    expect(tenantColorsCss({})).toBe("");
    expect(tenantColorsCss({ light: {} })).toBe("");
  });

  it("accepts #rrggbb per mode and per key", () => {
    expect(parseTenantColors({ light: LIGHT, dark: { background: "#1b1b1b" } }, "t")).toEqual({
      light: LIGHT,
      dark: { background: "#1b1b1b" },
    });
  });

  it("refuses anything but a known key with a #rrggbb value", () => {
    expect(() => parseTenantColors({ light: { background: "red" } }, "t")).toThrow(/colors\.light\.background/);
    expect(() => parseTenantColors({ light: { background: "#fff" } }, "t")).toThrow(/colors\.light\.background/);
    expect(() => parseTenantColors({ light: { background: "#ffffff;}body{display:none" } }, "t")).toThrow();
    expect(() => parseTenantColors({ light: { link: "var(--x)" } }, "t")).toThrow(/colors\.light\.link/);
    expect(() => parseTenantColors({ light: { glow: "#ffffff" } }, "t")).toThrow();
    expect(() => parseTenantColors({ sepia: {} }, "t")).toThrow();
  });

  it("maps each key to the skin variables it owns, and only set keys", () => {
    const vars = Object.fromEntries(tenantColorVars({ background: "#101010", link: "#3366cc" }));
    expect(vars).toEqual({
      "--bg": "#101010",
      "--embed-canvas": "#101010",
      "--background": "#101010",
      "--term-bg": "#101010",
      "--chat-skin-canvas": "#101010",
      "--tenant-link": "#3366cc",
    });
  });

  it("scopes each set to its own document theme", () => {
    const css = tenantColorsCss({ light: LIGHT, dark: { background: "#1b1b1b", userBubble: "#333a44" } });
    expect(css.startsWith(':root:root[data-theme="light"]:not([data-palette]),')).toBe(true);
    expect(css).toContain('[data-stock-product]{--bg:#1b1b1b;');
    expect(css).toContain("--background:#ffffff");
    expect(css).toContain("--background:#1b1b1b");
    expect(css).toContain(':root:root[data-theme="light"]:not([data-palette]) .aui-md-a{color:var(--tenant-link)}');
    expect(css).toContain(':root:root[data-theme="dark"]:not([data-palette]) .aui-user-message-content{background:var(--tenant-user-bubble);}');
    expect(css).toContain(':root:root[data-theme="light"]:not([data-palette]) :focus-visible{outline-color:var(--tenant-focus-ring)}');
    // No link rule in dark: the dark set has no link.
    expect(css).not.toContain(':root:root[data-theme="dark"]:not([data-palette]) .aui-md-a');
  });

  it("only ever writes validated hex values into the stylesheet", () => {
    const css = tenantColorsCss({ light: LIGHT });
    const values = [...css.matchAll(/:(#[0-9a-fA-F]+)[;}]/g)].map((m) => m[1]);
    expect(values.length).toBeGreaterThan(0);
    expect(values.every((v) => /^#[0-9a-fA-F]{6}$/.test(v))).toBe(true);
    expect(css).not.toMatch(/url\(|@import|expression/);
  });

  it("heading-font rule is scoped to the tenant wrapper attribute", () => {
    expect(TENANT_HEADING_FONT_CSS.startsWith("[data-tenant-heading-font] ")).toBe(true);
    expect(TENANT_HEADING_FONT_CSS).toContain("font-family:var(--font-heading)");
  });
});

describe("tenant surface reaches the shadcn hover and secondary fills", () => {
  it("derives --muted and --secondary off the surface toward the text, distinct from --popover", () => {
    const vars = Object.fromEntries(tenantColorVars({ surface: "#3d3d3d", text: "#fafafa" }));
    expect(vars["--popover"]).toBe("#3d3d3d");
    expect(vars["--muted"]).toBe("color-mix(in oklch, #3d3d3d 92%, #fafafa)");
    expect(vars["--secondary"]).toBe(vars["--muted"]);
    expect(vars["--muted"]).not.toBe(vars["--popover"]);
    expect(vars["--secondary-foreground"]).toBe("#fafafa");
  });

  it("mixes toward the theme foreground when the tenant sets no text colour", () => {
    const vars = Object.fromEntries(tenantColorVars({ surface: "#f6f6f6" }));
    expect(vars["--muted"]).toBe("color-mix(in oklch, #f6f6f6 92%, var(--foreground))");
    expect(vars["--muted"]).not.toBe(vars["--popover"]);
  });

  it("sets no --muted without a surface", () => {
    expect(Object.fromEntries(tenantColorVars({ text: "#111111" }))["--muted"]).toBeUndefined();
  });
});
