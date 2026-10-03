/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DigichatWordmark } from "./DigichatWordmark";
import { WORDMARK_CLOCK_HOST, shadeHex } from "./digichat-wordmark";

const DIM = shadeHex("dim");
const REST = shadeHex("rest");

function host(): Record<string, unknown> {
  return window as unknown as Record<string, unknown>;
}

describe("DigichatWordmark session", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    delete host()[WORDMARK_CLOCK_HOST];
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
    delete host()[WORDMARK_CLOCK_HOST];
    vi.useRealTimers();
  });

  function renderMark() {
    act(() => {
      root.render(createElement(DigichatWordmark));
    });
  }

  it("scrambles on the first load and not after a reload", () => {
    renderMark();
    act(() => {
      vi.advanceTimersByTime(80);
    });
    expect(container.innerHTML).toContain(DIM);

    act(() => root.unmount());
    delete host()[WORDMARK_CLOCK_HOST];
    root = createRoot(container);
    renderMark();
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(container.innerHTML).not.toContain(DIM);
    expect(container.innerHTML).toContain(REST);
  });

  it("does not restart the scramble when the header remounts", () => {
    renderMark();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(container.innerHTML).not.toContain(DIM);

    act(() => root.unmount());
    root = createRoot(container);
    renderMark();
    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(container.innerHTML).not.toContain(DIM);
    expect(container.innerHTML).toContain(REST);
  });
});
