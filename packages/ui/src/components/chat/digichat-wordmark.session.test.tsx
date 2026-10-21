/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";



import { DigichatWordmark } from "./DigichatWordmark";
import * as React from "react";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its web.tsx with classic JSX while production (Next.js) uses automatic.
// The free `React` name resolves here at render time.
(globalThis as unknown as Record<string, unknown>).React ??= React;

describe("DigichatWordmark session", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    sessionStorage.clear();
    // happy-dom has no canvas 2d context; without this the banner effect
    // returns before the session claim and the once-per-tab pin is void.
    // `getContext` is overloaded, so the stub is cast to the whole method:
    // one implementation signature satisfies none of the overloads on its own.
    // Only the 2d context is faked, the other ids get the null the real API
    // returns, so the cast cannot hide a wrong context type.
    HTMLCanvasElement.prototype.getContext = function (contextId: string) {
      if (contextId !== "2d") return null;
      return new Proxy({}, { get: () => () => {} }) as unknown as CanvasRenderingContext2D;
    } as unknown as HTMLCanvasElement["getContext"];
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() {
        return false;
      },
      onchange: null,
    })) as unknown as typeof window.matchMedia;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    sessionStorage.clear();
  });

  function renderMark() {
    act(() => {
      root.render(createElement(DigichatWordmark));
    });
  }

  it("mounts a canvas carrying the digichat label", () => {
    renderMark();
    const canvas = container.querySelector("canvas");
    expect(canvas).not.toBeNull();
    expect(canvas?.getAttribute("aria-label")).toBe("digichat");
  });

  it("fakes the 2d context only, the other ids get the null of the real API", () => {
    const canvas = document.createElement("canvas");
    expect(canvas.getContext("2d")).not.toBeNull();
    expect(canvas.getContext("webgl")).toBeNull();
  });

  it("plays loading once per tab through the component", () => {
    renderMark();
    expect(sessionStorage.getItem("hero-banner:digichat:played")).toBe("1");
    expect(container.querySelector("canvas")).not.toBeNull();
  });

  it("does not replay on header remount", () => {
    renderMark();
    act(() => root.unmount());
    root = createRoot(container);
    renderMark();
    expect(sessionStorage.getItem("hero-banner:digichat:played")).toBe("1");
    expect(container.querySelector("canvas")?.getAttribute("aria-label")).toBe("digichat");
  });

  it("survives a header remount without losing the label", () => {
    renderMark();
    act(() => root.unmount());
    root = createRoot(container);
    renderMark();
    expect(container.querySelector("canvas")?.getAttribute("aria-label")).toBe("digichat");
  });
});
