/**
 * Enter on /compact must run the palette execute. That path serializes the
 * thread and queues a summary. executeDef only resets prefs. The submit
 * handling lives in the skin-agnostic palette hook the digichat skin uses.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const src = readFileSync(
  join(__dirname, "../stock/skin-slash-palette.tsx"),
  "utf8",
);
const skin = readFileSync(join(__dirname, "digichat.tsx"), "utf8");

describe("DigichatSkin /compact submit", () => {
  it("runs the palette compact execute on Enter", () => {
    const runAt = src.indexOf('action.kind === "run"');
    const gateAt = src.indexOf("return false", runAt);
    const runBranch = src.slice(runAt, gateAt);
    expect(runBranch).toContain('action.command.id === "compact"');
    expect(runBranch).toContain('commands.find((command) => command.id === "compact")');
    expect(runBranch).toContain("compact.execute()");
    expect(runBranch).toContain("applyExportSlash(action.arg");
    expect(src).toMatch(/copyExport, extra, commands\]/);
    expect(skin).toMatch(/useSkinSlashPalette\(/);
    expect(skin).toMatch(/if \(paletteSubmit\(event\)\) return;\s*gateSubmit\?\.\(event\);/);
  });
});
