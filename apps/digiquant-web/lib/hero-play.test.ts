import * as React from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its web.tsx with classic JSX while production (Next.js) uses automatic.
// The free `React` name resolves here at render time.
(globalThis as unknown as Record<string, unknown>).React ??= React;
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { QuantWordmark, quantArmed } from "@/app/_chrome/QuantWordmark";
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

  it("draws the shared DIGIQUANT definition through HeroBanner", () => {
    const src = readFileSync(new URL("../app/_chrome/QuantWordmark.tsx", import.meta.url), "utf8");
    expect(src).toContain("@digithings/hero-banner/definitions");
    expect(src).toContain("DIGIQUANT");
    expect(src).toContain("@digithings/hero-banner/web");
    expect(src).toContain("HeroBanner");
    expect(src).toContain("replayLoading={replay}");
    const html = renderToStaticMarkup(createElement(QuantWordmark));
    expect(html).toContain('aria-label="digiquant"');
    expect(html).toContain("<canvas");
    const hero = renderToStaticMarkup(createElement(QuantWordmark, { replay: true }));
    expect(hero).toContain('aria-label="digiquant"');
    const idle = renderToStaticMarkup(createElement(QuantWordmark, { phase: "idle" }));
    expect(idle).toContain('aria-label="digiquant"');
  });

  it("keeps the shared rise definition carrying both year-round tones", () => {
    const defs = readFileSync(
      new URL("../../../packages/hero-banner/src/definitions/index.ts", import.meta.url),
      "utf8",
    );
    expect(defs).toContain('up: { hex: "#3DD6C4"');
    expect(defs).toContain('down: { hex: "#E5533E"');
    expect(defs).toContain("seed: 0x9a17");
  });

  it("holds idle marks back until they may start", () => {
    expect(quantArmed({ phase: "run", armed: true })).toBe(true);
    expect(quantArmed({ phase: "run", armed: false })).toBe(false);
    expect(quantArmed({ phase: "idle", armed: true })).toBe(false);
    expect(quantArmed({ phase: "idle", armed: false })).toBe(false);
  });

  it("builds the top hero on every load", () => {
    const top = readFileSync(new URL("../app/_bands/top.tsx", import.meta.url), "utf8");
    expect(top).toMatch(/<QuantWordmark replay /);
  });
});
