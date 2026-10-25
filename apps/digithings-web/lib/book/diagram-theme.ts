"use client";

/**
 * Diagrams are rendered ahead of time, once per theme, with that theme's default
 * tokens baked into the SVG. A palette then changes the accent and the ink, and
 * the baked file cannot know: the arrows and boxes would stay teal while the
 * page around them changed.
 *
 * Rather than rendering 32 palettes × 2 themes, the file is fetched once, its
 * baked colours are swapped for the live tokens, and the result is served to the
 * <img> as a blob. It is the same drawing, drawn in whatever the reader chose.
 */

/**
 * The colours the renderer writes into each theme's file. These are not a
 * palette: they are the exact strings that appear in the SVG, and they have to
 * match `scripts/book/render-diagrams.mjs`. Everything else is read live.
 */
const BAKED = {
  light: {
    accent: "#0c7c71", // canon-allow: baked into the rendered SVG, mirrors tokens.css
    ink: "#14181b", // canon-allow: baked into the rendered SVG, mirrors tokens.css
    inkSoft: "#5c636a", // canon-allow: baked into the rendered SVG, mirrors tokens.css
    surface: "#fbfbf9", // canon-allow: baked into the rendered SVG, mirrors tokens.css
  },
  dark: {
    accent: "#3dd6c4", // canon-allow: baked into the rendered SVG, mirrors tokens.css
    ink: "#eceef0", // canon-allow: baked into the rendered SVG, mirrors tokens.css
    inkSoft: "#9aa0a6", // canon-allow: baked into the rendered SVG, mirrors tokens.css
    surface: "#0a0e0c", // canon-allow: baked into the rendered SVG, mirrors tokens.css
  },
} as const;

type Mode = keyof typeof BAKED;

type Tokens = Record<keyof (typeof BAKED)["light"], string> & { surface2: string };

/**
 * Colours the renderer writes that are not a theme ink or accent: the cluster
 * and node fills, and one flat grey in the sequence diagrams. They were left
 * baked before, which is why a box could stay light on a dark page.
 */
const FILLS: Record<Mode, [string, string][]> = {
  light: [
    ["rgb(244, 244, 241)", "surface2"], // canon-allow: baked into the rendered SVG, mirrors tokens.css --surface-2
    ["#eaeaea", "surface2"], // canon-allow: baked into the rendered SVG, mirrors tokens.css --surface-2
  ],
  dark: [
    ["rgb(23, 26, 30)", "surface2"], // canon-allow: baked into the rendered SVG, mirrors tokens.css --surface-2
    ["#eaeaea", "surface2"], // canon-allow: baked into the rendered SVG, mirrors tokens.css --surface-2
  ],
};

const cache = new Map<string, string>();
/** The original SVG source, so a palette switch never waits on the network. */
const sources = new Map<string, Promise<string>>();

function sourceText(original: string): Promise<string> {
  let pending = sources.get(original);
  if (!pending) {
    pending = fetch(original, { cache: "force-cache" })
      .then((response) => (response.ok ? response.text() : ""))
      .catch(() => "");
    sources.set(original, pending);
  }
  return pending;
}
const objects = new Set<string>();

function tokensFor(mode: Mode): Tokens {
  // A probe carrying the same attributes as <html> resolves the palette's
  // tokens for that mode without changing the page the reader is looking at.
  const probe = document.createElement("div");
  probe.setAttribute("data-theme", mode);
  const palette = document.documentElement.getAttribute("data-palette");
  if (palette) probe.setAttribute("data-palette", palette);
  probe.style.cssText = "position:absolute;left:-10000px;top:0;width:0;height:0";
  document.body.appendChild(probe);
  const style = getComputedStyle(probe);
  const read = (name: string, fallback: string) =>
    style.getPropertyValue(name).trim() || fallback;
  const tokens: Tokens = {
    accent: read("--accent", BAKED[mode].accent),
    ink: read("--ink", BAKED[mode].ink),
    inkSoft: read("--ink-soft", BAKED[mode].inkSoft),
    surface: read("--bg", BAKED[mode].surface),
    surface2: read("--surface-2", mode === "light" ? "rgb(244, 244, 241)" : "rgb(23, 26, 30)"),
  };
  probe.remove();
  return tokens;
}

/** Mermaid writes most fills as rgb() triples and a few as hex; both appear. */
function rgbOf(hex: string): string {
  const value = hex.replace("#", "");
  const full = value.length === 3 ? value.split("").map((c) => c + c).join("") : value;
  const n = Number.parseInt(full, 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

function recolour(svg: string, mode: Mode): string {
  const tokens = tokensFor(mode);
  let out = svg;
  for (const [from, key] of FILLS[mode]) {
    out = out.replaceAll(from, tokens[key as keyof Tokens]);
    out = out.replaceAll(from.toUpperCase(), tokens[key as keyof Tokens]);
  }
  for (const key of Object.keys(BAKED[mode]) as Exclude<keyof Tokens, "surface2">[]) {
    const from = BAKED[mode][key];
    const to = tokens[key];
    out = out.replaceAll(from, to);
    out = out.replaceAll(from.toUpperCase(), to);
    out = out.replaceAll(rgbOf(from), rgbOf(to));
  }
  return out;
}

async function sourceFor(original: string, mode: Mode): Promise<string> {
  // The palette is part of the key: a cached blob made for monokai is the wrong
  // drawing the moment the reader picks matrix, and the page boxes are not
  // re-rendered when that happens.
  const palette = document.documentElement.getAttribute("data-palette") ?? "default";
  const key = `${palette}|${mode}|${original}`;
  const cached = cache.get(key);
  if (cached) return cached;
  const text = await sourceText(original);
  if (!text) return original;
  const url = URL.createObjectURL(new Blob([recolour(text, mode)], { type: "image/svg+xml" }));
  objects.add(url);
  cache.set(key, url);
  return url;
}

/**
 * Point every diagram at the current palette's drawing. Returns a cleanup that
 * releases the blob URLs this run created.
 */
export async function applyDiagramTheme(root: ParentNode = document): Promise<() => void> {
  const images = Array.from(root.querySelectorAll<HTMLImageElement>("img[data-diagram-src]"));
  const created: string[] = [];
  await Promise.all(
    images.map(async (image) => {
      const original = image.dataset.diagramSrc;
      if (!original) return;
      const mode: Mode = image.classList.contains("book-figure__light") ? "light" : "dark";
      const url = await sourceFor(original, mode);
      if (url !== original && image.src !== url) {
        image.src = url;
        created.push(url);
      }
    }),
  );
  return () => {
    // The cache keeps these alive across a theme flip; nothing to release per
    // run, but the hook below may drop them when the figure unmounts.
    void created;
  };
}

/** Release every blob this module has made. For tests and hard resets. */
export function releaseDiagramObjects(): void {
  for (const url of objects) URL.revokeObjectURL(url);
  objects.clear();
  cache.clear();
  sources.clear();
}
