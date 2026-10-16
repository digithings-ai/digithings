/**
 * Enter on /compact must run the palette execute. That path serializes the
 * thread and queues a summary. executeDef only resets prefs.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const src = readFileSync(join(__dirname, "digichat.tsx"), "utf8");

describe("DigichatSkin /compact submit", () => {
  it("runs the palette compact execute on Enter", () => {
    const runAt = src.indexOf('action.kind === "run"');
    const gateAt = src.indexOf("gateSubmit", runAt);
    const runBranch = src.slice(runAt, gateAt);
    expect(runBranch).toContain('action.command.id === "compact"');
    expect(runBranch).toContain('commands.find((command) => command.id === "compact")');
    expect(runBranch).toContain("compact.execute()");
    expect(src).toMatch(/copyExport, extra, commands\]/);
  });
});
