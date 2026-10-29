// @vitest-environment happy-dom
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { PALETTE_IDS } from "@digithings/ui/theme";
import { describe, expect, it } from "vitest";

/**
 * Every palette the site picker offers has to resolve the same background,
 * surface, ink, accent, and hairline on /chat and the top-level embed as on
 * digithings.ai. happy-dom's CSS engine drops :is()/:has(), so this walks the
 * real sheets and uses selector matching (which does support them) to decide
 * the winning custom property. A palette added to PALETTE_IDS without a
 * palettes.css block, or a later chat rule that paints over that block, fails.
 */

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const KEYS = ["--bg", "--surface", "--ink", "--accent", "--hair", "--hair-2"] as const;

type Spec = [number, number, number];
type Rule = { selector: string; decls: Record<string, string>; spec: Spec; order: number };

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function splitTop(input: string, sep: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === "(" || ch === "[") depth += 1;
    else if (ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
    else if (ch === sep && depth === 0) {
      parts.push(input.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(input.slice(start));
  return parts;
}

function cmpSpec(a: Spec, b: Spec): number {
  return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
}

function specificity(selector: string): Spec {
  let a = 0;
  let b = 0;
  let c = 0;
  let i = 0;
  const text = selector.replace(/::[A-Za-z-]+/g, () => {
    c += 1;
    return " ";
  });
  while (i < text.length) {
    if (
      text.startsWith(":where(", i) ||
      text.startsWith(":is(", i) ||
      text.startsWith(":not(", i) ||
      text.startsWith(":has(", i)
    ) {
      const name = text.startsWith(":where(", i)
        ? "where"
        : text.startsWith(":is(", i)
          ? "is"
          : text.startsWith(":not(", i)
            ? "not"
            : "has";
      const open = i + name.length + 2;
      let depth = 1;
      let j = open;
      for (; j < text.length && depth; j++) {
        if (text[j] === "(") depth += 1;
        else if (text[j] === ")") depth -= 1;
      }
      if (name !== "where") {
        let best: Spec = [0, 0, 0];
        for (const arg of splitTop(text.slice(open, j - 1), ",")) {
          const spec = specificity(arg);
          if (cmpSpec(spec, best) > 0) best = spec;
        }
        a += best[0];
        b += best[1];
        c += best[2];
      }
      i = j;
      continue;
    }
    const ch = text[i];
    if (ch === "[") {
      b += 1;
      let depth = 1;
      i += 1;
      for (; i < text.length && depth; i++) {
        if (text[i] === "[") depth += 1;
        else if (text[i] === "]") depth -= 1;
      }
      continue;
    }
    if (ch === "#") {
      a += 1;
      i += 1;
      while (i < text.length && /[A-Za-z0-9_-]/.test(text[i])) i += 1;
      continue;
    }
    if (ch === ".") {
      b += 1;
      i += 1;
      while (i < text.length && /[A-Za-z0-9_-]/.test(text[i])) i += 1;
      continue;
    }
    if (ch === ":") {
      b += 1;
      i += 1;
      while (i < text.length && /[A-Za-z0-9_-]/.test(text[i])) i += 1;
      continue;
    }
    if (/[A-Za-z*]/.test(ch)) {
      if (ch !== "*") c += 1;
      while (i < text.length && /[A-Za-z0-9_-]/.test(text[i])) i += 1;
      continue;
    }
    i += 1;
  }
  return [a, b, c];
}

function parseRules(css: string, out: Rule[], order: { n: number }): void {
  const text = stripComments(css);
  let i = 0;
  while (i < text.length) {
    while (i < text.length && /\s/.test(text[i])) i += 1;
    if (i >= text.length) break;
    if (text[i] === "@") {
      const semi = text.indexOf(";", i);
      const brace = text.indexOf("{", i);
      if (brace === -1 || (semi !== -1 && semi < brace)) {
        i = semi === -1 ? text.length : semi + 1;
        continue;
      }
      const head = text.slice(i, brace);
      let depth = 1;
      let j = brace + 1;
      for (; j < text.length && depth; j++) {
        if (text[j] === "{") depth += 1;
        else if (text[j] === "}") depth -= 1;
      }
      if (/^@(media|supports|layer)\b/.test(head)) parseRules(text.slice(brace + 1, j - 1), out, order);
      i = j;
      continue;
    }
    const brace = text.indexOf("{", i);
    if (brace === -1) break;
    const selector = text.slice(i, brace).trim();
    let depth = 1;
    let j = brace + 1;
    for (; j < text.length && depth; j++) {
      if (text[j] === "{") depth += 1;
      else if (text[j] === "}") depth -= 1;
    }
    const decls: Record<string, string> = {};
    for (const part of text.slice(brace + 1, j - 1).split(";")) {
      const idx = part.indexOf(":");
      if (idx === -1) continue;
      const prop = part.slice(0, idx).trim();
      const value = part.slice(idx + 1).replace(/!important/g, "").trim();
      if (prop.startsWith("--") && value) decls[prop] = value;
    }
    if (selector && Object.keys(decls).length > 0) {
      for (const sel of splitTop(selector, ",")) {
        const one = sel.trim();
        if (!one) continue;
        out.push({ selector: one, decls, spec: specificity(one), order: order.n });
        order.n += 1;
      }
    }
    i = j;
  }
}

function resolveVars(value: string, get: (name: string) => string | undefined, stack: Set<string>): string {
  let current = value;
  for (let guard = 0; current.includes("var(") && guard < 8; guard++) {
    current = current.replace(/var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*([^)]*))?\)/g, (_match, name: string, fallback?: string) => {
      if (stack.has(name)) return fallback?.trim() ?? "";
      stack.add(name);
      const next = get(name);
      const resolved = next ? resolveVars(next, get, stack) : (fallback?.trim() ?? "");
      stack.delete(name);
      return resolved;
    });
  }
  return current.trim();
}

function cascade(rules: Rule[], elements: Element[]): Record<string, string>[] {
  const maps: Record<string, string>[] = [];
  elements.forEach((el, index) => {
    const parent = index > 0 ? maps[index - 1] : null;
    const matched = rules.filter((rule) => {
      try {
        return el.matches(rule.selector);
      } catch {
        return false;
      }
    });
    matched.sort((a, b) => cmpSpec(a.spec, b.spec) || a.order - b.order);
    const specified: Record<string, string> = parent ? { ...parent } : {};
    for (const rule of matched) Object.assign(specified, rule.decls);
    if (parent) {
      for (const [prop, value] of Object.entries(specified)) {
        if (value === "inherit" && parent[prop]) specified[prop] = parent[prop];
      }
    }
    const computed: Record<string, string> = {};
    for (const [prop, value] of Object.entries(specified)) {
      computed[prop] = resolveVars(value, (name) => specified[name], new Set([prop]));
    }
    maps.push(computed);
  });
  return maps;
}

function resolveImport(fromFile: string, spec: string): string | null {
  if (spec === "tailwindcss" || spec === "tw-animate-css") return null;
  if (spec.startsWith("@digithings/design/")) {
    return path.join(ROOT, "packages/design", spec.slice("@digithings/design/".length));
  }
  if (spec.startsWith("@digithings/ui/styles/")) {
    return path.join(ROOT, "packages/ui/src/styles", spec.slice("@digithings/ui/styles/".length));
  }
  if (spec.startsWith(".")) return path.resolve(path.dirname(fromFile), spec);
  return null;
}

function readSheet(file: string, seen: Set<string>): string {
  if (seen.has(file) || !existsSync(file)) return "";
  seen.add(file);
  const css = readFileSync(file, "utf8");
  const imports = [...css.matchAll(/@import\s+(?:url\()?["']([^"']+)["']/g)].map((match) => match[1]);
  const body = css.replace(/@import[^;]+;/g, "");
  return imports.map((spec) => readSheet(resolveImport(file, spec) ?? "", seen)).join("\n") + body;
}

function chatCss(): string {
  const globals = path.join(ROOT, "apps/digichat/src/app/(digichat)/globals.css");
  return readSheet(globals, new Set());
}

function siteCss(): string {
  const palettes = readFileSync(path.join(ROOT, "packages/design/palettes.css"), "utf8");
  const tokens = readFileSync(path.join(ROOT, "packages/design/tokens.css"), "utf8").replace(
    /@import[^;]+;/,
    "",
  );
  const globals = readFileSync(path.join(ROOT, "apps/digithings-web/app/globals.css"), "utf8");
  const accent = globals.match(
    /:root\[data-theme="dark"\]\s*\{[^}]*--accent:\s*var\(--ink\);[^}]*\}[\s\S]*?:root\[data-theme="light"\]\s*\{[^}]*--accent:\s*var\(--ink\);[^}]*\}/,
  );
  if (!accent) throw new Error("digithings.ai accent override is missing from globals.css");
  return `${palettes}\n${tokens}\n${accent[0]}`;
}

function declaredBg(id: string, theme: string): string | null {
  const palettes = readFileSync(path.join(ROOT, "packages/design/palettes.css"), "utf8");
  const block = palettes.match(
    new RegExp(`:root\\[data-palette="${id}"\\]\\[data-theme="${theme}"\\][^{]*\\{([^}]*)\\}`),
  );
  const bg = block?.[1].match(/--bg:\s*([^;]+)/);
  return bg ? bg[1].trim() : null;
}

const chatRules: Rule[] = [];
const siteRules: Rule[] = [];
parseRules(chatCss(), chatRules, { n: 0 });
parseRules(siteCss(), siteRules, { n: 0 });

function paint(theme: string, id: string, surface: "app" | "occ"): Record<string, string>[] {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.setAttribute("data-palette", id);
  if (surface === "occ") document.documentElement.setAttribute("data-site-theme", "1");
  else document.documentElement.removeAttribute("data-site-theme");
  const mode = surface === "app" ? "app" : "embed";
  document.body.innerHTML =
    surface === "occ"
      ? `<div class="dc-embed-shell" data-skin-canvas="1"><div data-stock-product data-thread-skin="digichat" data-chrome-mode="${mode}" class="accent-digichat"><div class="digichat-thread"></div></div></div>`
      : `<div data-stock-product data-thread-skin="digichat" data-chrome-mode="${mode}" class="accent-digichat"><div class="digichat-thread"></div></div>`;
  const thread = document.querySelector(".digichat-thread");
  const host = thread?.parentElement;
  if (!thread || !host) throw new Error("fixture missing the chat thread");
  const chain = [document.documentElement, document.body, host, thread];
  if (surface === "occ") {
    const shell = document.querySelector(".dc-embed-shell");
    if (!shell) throw new Error("fixture missing the embed shell");
    chain.splice(2, 0, shell);
  }
  return cascade(surface === "app" || surface === "occ" ? chatRules : siteRules, chain);
}

function siteTokens(theme: string, id: string): Record<string, string> {
  document.body.innerHTML = "";
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.setAttribute("data-palette", id);
  document.documentElement.removeAttribute("data-site-theme");
  return cascade(siteRules, [document.documentElement])[0];
}

const cases = PALETTE_IDS.flatMap((id) =>
  (["light", "dark"] as const).map((theme) => [id, theme] as const),
);

describe("chat palette parity with digithings.ai", () => {
  it("reads the site palette list", () => {
    expect(PALETTE_IDS.length).toBeGreaterThan(0);
  });

  it.each(cases)("%s %s matches site tokens on /chat and the top-level embed", (id, theme) => {
    const declared = declaredBg(id, theme);
    expect(declared, `${id} ${theme} is missing from palettes.css`).toMatch(/^#[0-9a-fA-F]{3,8}$/);
    const site = siteTokens(theme, id);
    const app = paint(theme, id, "app");
    const occ = paint(theme, id, "occ");
    const appRoot = app[0];
    const appThread = app[app.length - 1];
    const occRoot = occ[0];
    const occThread = occ[occ.length - 1];
    for (const key of KEYS) {
      const siteValue = (site[key] ?? "").toLowerCase();
      expect((appRoot[key] ?? "").toLowerCase(), `app root ${key}`).toBe(siteValue);
      expect((appThread[key] ?? "").toLowerCase(), `app thread ${key}`).toBe(siteValue);
      expect((occRoot[key] ?? "").toLowerCase(), `occ root ${key}`).toBe(siteValue);
      expect((occThread[key] ?? "").toLowerCase(), `occ thread ${key}`).toBe(siteValue);
    }
    expect((appRoot["--bg"] ?? "").toLowerCase()).toBe(declared!.toLowerCase());
    expect((occRoot["--bg"] ?? "").toLowerCase()).toBe(declared!.toLowerCase());
    expect((appThread["--bg"] ?? "").toLowerCase()).toBe(declared!.toLowerCase());
    expect((occThread["--bg"] ?? "").toLowerCase()).toBe(declared!.toLowerCase());
  });
});

/**
 * The thread column has no canvas of its own on a site chat. The footer that
 * holds the welcome, the examples and the composer used to paint
 * `bg-surface` in every named palette (and on the top-level OCC page in every
 * palette), which drew a tinted box around the welcome block that the rest of
 * the page did not share. It must resolve to the page canvas for every
 * palette, on /chat and on the top-level embed.
 */
function footerTokens(theme: string, id: string | null, surface: "app" | "occ"): Record<string, string> {
  document.documentElement.setAttribute("data-theme", theme);
  if (id) document.documentElement.setAttribute("data-palette", id);
  else document.documentElement.removeAttribute("data-palette");
  if (surface === "occ") document.documentElement.setAttribute("data-site-theme", "1");
  else document.documentElement.removeAttribute("data-site-theme");
  const mode = surface === "app" ? "app" : "embed";
  document.body.innerHTML = `<div data-stock-product data-thread-skin="digichat" data-chrome-mode="${mode}"><div class="digichat-thread"><div class="digichat-thread__footer bg-surface"></div></div></div>`;
  const host = document.querySelector("[data-stock-product]")!;
  const thread = document.querySelector(".digichat-thread")!;
  const footer = document.querySelector(".digichat-thread__footer")!;
  const maps = cascade(chatRules, [document.documentElement, document.body, host, thread, footer]);
  return maps[maps.length - 1];
}

describe("chat thread column sits on the page canvas", () => {
  const all = [null, ...PALETTE_IDS].flatMap((id) =>
    (["light", "dark"] as const).flatMap((theme) =>
      (["app", "occ"] as const).map((surface) => [id ?? "default", theme, surface] as const),
    ),
  );

  it.each(all)("%s %s %s: the footer paints no surface", (id, theme, surface) => {
    const footer = footerTokens(theme, id === "default" ? null : id, surface);
    expect(footer["--bg"]).toBe("transparent");
    expect(footer["--surface"]).toBe("transparent");
  });

  it("the site-chat rule clears the footer background with no palette gate", () => {
    const css = stripComments(
      readFileSync(path.join(ROOT, "apps/digichat/src/styles/site-chat.css"), "utf8"),
    );
    const rule = css.match(/[^{}]*\.digichat-thread__footer[^{}]*\{[^}]*\}/g) ?? [];
    const canvas = rule.find((r) => /background:\s*transparent/.test(r));
    expect(canvas, "site-chat.css footer canvas rule").toBeTruthy();
    expect(canvas).not.toMatch(/data-palette/);
    expect(canvas).toMatch(/data-site-theme="1"/);
  });
});

/**
 * The command palette and the composer (settings) menu sit inside that
 * footer, so they inherit its cleared tokens. Their background is var(--bg),
 * which made both menus see-through on the top-level OCC page in every
 * palette. They must get the palette's canvas and surface back.
 */
function menuTokens(
  theme: string,
  id: string | null,
  surface: "app" | "occ",
  menuClass: string,
): { thread: Record<string, string>; menu: Record<string, string> } {
  document.documentElement.setAttribute("data-theme", theme);
  if (id) document.documentElement.setAttribute("data-palette", id);
  else document.documentElement.removeAttribute("data-palette");
  if (surface === "occ") document.documentElement.setAttribute("data-site-theme", "1");
  else document.documentElement.removeAttribute("data-site-theme");
  const mode = surface === "app" ? "app" : "embed";
  // OCC mounts inside .dc-embed-shell, and the composer menu carries its own
  // data-thread-skin (embed-composer-menu.tsx), so product-chrome.css re-points
  // --term-bg on the menu element itself (#08090b in dark).
  const skin = menuClass.includes("dc-composer-menu") ? ' data-thread-skin="digichat"' : "";
  const product = `<div data-stock-product data-thread-skin="digichat" data-chrome-mode="${mode}"><div class="digichat-thread"><div class="digichat-thread__footer"><div class="aui-composer-root"><div class="${menuClass}"${skin}></div></div></div></div></div>`;
  document.body.innerHTML = surface === "occ" ? `<div class="dc-embed-shell">${product}</div>` : product;
  const host = document.querySelector("[data-stock-product]")!;
  const thread = document.querySelector(".digichat-thread")!;
  const footer = document.querySelector(".digichat-thread__footer")!;
  const root = document.querySelector(".aui-composer-root")!;
  const menu = root.firstElementChild!;
  const shell = document.querySelector(".dc-embed-shell");
  const chain = [document.documentElement, document.body, ...(shell ? [shell] : []), host, thread, footer, root, menu];
  const maps = cascade(chatRules, chain);
  return { thread: maps[chain.indexOf(thread)], menu: maps[maps.length - 1] };
}

describe("chat menus keep the palette canvas inside the clear footer", () => {
  const menus = ["aui-composer-trigger-popover", "dc-composer-menu aui-composer-trigger-popover"];
  const all = [null, ...PALETTE_IDS].flatMap((id) =>
    (["light", "dark"] as const).flatMap((theme) =>
      (["app", "occ"] as const).flatMap((surface) =>
        menus.map((menu) => [id ?? "default", theme, surface, menu] as const),
      ),
    ),
  );

  it.each(all)("%s %s %s: .%s paints the page canvas", (id, theme, surface, menuClass) => {
    const { thread, menu } = menuTokens(theme, id === "default" ? null : id, surface, menuClass);
    expect(thread["--bg"]).toMatch(/^#[0-9a-fA-F]{3,8}$/);
    expect(menu["--bg"]).not.toBe("transparent");
    expect(menu["--bg"]?.toLowerCase()).toBe(thread["--bg"].toLowerCase());
    expect(menu["--surface"]?.toLowerCase()).toBe(thread["--surface"].toLowerCase());
    // The background itself is painted from --term-bg / --site-menu-canvas;
    // both must resolve to the thread canvas on the menu element.
    expect(menu["--term-bg"]?.toLowerCase()).toBe(thread["--bg"].toLowerCase());
  });

  it("site-chat.css paints the menus with the thread's canvas on every site chat", () => {
    const css = stripComments(
      readFileSync(path.join(ROOT, "apps/digichat/src/styles/site-chat.css"), "utf8"),
    );
    const rule = (css.match(/[^{}]*\.dc-composer-menu[^{}]*\{[^}]*\}/g) ?? []).find((r) =>
      /background:\s*var\(--site-menu-canvas\)/.test(r),
    );
    expect(rule, "site-chat.css menu canvas rule").toBeTruthy();
    expect(rule).toMatch(/\.aui-composer-trigger-popover/);
    expect(rule).toMatch(/data-site-theme="1"/);
    expect(rule).not.toMatch(/data-palette/);
  });
});

/**
 * The boot loader covers the chat with `.dboot-overlay bg-surface`. On a
 * site chat the chat sits on --bg, so the loader painted a lighter frame and
 * then jumped to a different grey when the chat appeared. It must paint the
 * same canvas as the chat it hands off to.
 */
describe("boot loader paints the chat canvas on a site chat", () => {
  it("site-chat.css gives the overlay var(--bg), keeping wide embeds transparent", () => {
    const css = stripComments(
      readFileSync(path.join(ROOT, "apps/digichat/src/styles/site-chat.css"), "utf8"),
    );
    const rule = (css.match(/[^{}]*\.dboot-overlay[^{}]*\{[^}]*\}/g) ?? []).find((r) =>
      /background:\s*var\(--bg\)/.test(r),
    );
    expect(rule, "site-chat.css boot overlay canvas rule").toBeTruthy();
    expect(rule).toMatch(/data-site-theme="1"/);
    expect(rule).toMatch(/data-chrome-mode="app"/);
    expect(rule).toMatch(/:not\(\[data-embed-wide="1"\]\)/);
    expect(rule).not.toMatch(/data-palette/);
  });

  it.each([null, ...PALETTE_IDS].flatMap((id) => (["light", "dark"] as const).map((t) => [id ?? "default", t] as const)))(
    "%s %s: the overlay's --bg is the thread's canvas on /chat and OCC",
    (id, theme) => {
      for (const surface of ["app", "occ"] as const) {
        const { thread } = menuTokens(theme, id === "default" ? null : id, surface, "x");
        document.querySelector("[data-stock-product]")!.insertAdjacentHTML("afterbegin", '<div class="dboot-overlay bg-surface"></div>');
        const host = document.querySelector("[data-stock-product]")!;
        const overlay = document.querySelector(".dboot-overlay")!;
        const shell = document.querySelector(".dc-embed-shell");
        const maps = cascade(chatRules, [document.documentElement, document.body, ...(shell ? [shell] : []), host, overlay]);
        expect(maps[maps.length - 1]["--bg"]?.toLowerCase(), `${surface} overlay --bg`).toBe(thread["--bg"].toLowerCase());
      }
    },
  );
});

/**
 * Stock skins on the embed route sit in a wrapper that carries shadcn's
 * `.dark` class and paints bg-background. `.dark` redeclares --background as
 * zinc, so with a named palette the base skin's chat area showed near-black
 * instead of the palette canvas (lucent-orng dark: #2a1a15). The wrapper's
 * --background must resolve to the palette's dark --bg for every palette, and
 * stay on the shadcn zinc when no palette is set.
 */
function embedWrapperBackground(id: string | null, skin = "base"): string {
  document.documentElement.setAttribute("data-theme", "dark");
  document.documentElement.setAttribute("data-site-theme", "1");
  if (id) document.documentElement.setAttribute("data-palette", id);
  else document.documentElement.removeAttribute("data-palette");
  document.body.className = "accent-digichat bg-background";
  document.body.innerHTML = `<div class="dc-embed-shell bg-background"><div class="dark accent-digichat bg-background"><div data-stock-product data-thread-skin="${skin}" data-chrome-mode="embed"></div></div></div>`;
  const shell = document.querySelector(".dc-embed-shell")!;
  const wrapper = shell.firstElementChild!;
  const maps = cascade(chatRules, [document.documentElement, document.body, shell, wrapper]);
  document.body.className = "";
  return (maps[maps.length - 1]["--background"] ?? "").toLowerCase();
}

describe("base skin embed wrapper paints the palette canvas in dark", () => {
  it.each(PALETTE_IDS.map((id) => [id] as const))("%s dark: wrapper --background is the palette --bg", (id) => {
    const declared = declaredBg(id, "dark");
    expect(declared, `${id} dark is missing from palettes.css`).toMatch(/^#[0-9a-fA-F]{3,8}$/);
    expect(embedWrapperBackground(id)).toBe(declared!.toLowerCase());
  });

  it("lucent-orng dark resolves to its brown canvas, not the zinc", () => {
    expect(embedWrapperBackground("lucent-orng")).toBe("#2a1a15");
  });

  it("no palette: the wrapper keeps the shadcn dark background", () => {
    expect(embedWrapperBackground(null)).toBe("oklch(0.141 0.005 285.823)");
  });
});

/**
 * The chatgpt skin paints its own dark canvas (thread root and composer
 * footer) through --chat-skin-canvas, #000 when unset. With a named palette in
 * dark, the embed sets that token (and the wrapper --background) to the
 * palette --bg, as for the base skin. No palette, light, or another skin
 * leaves the token unset, so the skin keeps its #000.
 */
function chatgptCanvas(id: string | null, theme: "dark" | "light" = "dark", skin = "chatgpt"): string | undefined {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.setAttribute("data-site-theme", "1");
  if (id) document.documentElement.setAttribute("data-palette", id);
  else document.documentElement.removeAttribute("data-palette");
  document.body.className = "accent-digichat bg-background";
  document.body.innerHTML = `<div class="dc-embed-shell bg-background"><div class="${theme === "dark" ? "dark " : ""}accent-digichat bg-background"><div data-stock-product data-thread-skin="${skin}" data-chrome-mode="embed"></div></div></div>`;
  const shell = document.querySelector(".dc-embed-shell")!;
  const wrapper = shell.firstElementChild!;
  const stock = wrapper.firstElementChild!;
  const maps = cascade(chatRules, [document.documentElement, document.body, shell, wrapper, stock]);
  document.body.className = "";
  return maps[maps.length - 1]["--chat-skin-canvas"]?.toLowerCase();
}

describe("chatgpt skin paints the palette canvas in dark", () => {
  it("the skin reads its dark canvas from --chat-skin-canvas with a #000 fallback", () => {
    const tsx = readFileSync(path.join(ROOT, "packages/ui/src/components/chat/skins/chatgpt.tsx"), "utf8");
    expect(tsx).not.toMatch(/dark:bg-black\b/);
    expect(tsx.match(/dark:bg-\[color:var\(--chat-skin-canvas,#000\)\]/g)).toHaveLength(2);
  });

  it.each(PALETTE_IDS.map((id) => [id] as const))("%s dark: chatgpt canvas and wrapper are the palette --bg", (id) => {
    const declared = declaredBg(id, "dark");
    expect(declared, `${id} dark is missing from palettes.css`).toMatch(/^#[0-9a-fA-F]{3,8}$/);
    expect(chatgptCanvas(id)).toBe(declared!.toLowerCase());
    expect(embedWrapperBackground(id, "chatgpt")).toBe(declared!.toLowerCase());
  });

  it("lucent-orng dark resolves to its brown canvas, not black", () => {
    expect(chatgptCanvas("lucent-orng")).toBe("#2a1a15");
  });

  it("no palette, light, or another skin: the token stays unset (skin keeps #000)", () => {
    expect(chatgptCanvas(null)).toBeUndefined();
    expect(chatgptCanvas("lucent-orng", "light")).toBeUndefined();
    expect(chatgptCanvas("lucent-orng", "dark", "claude")).toBeUndefined();
    expect(embedWrapperBackground(null, "chatgpt")).toBe("oklch(0.141 0.005 285.823)");
    expect(embedWrapperBackground("lucent-orng", "claude")).toBe("oklch(0.141 0.005 285.823)");
  });
});
