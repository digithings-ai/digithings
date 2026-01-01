/**
 * Shared terminal theme file. Web persists on `dt-theme` / `dt-palette`
 * (same origin). TUIs share `~/.digithings/theme.json` so a palette picked
 * in one terminal client shows up in the others.
 *
 * Auto follows COLORFGBG when the terminal publishes it (0–7 is a dark
 * background). With no signal, auto is dark.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import {
  isThemePreference,
  normalizePalette,
  type PaletteName,
  type ThemePreference,
} from "./apply-theme";

export type TuiThemePrefs = {
  mode: ThemePreference;
  palette: PaletteName;
};

export const DEFAULT_TUI_PREFS: TuiThemePrefs = { mode: "auto", palette: "default" };

export function themeFilePath(home = homedir()): string {
  return join(home, ".digithings", "theme.json");
}

export function detectTerminalDark(env: NodeJS.ProcessEnv = process.env): boolean | null {
  const raw = env.COLORFGBG;
  if (!raw) return null;
  const bg = Number(String(raw).split(";").pop());
  if (!Number.isFinite(bg)) return null;
  return bg < 8;
}

export function resolveTuiMode(
  mode: ThemePreference,
  terminalDark: boolean | null,
): "dark" | "light" {
  if (mode === "dark" || mode === "light") return mode;
  if (terminalDark === null) return "dark";
  return terminalDark ? "dark" : "light";
}

export function readTuiPrefs(path = themeFilePath()): TuiThemePrefs {
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as { mode?: unknown; palette?: unknown };
    const mode =
      typeof parsed.mode === "string" && isThemePreference(parsed.mode) ? parsed.mode : "auto";
    const palette = normalizePalette(typeof parsed.palette === "string" ? parsed.palette : null);
    return { mode, palette };
  } catch {
    return { ...DEFAULT_TUI_PREFS };
  }
}

export function writeTuiPrefs(prefs: TuiThemePrefs, path = themeFilePath()): void {
  const mode = isThemePreference(prefs.mode) ? prefs.mode : "auto";
  const palette = normalizePalette(prefs.palette);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify({ mode, palette })}\n`, "utf8");
}
