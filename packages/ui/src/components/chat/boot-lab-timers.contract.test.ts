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
    const start = css.indexOf(".dboot-lab-tools .aui-tool-fallback-duration");
    expect(start).toBeGreaterThan(-1);
    const rule = css.slice(start, css.indexOf("}", start));
    expect(rule).toContain("margin-left: auto");
    expect(rule).toContain("text-align: right");
  });

  it("renders the timer span inside the scoped list", () => {
    // Scoping depends on both halves: the list container in boot-lab.tsx and
    // the duration span the row anatomy renders.
    expect(source).toContain('className="dboot-lab-tools"');
    expect(source).toContain("aui-tool-fallback-duration");
  });
});
