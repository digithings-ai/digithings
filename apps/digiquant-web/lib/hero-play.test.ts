import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { QuantWordmark } from "@/app/_chrome/QuantWordmark";
import { HERO_ADOPT_MS, HERO_PLAYED_KEY, HERO_PLAYED_SCRIPT, nextHeroLive } from "./hero-play";

describe("digiquant hero play", () => {
  it("marks a later document before paint and leaves the first load free", () => {
    expect(HERO_PLAYED_SCRIPT).toContain(JSON.stringify(HERO_PLAYED_KEY));
    expect(HERO_PLAYED_SCRIPT).toContain('setAttribute("data-dq-hero","played")');
    expect(HERO_PLAYED_SCRIPT).toContain("sessionStorage.setItem");
    const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
    expect(css).toContain('html[data-dq-hero="played"] :not([data-dq-live]) > [data-dq-build]');
    expect(css).toContain("var(--dq-glint, none)");
    const reduced = css.slice(css.indexOf("prefers-reduced-motion: reduce"));
    expect(reduced).toContain('html[data-dq-hero="played"] :not([data-dq-live]) > [data-dq-build]');
  });

  it("claims the rise once, adopts a strict remount, and skips a later mount", () => {
    expect(nextHeroLive({ played: false, armed: true, idle: false, now: 10, gate: null })).toEqual({
      live: true,
      claim: true,
    });
    expect(nextHeroLive({ played: false, armed: false, idle: false, now: 10, gate: null })).toEqual({
      live: false,
      claim: false,
    });
    expect(
      nextHeroLive({
        played: true,
        armed: true,
        idle: false,
        now: 20,
        gate: { started: 10, connected: false },
      }).live,
    ).toBe(true);
    expect(HERO_ADOPT_MS).toBeLessThan(200);
    expect(nextHeroLive({ played: true, replay: true, armed: true, idle: false, now: 500, gate: null })).toEqual({
      live: true,
      claim: false,
    });
    expect(nextHeroLive({ played: false, replay: true, armed: true, idle: false, now: 10, gate: null })).toEqual({
      live: true,
      claim: true,
    });
    expect(nextHeroLive({ played: true, replay: true, armed: true, idle: true, now: 10, gate: null }).live).toBe(false);
    expect(
      nextHeroLive({
        played: true,
        armed: true,
        idle: false,
        now: 500,
        gate: { started: 10, connected: false },
      }),
    ).toEqual({ live: false, claim: false });
  });

  it("paints the rise on the first server render and holds an idle mark", () => {
    const html = renderToStaticMarkup(createElement(QuantWordmark));
    expect(html).toContain('aria-label="digiquant"');
    expect(html).toContain("dq-rise");
    expect(html).toContain("var(--up)");
    expect(html).toContain("var(--down)");
    expect(html).toContain("data-dq-build");
    expect(html).not.toContain("data-dq-live");
    const hero = renderToStaticMarkup(createElement(QuantWordmark, { replay: true }));
    expect(hero).toContain("data-dq-live");
    const idle = renderToStaticMarkup(createElement(QuantWordmark, { phase: "idle" }));
    expect(idle).not.toContain("data-dq-build");
    expect(idle).toContain("opacity:0");
  });

  it("keeps red and green pixels flashing after the build", () => {
    const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
    const glint = css.slice(css.indexOf("@keyframes dq-glint"), css.indexOf("@keyframes dq-blink"));
    expect(glint).toContain("var(--dq-cell");
    expect(glint).not.toContain("var(--accent)");
    expect(css).toContain("@keyframes dq-blink");
    const html = renderToStaticMarkup(createElement(QuantWordmark, { replay: true }));
    const cells = [...html.matchAll(/<rect [^>]*style="([^"]*)"/g)].map((m) => m[1]);
    const tones = (name: string) =>
      new Set(cells.filter((st) => st.includes(name) && st.includes("infinite")).map((st) => /--dq-cell:([^;]+)/.exec(st)?.[1]));
    expect(tones("dq-glint")).toEqual(new Set(["var(--up)", "var(--down)"]));
    expect(tones("dq-blink")).toEqual(new Set(["var(--up)", "var(--down)"]));
    const reduced = css.slice(css.indexOf("prefers-reduced-motion: reduce"));
    expect(reduced).toContain("[data-dq-anim]");
    expect(html).toContain("data-dq-anim");
  });

  it("builds the top hero on every load", () => {
    const top = readFileSync(new URL("../app/_bands/top.tsx", import.meta.url), "utf8");
    expect(top).toMatch(/<QuantWordmark replay /);
  });
});
