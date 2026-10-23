import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { detectTerminalDark, readTuiPrefs, resolveTuiMode, writeTuiPrefs } from "./tui-prefs";

describe("tui theme file", () => {
  it("round-trips through a temp path", () => {
    const dir = mkdtempSync(join(tmpdir(), "dt-theme-"));
    const path = join(dir, "nested", "theme.json");
    writeTuiPrefs({ mode: "light", palette: "dracula" }, path);
    expect(readTuiPrefs(path)).toEqual({ mode: "light", palette: "dracula" });
  });

  it("drops an unknown palette back to default", () => {
    const dir = mkdtempSync(join(tmpdir(), "dt-theme-"));
    const path = join(dir, "theme.json");
    writeFileSync(path, `${JSON.stringify({ mode: "auto", palette: "not-a-palette" })}\n`);
    expect(readTuiPrefs(path)).toEqual({ mode: "auto", palette: "default" });
  });

  it("reads COLORFGBG and falls back to dark", () => {
    expect(detectTerminalDark({ COLORFGBG: "15;0" })).toBe(true);
    expect(detectTerminalDark({ COLORFGBG: "0;15" })).toBe(false);
    expect(detectTerminalDark({})).toBeNull();
    expect(resolveTuiMode("auto", null)).toBe("dark");
    expect(resolveTuiMode("auto", false)).toBe("light");
    expect(resolveTuiMode("light", true)).toBe("light");
  });
});
