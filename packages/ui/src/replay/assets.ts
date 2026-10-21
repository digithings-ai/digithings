/**
 * Node-only stylesheet + font bundle for the API and the export script.
 * The browser palette path must not import this file (it reads the disk).
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { REPLAY_SHELL_CSS, stripStylesheet } from "./styles";

const here = dirname(fileURLToPath(import.meta.url));

let cached: string | null = null;

/** Chat sheets, palette tokens, and Geist Mono, inlined for a file:// document. */
export function loadReplayStyles(): string {
  if (cached) return cached;
  const uiStyles = join(here, "../styles");
  const design = join(here, "../../../design");
  const fonts = join(here, "fonts");
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
