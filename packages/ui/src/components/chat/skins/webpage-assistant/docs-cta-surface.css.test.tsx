// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { renderToStaticMarkup } from "react-dom/server";
import { compile } from "tailwindcss";
import { beforeAll, describe, expect, it } from "vitest";

import { DocsArticle } from "./docs-article";
import { getPageById } from "./pages";
import { defaultDocsHostUi } from "./host-ui";

/**
 * DIG-6110: chat-aui.css emits the stock skin's `bg-surface-2` utility only
 * inside the stock thread and its portals. The docs page's "Ask … Assistant"
 * call to action is a stock outline Button rendered by the host page, outside
 * the thread, and asks for surface-2 on hover, when expanded and (dark) at
 * rest. No surface-2 declaration may reach it there, so it keeps its own
 * `bg-surface` as on develop, while the same Button inside a stock thread or
 * a stock portal still fills.
 *
 * happy-dom does not run the cascade, so this compiles the real chat-aui.css
 * with Tailwind for the Button's real classes, walks the emitted rules, and
 * uses happy-dom's selector matching on the rendered docs page to decide which
 * background-color declarations apply and whether the switch is inherited.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const STYLES = path.resolve(here, "../../../../styles");
const BUTTON_SRC = path.resolve(here, "../../stock/ui/button.tsx");
const require = createRequire(import.meta.url);

type Rule = { selector: string; decls: Record<string, string> };

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function splitSelectors(sel: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let cur = "";
  for (let i = 0; i < sel.length; i++) {
    const ch = sel[i]!;
    if (ch === "\\") {
      cur += ch + (sel[i + 1] ?? "");
      i++;
      continue;
    }
    if (ch === "(" || ch === "[") depth++;
    if (ch === ")" || ch === "]") depth--;
    if (ch === "," && depth === 0) {
      out.push(cur.trim());
      cur = "";
    } else cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

/** Flattens Tailwind's nested output: `&` resolves against the parent, at-rules pass through. */
function flatten(css: string): Rule[] {
  const rules: Rule[] = [];
  const src = stripComments(css);
  let i = 0;
  function block(parents: string[]): void {
    let buf = "";
    const decls: Record<string, string> = {};
    while (i < src.length) {
      const ch = src[i]!;
      if (ch === "\\") {
        buf += ch + src[i + 1];
        i += 2;
        continue;
      }
      if (ch === "{") {
        i++;
        const head = buf.trim();
        buf = "";
        if (head.startsWith("@")) {
          block(parents);
        } else {
          const own = splitSelectors(head);
          const next =
            parents.length === 0
              ? own
              : parents.flatMap((p) => own.map((s) => (s.includes("&") ? s.split("&").join(p) : `${p} ${s}`)));
          block(next);
        }
        continue;
      }
      if (ch === "}") {
        i++;
        const tail = buf.trim();
        if (tail) addDecl(decls, tail);
        if (parents.length && Object.keys(decls).length) {
          for (const s of parents) rules.push({ selector: s, decls: { ...decls } });
        }
        return;
      }
      if (ch === ";") {
        addDecl(decls, buf.trim());
        buf = "";
        i++;
        continue;
      }
      buf += ch;
      i++;
    }
  }
  function addDecl(decls: Record<string, string>, text: string): void {
    if (!text || text.startsWith("@")) return;
    const at = text.indexOf(":");
    if (at < 0) return;
    decls[text.slice(0, at).trim()] = text.slice(at + 1).trim();
  }
  block([]);
  return rules;
}

function outlineButtonClasses(): string[] {
  const src = readFileSync(BUTTON_SRC, "utf8");
  const base = /cva\(\s*"([^"]+)"/.exec(src)?.[1];
  const outline = /outline:\s*"([^"]+)"/.exec(src)?.[1];
  expect(base, "stock Button base classes").toBeTruthy();
  expect(outline, "stock Button outline classes").toBeTruthy();
  return `${base} ${outline}`.split(/\s+/).filter(Boolean);
}

async function buildRules(candidates: string[]): Promise<Rule[]> {
  const theme = readFileSync(path.join(STYLES, "digichat-app-theme.css"), "utf8");
  const darkVariant = /@custom-variant dark \([^;]+\);/.exec(theme)?.[0];
  expect(darkVariant, "the app's dark variant").toBeTruthy();
  const input = [
    '@import "tailwindcss/theme.css" layer(theme);',
    '@import "tailwindcss/utilities.css" layer(utilities);',
    darkVariant,
    `@import "${path.join(STYLES, "chat-aui.css")}";`,
  ].join("\n");
  const compiler = await compile(input, {
    base: STYLES,
    loadStylesheet: async (id: string, base: string) => {
      const file = id.startsWith("tailwindcss/") ? require.resolve(id) : path.resolve(base, id);
      return { path: file, base: path.dirname(file), content: readFileSync(file, "utf8") };
    },
  });
  return flatten(compiler.build(candidates));
}

const SCOPE = ":where([data-stock-thread], [data-stock-thread] *, [data-stock-portal], [data-stock-portal] *)";

function inStockScope(el: Element): boolean {
  return el.closest("[data-stock-thread], [data-stock-portal]") !== null;
}

type State = "rest" | "hover" | "expanded";
type Mode = "light" | "dark";

/** The background-color values that apply to `el` in a state, via selector matching. */
function backgrounds(rules: Rule[], el: Element, state: State): string[] {
  const out: string[] = [];
  for (const r of rules) {
    const bg = r.decls["background-color"];
    if (!bg) continue;
    let sel = r.selector;
    if (sel.includes(":hover")) {
      if (state !== "hover") continue;
      sel = sel.split(":hover").join("");
    }
    // happy-dom cannot match complex selectors inside :is()/:where(). The
    // dark variant `X:is(.dark *)` on a single compound equals `.dark X`; the
    // stock scope `X:where([data-stock-thread], [data-stock-thread] *, …)`
    // holds when X or an ancestor carries one of the two attributes.
    if (sel.includes(SCOPE)) {
      if (!inStockScope(el)) continue;
      sel = sel.split(SCOPE).join("");
    }
    if (sel.includes(":is(.dark *)")) sel = `.dark ${sel.split(":is(.dark *)").join("")}`;
    let hit = false;
    try {
      hit = el.matches(sel);
    } catch {
      hit = false;
    }
    if (hit) out.push(bg);
  }
  return out;
}

/** The surface-2 background declarations that reach `el` in a state. */
function surface2Fills(rules: Rule[], el: Element, state: State): string[] {
  return backgrounds(rules, el, state).filter((v) => v.includes("--surface-2"));
}

function setup(markup: string, mode: Mode, state: State): Element {
  document.documentElement.className = mode === "dark" ? "dark" : "";
  document.body.innerHTML = markup;
  const buttons = [...document.querySelectorAll("button")].filter((b) =>
    /Assistant/.test(b.textContent ?? ""),
  );
  expect(buttons).toHaveLength(1);
  const btn = buttons[0]!;
  if (state === "expanded") btn.setAttribute("aria-expanded", "true");
  return btn;
}

const MODES: Mode[] = ["light", "dark"];
const STATES: State[] = ["rest", "hover", "expanded"];

describe("docs page CTA keeps no surface-2 fill outside the stock thread (DIG-6110)", () => {
  let rules: Rule[] = [];
  let docsPage = "";

  beforeAll(async () => {
    rules = await buildRules(outlineButtonClasses());
    const props = defaultDocsHostUi.root.props;
    const page = getPageById(props.defaultPageId, props.pages, props.defaultPageId);
    // As on the real docs page, the stock thread is mounted beside the
    // article (the assistant panel), so a page-wide switch would leak here.
    docsPage = `<main>${renderToStaticMarkup(<DocsArticle page={page} onSelectPage={() => {}} />)}</main><aside><div data-stock-thread=""></div></aside>`;
  });

  it("the CTA asks for surface-2 on hover, when expanded and at rest in dark", () => {
    // Guards the test itself: without these requests the checks below prove nothing.
    const asks = (state: State) => [...rules].some((r) => {
      const bg = r.decls["background-color"];
      return !!bg?.includes("--surface-2") && (state === "hover" ? r.selector.includes(":hover") : r.selector.includes("aria-expanded"));
    });
    expect(asks("hover")).toBe(true);
    expect(asks("expanded")).toBe(true);
    expect(rules.some((r) => r.selector.startsWith(".dark\\:bg-surface-2\\/30") && r.decls["background-color"]?.includes("--surface-2"))).toBe(true);
  });

  it("emits surface-2 backgrounds only inside the stock thread and its portals, never page-wide", () => {
    const s2 = rules.filter((r) => r.decls["background-color"]?.includes("--surface-2"));
    expect(s2.length).toBeGreaterThan(0);
    for (const r of s2) {
      expect(r.selector, r.selector).toContain(SCOPE);
      expect(r.selector, r.selector).not.toContain(":has(");
    }
  });

  it("keeps the CTA's own bg-surface at rest in light, as on develop", () => {
    const btn = setup(docsPage, "light", "rest");
    expect(backgrounds(rules, btn, "rest")).toEqual(["var(--surface)"]);
  });

  for (const mode of MODES) {
    for (const state of STATES) {
      it(`has no surface-2 fill on the docs page (${mode}, ${state})`, () => {
        const btn = setup(docsPage, mode, state);
        expect(btn.closest("[data-stock-thread], [data-stock-portal]")).toBeNull();
        expect(surface2Fills(rules, btn, state)).toEqual([]);
      });

      it(`still fills inside a stock thread and a stock portal (${mode}, ${state})`, () => {
        if (mode === "light" && state === "rest") return; // outline rests on bg-surface in light
        for (const wrap of ["data-stock-thread", "data-stock-portal"]) {
          const btn = setup(`<div ${wrap}="">${docsPage}</div>`, mode, state);
          expect(surface2Fills(rules, btn, state).length, wrap).toBeGreaterThan(0);
        }
      });
    }
  }
});
