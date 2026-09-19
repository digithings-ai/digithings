// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TypedWelcomeCopy } from "./typed-welcome-copy";

const LINES = ["First line", "Second line"];

function stubMatchMedia(reduced: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduced,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

function mount(reduced: boolean) {
  stubMatchMedia(reduced);
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<TypedWelcomeCopy lines={LINES} />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

function copyText(container: HTMLElement): string {
  return Array.from(container.querySelectorAll(".aui-thread-welcome-copy"))
    .map((node) => node.textContent)
    .join("|");
}

function visibleText(container: HTMLElement): string {
  return Array.from(container.querySelectorAll(".aui-thread-welcome-copy"))
    .map((node) => {
      const ghost = node.querySelector(".aui-thread-welcome-ghost");
      return node.textContent!.replace(ghost?.textContent ?? "", "");
    })
    .join("|");
}

function carets(container: HTMLElement): number {
  return container.querySelectorAll(".aui-thread-welcome-caret").length;
}

describe("TypedWelcomeCopy", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("keeps the full copy in static markup (SSR / no-JS)", () => {
    const html = renderToStaticMarkup(<TypedWelcomeCopy lines={LINES} />);
    expect(html).toContain("First line");
    expect(html).toContain("Second line");
    expect(html).not.toContain("aui-thread-welcome-caret");
  });

  it("keeps every line mounted while the typewriter reveals it in place", () => {
    const { container, cleanup } = mount(false);
    try {
      expect(copyText(container)).toBe("First line|Second line");
      expect(visibleText(container)).toBe("|");
      expect(carets(container)).toBe(1);

      act(() => {
        vi.advanceTimersByTime(18 * 5);
      });
      expect(copyText(container)).toBe("First line|Second line");
      expect(visibleText(container)).toBe("First|");
      expect(carets(container)).toBe(1);

      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(copyText(container)).toBe("First line|Second line");
      expect(visibleText(container)).toBe("First line|Second line");
      expect(carets(container)).toBe(0);
    } finally {
      cleanup();
    }
  });

  it("leaves the copy static under prefers-reduced-motion", () => {
    const { container, cleanup } = mount(true);
    try {
      expect(copyText(container)).toBe("First line|Second line");
      expect(visibleText(container)).toBe("First line|Second line");
      expect(carets(container)).toBe(0);
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(visibleText(container)).toBe("First line|Second line");
    } finally {
      cleanup();
    }
  });
});
