/**
 * Node-only stylesheet + font bundle for the API and the export script.
 * The browser palette path must not import this file (it reads the disk).
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { REPLAY_SHELL_CSS, stripStylesheet } from "./styles";

let cached: string | null = null;

const MARKER = join("ui", "src", "styles", "chat-aui.css");

/**
 * Where `packages/` sits. From source (tests, the export script) that is next
 * to this file. In the Next standalone server this module is bundled into
 * `.next/`, so fall back to the working directory: the server runs from
 * `apps/digichat` and next.config traces these files into the image.
 */
export function replayPackageCandidates(
  moduleUrl: string | null = import.meta.url,
  cwd: string = process.cwd(),
): string[] {
  const out: string[] = [];
  try {
    if (moduleUrl) out.push(join(dirname(fileURLToPath(moduleUrl)), "../../.."));
  } catch {
    /* not a file URL once bundled */
  }
  out.push(join(cwd, "../../packages"), join(cwd, "packages"));
  return out;
}

export function findReplayPackagesDir(
  candidates: readonly string[] = replayPackageCandidates(),
  exists: (path: string) => boolean = existsSync,
): string {
  const found = candidates.find((dir) => exists(join(dir, MARKER)));
  if (!found) throw new Error("replay stylesheets not found");
  return found;
}

/** Chat sheets, palette tokens, and Geist Mono, inlined for a file:// document. */
export function loadReplayStyles(): string {
  if (cached) return cached;
  const packages = findReplayPackagesDir();
  const uiStyles = join(packages, "ui/src/styles");
  const design = join(packages, "design");
  const fonts = join(packages, "ui/src/replay/fonts");
  const sheets = [
    stripStylesheet(readFileSync(join(design, "palettes.css"), "utf8")),
    stripStylesheet(readFileSync(join(design, "tokens.css"), "utf8")),
    stripStylesheet(readFileSync(join(uiStyles, "chat-aui.css"), "utf8")),
    readFileSync(join(uiStyles, "chat-digichat.css"), "utf8"),
    readFileSync(join(uiStyles, "chat-widgets.css"), "utf8"),
    fontFace(fonts),
    REPLAY_SHELL_CSS,
  ];
  cached = sheets.join("\n");
  return cached;
}

function fontFace(fonts: string): string {
  const regular = readFileSync(join(fonts, "geist-mono-latin-400.woff2"));
  const medium = readFileSync(join(fonts, "geist-mono-latin-500.woff2"));
  return `
@font-face {
  font-family: "Geist Mono";
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url("data:font/woff2;base64,${regular.toString("base64")}") format("woff2");
}
@font-face {
  font-family: "Geist Mono";
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url("data:font/woff2;base64,${medium.toString("base64")}") format("woff2");
}
:root {
  --font-mono-face: "Geist Mono";
  --font-geist-mono: "Geist Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --font-mono: "Geist Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
`;
}
