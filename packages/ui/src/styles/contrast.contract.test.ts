import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Single `__dirname` usage: the tsconfig carries no node types, so this file
// reports TS2304 for it (pre-existing, like its node: imports — see
// web-theme.test.ts).
const here = __dirname;

const tokens = readFileSync(
  path.resolve(here, "../../../design/tokens.css"),
  "utf8",
);
const webTheme = readFileSync(path.resolve(here, "web-theme.css"), "utf8");
const finance = readFileSync(path.resolve(here, "finance-tearsheet.css"), "utf8");
const stages = readFileSync(path.resolve(here, "stages.css"), "utf8");
const terminal = readFileSync(
  path.resolve(
    here,
    "../../../../apps/reference/app/(gallery)/(chat)/terminal/terminal.css",
  ),
  "utf8",
);

/** Slice out one `:root[data-theme="X"] { … }` block (top-level braces). */
function themeBlock(theme: "dark" | "light"): string {
  const start = tokens.indexOf(`:root[data-theme="${theme}"]`);
  expect(start, `tokens.css has a ${theme} block`).toBeGreaterThan(-1);
  let depth = 0;
  let i = tokens.indexOf("{", start);
  const open = i;
  for (; i < tokens.length; i++) {
    if (tokens[i] === "{") depth++;
    else if (tokens[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  return tokens.slice(open, i + 1);
}

/** The bare `:root { … }` block, which carries the fallback per-module accents
 *  that a theme block may not override (only seven liveries are deepened for
 *  light; the rest keep their :root hue in both themes). */
function rootBlock(): string {
  const start = tokens.indexOf(":root {");
  expect(start, "tokens.css has a :root block").toBeGreaterThan(-1);
  let depth = 0;
  let i = tokens.indexOf("{", start);
  const open = i;
  for (; i < tokens.length; i++) {
    if (tokens[i] === "{") depth++;
    else if (tokens[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  return tokens.slice(open, i + 1);
}

/** Resolve a `--name: #hex;` (or a one-hop `var(--other)`) out of a block,
 *  falling back to the bare :root block when the theme block omits it. */
function hexToken(block: string, name: string): string {
  const find = (src: string, key: string) =>
    src.match(new RegExp(`--${key}:\\s*([^;]+);`))?.[1]?.trim();
  let value = find(block, name) ?? find(rootBlock(), name);
  expect(value, `--${name} defined`).toBeDefined();
  const asVar = value!.match(/^var\(--([a-z-]+)\)$/);
  if (asVar) {
    const nested = find(block, asVar[1]) ?? find(rootBlock(), asVar[1]);
    expect(nested, `--${asVar[1]} (referenced by --${name}) defined`).toBeDefined();
    value = nested!;
  }
  return value!;
}

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  expect(h, `${hex} is a 6-digit hex`).toMatch(/^[0-9a-fA-F]{6}$/);
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function luminance([r, g, b]: [number, number, number]): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: string, b: string): number {
  const la = luminance(rgb(a));
  const lb = luminance(rgb(b));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Composite `fg` at `alpha` over `bg` (both hex). */
function over(fg: string, alpha: number, bg: string): string {
  const f = rgb(fg);
  const b = rgb(bg);
  const c = f.map((v, i) => v * alpha + b[i] * (1 - alpha));
  return "#" + c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
}

/** color-mix(in srgb, a t%, b) — the CSS mix this codebase uses. */
function mix(a: string, t: number, b: string): string {
  return over(a, t, b);
}

const AA_TEXT = 4.5;

describe("canon contrast contract (#4306, canon-audit S2)", () => {
  const dark = themeBlock("dark");
  const light = themeBlock("light");

  describe("money tokens as small text (light theme)", () => {
    // Badge warn/down, .dg-tier.t-roadmap and .is-neg all read these tokens as
    // 12–16px text. They are the tightest against --surface-2.
    const grounds = ["surface", "surface-2", "bg"] as const;
    for (const theme of ["light", "dark"] as const) {
      const block = theme === "light" ? light : dark;
      for (const token of ["warn", "down"] as const) {
        for (const ground of grounds) {
          it(`--${token} on --${ground} (${theme}) clears AA`, () => {
            const ratio = contrast(
              hexToken(block, token),
              hexToken(block, ground),
            );
            expect(ratio).toBeGreaterThanOrEqual(AA_TEXT);
          });
        }
      }
    }
  });

  describe("accent-as-small-text (kicker, ts-seg, ns-node)", () => {
    // The shared recipe: color-mix(in srgb, var(--accent) 70%, var(--ink)).
    // Every light-theme module livery must clear AA on paper once mixed.
    const lightLiveries: Record<string, string> = {
      "accent (generic)": hexToken(light, "accent"),
      "accent-digigraph": hexToken(light, "accent-digigraph"),
      "accent-digiquant": hexToken(light, "accent-digiquant"),
      "accent-digisearch": hexToken(light, "accent-digisearch"),
      "accent-digismith": hexToken(light, "accent-digismith"),
      "accent-digibase": hexToken(light, "accent-digibase"),
      "accent-digivault": hexToken(light, "accent-digivault"),
      "accent-digilink": hexToken(light, "accent-digilink"),
      "accent-digichat": hexToken(light, "accent-digichat"),
      "accent-digikey": hexToken(light, "accent-digikey"),
      "accent-digiclaw": hexToken(light, "accent-digiclaw"),
      "accent-digistore": hexToken(light, "accent-digistore"),
    };
    const lightInk = hexToken(light, "ink");
    const paper = hexToken(light, "surface");
    for (const [name, accent] of Object.entries(lightLiveries)) {
      it(`${name} mixed toward ink clears AA on paper`, () => {
        const text = mix(accent, 0.7, lightInk);
        expect(contrast(text, paper)).toBeGreaterThanOrEqual(AA_TEXT);
      });
    }

    it("the accent-as-text recipe is the one the stylesheets use", () => {
      const recipe = "color-mix(in srgb, var(--accent) 70%, var(--ink))";
      for (const [file, css] of [
        ["finance-tearsheet.css", finance],
        ["stages.css", stages],
      ] as const) {
        expect(css, `${file} uses the shared recipe`).toContain(recipe);
      }
    });

    it(".ts-seg-btn.is-active does not wear the raw accent", () => {
      const rule = finance.match(/\.ts-seg-btn\.is-active\s*\{[^}]*\}/)?.[0];
      expect(rule).toBeDefined();
      expect(rule).not.toContain("color: var(--accent);");
    });

    it(".ns-node does not wear the raw accent", () => {
      const rule = stages.match(/\.ns-node\s*\{[^}]*\}/)?.[0];
      expect(rule).toBeDefined();
      expect(rule).not.toContain("color: var(--accent);");
    });
  });

  describe("returns-matrix cell ink (dark theme)", () => {
    // ReturnsMatrix paints color-mix(in srgb, tone pct%, transparent) over
    // --surface and selects --heat-ink, or --heat-ink-strong past the boundary.
    const darkSurface = hexToken(dark, "surface");
    const ink = hexToken(dark, "heat-ink");
    const inkStrong = hexToken(dark, "heat-ink-strong");
    const tones = { up: hexToken(dark, "up"), down: hexToken(dark, "down") };

    const pctFor = (mag: number) => Math.round(14 + Math.min(1, mag) * 58);
    // The CSS/TS boundary: the up tone switches to the strong ink at pct>=57.
    const STRONG_FROM = 57;

    for (const [name, tone] of Object.entries(tones)) {
      it(`--${name} wash keeps every 14–72% step >= AA`, () => {
        let worst = Infinity;
        for (let pct = 14; pct <= 72; pct++) {
          const fill = over(tone, pct / 100, darkSurface);
          const strong = name === "up" && pct >= STRONG_FROM;
          worst = Math.min(worst, contrast(strong ? inkStrong : ink, fill));
        }
        expect(worst).toBeGreaterThanOrEqual(AA_TEXT);
      });
    }

    it("light theme aliases both heat inks to --ink (washes are dark on paper)", () => {
      expect(hexToken(light, "heat-ink")).toBe(hexToken(light, "ink"));
      expect(hexToken(light, "heat-ink-strong")).toBe(hexToken(light, "ink"));
      const lightSurface = hexToken(light, "surface");
      const lightInk = hexToken(light, "ink");
      for (const tone of [hexToken(light, "up"), hexToken(light, "down")]) {
        let worst = Infinity;
        for (let pct = 14; pct <= 72; pct++) {
          worst = Math.min(
            worst,
            contrast(lightInk, over(tone, pct / 100, lightSurface)),
          );
        }
        expect(worst).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it("the bridge exposes the heat-ink utilities", () => {
      expect(webTheme).toContain("--color-heat-ink: var(--heat-ink);");
      expect(webTheme).toContain(
        "--color-heat-ink-strong: var(--heat-ink-strong);",
      );
    });

    it("print pins the heat inks to light ink so dark-theme print stays readable", () => {
      expect(finance).toContain("--heat-ink: #14181b;");
      expect(finance).toContain("--heat-ink-strong: #14181b;");
    });

    it("the matrix boundary in ReturnsMatrix matches the CSS rule", () => {
      const matrix = readFileSync(
        path.resolve(here, "../components/finance-tearsheet/ReturnsMatrix.tsx"),
        "utf8",
      );
      expect(matrix).toContain(`>= ${STRONG_FROM}`);
      expect(finance).toContain(".ts-matrix-cell.is-strong");
    });
  });

  describe("reference diff palette (light theme)", () => {
    // terminal.css defines the dark pastels on .rv-frame and deepens them for
    // [data-theme="light"]; the +/− counts read the raw value, the code lines
    // read a 70%-toward-ink mix over the 13% wash.
    const lightFrame = terminal.match(
      /:root\[data-theme="light"\]\s*\.rv-frame\s*\{[^}]*\}/,
    )?.[0];
    expect(lightFrame, "terminal.css light .rv-frame override").toBeDefined();
    const addHex = lightFrame!.match(/--rv-add:\s*(#[0-9a-fA-F]{6})/)?.[1];
    const delHex = lightFrame!.match(/--rv-del:\s*(#[0-9a-fA-F]{6})/)?.[1];
    expect(addHex).toBeDefined();
    expect(delHex).toBeDefined();

    const lightInk = hexToken(light, "ink");
    const paper = hexToken(light, "surface");

    it("the +/− counts clear AA on paper", () => {
      expect(contrast(addHex!, paper)).toBeGreaterThanOrEqual(AA_TEXT);
      expect(contrast(delHex!, paper)).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it("the added/removed code lines clear AA on their washes", () => {
      for (const hue of [addHex!, delHex!]) {
        const wash = over(hue, 0.13, paper);
        const code = mix(hue, 0.7, lightInk);
        expect(contrast(code, wash)).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it("the light palette is not the dark pastel pair", () => {
      expect(addHex!.toLowerCase()).not.toBe("#86c98f");
      expect(delHex!.toLowerCase()).not.toBe("#e2929e");
    });

    it(".rv-ln mixes toward ink so line numbers clear AA on the washes", () => {
      expect(terminal).toContain(
        "color-mix(in srgb, var(--ink-mute) 55%, var(--ink))",
      );
    });
  });
});
