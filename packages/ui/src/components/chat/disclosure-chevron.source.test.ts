import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * One caret. Closed points right (rotate 0). Open points down (rotate 90),
 * on the icon svg only. The wrapper, the trigger, and the label do not
 * transform. A child combinator on the trigger, so an open chain does not
 * rotate the closed rows nested inside it.
 */
const here = dirname(fileURLToPath(import.meta.url));
const stylesDir = join(here, "..", "..", "styles");

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

function readStyle(name: string): string {
  return readFileSync(join(stylesDir, name), "utf8");
}

/** Style rules, comments removed. Skips at-rule headers. */
function rules(css: string): Array<[string, string]> {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const found: Array<[string, string]> = [];
  for (const match of stripped.matchAll(/([^{}@]+)\{([^}]*)\}/g)) {
    const sel = match[1].trim();
    if (!sel || sel.startsWith("@")) continue;
    found.push([sel, match[2]]);
  }
  return found;
}

const ROWS = [
  "stock/tool-group.aui.tsx",
  "stock/tool-fallback.aui.tsx",
  "stock/reasoning.tsx",
  "gallery-thread/reasoning.tsx",
  "gallery-thread/work-chain.tsx",
];

describe("shared disclosure chevron", () => {
  it("is the only caret on every trace row, with no per-row rotate", () => {
    for (const rel of ROWS) {
      const source = read(rel);
      expect(source, rel).toContain("DisclosureChevron");
      expect(source, rel).not.toMatch(/-rotate-90|group-data-open\/trigger:rotate-0/);
      expect(source, rel).not.toContain('data-slot="tool-group-trigger-chevron"');
      expect(source, rel).not.toContain('data-slot="reasoning-trigger-chevron"');
      expect(source, rel).not.toContain('data-slot="tool-fallback-trigger-chevron"');
      expect(source, rel).not.toContain('data-slot="aui_work-chain-chevron"');
    }
  });

  it("rotates only the icon svg, from that row's open state", () => {
    for (const sheet of ["chat-digichat.css", "chat-aui.css"]) {
      const css = readStyle(sheet);
      const icon = '[data-slot="dot-matrix-grid"]';
      expect(css, sheet).toContain(`[data-slot="disclosure-chevron"] ${icon}`);
      expect(css, sheet).toContain("transform: rotate(0deg)");
      expect(css, sheet).toContain("transform: rotate(90deg)");
      expect(css, sheet).toContain(
        `[aria-expanded="true"] > [data-slot="disclosure-chevron"] ${icon}`,
      );
      expect(css, sheet).toContain(
        `[data-panel-open] > [data-slot="disclosure-chevron"] ${icon}`,
      );
      expect(css, sheet).toContain(
        `[data-state="open"] > [data-slot="disclosure-chevron"] ${icon}`,
      );
      expect(css, sheet).not.toMatch(
        /\[data-state="open"\]\s+\[data-slot="disclosure-chevron"\]/,
      );
      expect(css, sheet).not.toMatch(/\[data-open\]\s+\[data-slot="disclosure-chevron"\]/);
      expect(css, sheet).toContain("transition: transform 150ms ease");
      expect(css, sheet).toContain("width: 0.55rem");

      const sheetRules = rules(css);
      const turned = sheetRules.filter(([, body]) => /transform:\s*rotate\(90deg\)/.test(body));
      expect(turned.length, sheet).toBeGreaterThan(0);
      for (const [sel] of turned) {
        expect(sel, sheet).toContain(icon);
        expect(sel, sheet).not.toMatch(
          /aui_work-status-label|tool-group-trigger-label|reasoning-trigger-label|tool-fallback-trigger-label/,
        );
        const parts = sel.replace(/:is\([^)]*\)/g, ":is()").split(",");
        for (const part of parts) {
          expect(part.trim().endsWith(icon), `${sheet}: ${part}`).toBe(true);
        }
      }

      for (const [sel, body] of sheetRules) {
        if (!sel.includes('[data-slot="disclosure-chevron"]') || sel.includes(icon)) continue;
        expect(body, `${sheet}: ${sel}`).not.toMatch(/transform:\s*rotate/);
      }

      const reduced = css.slice(css.indexOf("prefers-reduced-motion: reduce"));
      expect(reduced, sheet).toContain(icon);
      expect(reduced, sheet).toMatch(/transition:\s*none/);
    }
  });
});
