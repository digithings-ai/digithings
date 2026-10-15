/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { claimLoading } from "@digithings/hero-banner";

import { DIGICHAT } from "@digithings/hero-banner/definitions";
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

  it("plays loading once per tab through the shared claim", () => {
    expect(claimLoading(DIGICHAT, sessionStorage)).toBe(true);
    expect(claimLoading(DIGICHAT, sessionStorage)).toBe(false);
    renderMark();
    expect(container.querySelector("canvas")).not.toBeNull();
  });

  it("survives a header remount without losing the label", () => {
    renderMark();
    act(() => root.unmount());
    root = createRoot(container);
    renderMark();
    expect(container.querySelector("canvas")?.getAttribute("aria-label")).toBe("digichat");
  });
});
