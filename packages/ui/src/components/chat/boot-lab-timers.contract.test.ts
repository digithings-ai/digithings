import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The tool-chain boot rows carry their own timer. The digichat skin lets the
 * label size to its text, so without a rule of its own the timer would sit
 * right after the label and the column would jitter row to row. The rule is
 * scoped to the boot list so it cannot move a timer in the transcript.
 */
const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "../../styles/digichat-boot-loader.css"), "utf8");
const source = readFileSync(join(here, "boot-lab.tsx"), "utf8");

describe("boot-lab tool-chain timers", () => {
  it("right-aligns the per-row timer inside the tool-chain list", () => {
    const start = css.indexOf(".dboot-lab .dboot-lab-tools .aui-tool-fallback-duration");
    expect(start).toBeGreaterThan(-1);
    const rule = css.slice(start, css.indexOf("}", start));
    expect(rule).toContain("margin-left: auto");
    expect(rule).toContain("flex-shrink: 0");
    expect(rule).toContain("text-align: right");
  });

  it("stretches boot rows to the list so the timers share one column", () => {
    // The digichat skin sets trace rows to `width: fit-content`
    // (chat-digichat.css, 0-2-0); the boot rule must out-rank it (0-3-0).
    const start = css.indexOf('.dboot-lab .dboot-lab-tools [data-slot="tool-fallback-trigger"]');
    expect(start).toBeGreaterThan(-1);
    const rule = css.slice(start, css.indexOf("}", start));
    expect(rule).toContain("width: 100%");
  });

  it("leaves transcript tool rows alone", () => {
    // Every new selector is scoped under the boot list.
    const added = css.match(/^[^\n{]*aui-tool-fallback-duration[^\n{]*\{/gm) ?? [];
    for (const sel of added) expect(sel).toContain(".dboot-lab-tools");
  });

  it("renders the timer span inside the scoped list", () => {
    // Scoping depends on both halves: the list container in boot-lab.tsx and
    // the duration span the row anatomy renders.
    expect(source).toContain('className="dboot-lab-tools"');
    expect(source).toContain("aui-tool-fallback-duration");
  });
});
