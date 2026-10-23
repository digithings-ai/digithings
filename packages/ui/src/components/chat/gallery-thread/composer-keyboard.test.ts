// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  composerHasText,
  dismissComposerKeyboard,
  isCoarsePointer,
} from "./composer-keyboard";

function stubPointer(coarse: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(pointer: coarse)" ? coarse : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

function composerWithTextarea() {
  const root = document.createElement("form");
  const area = document.createElement("textarea");
  root.appendChild(area);
  document.body.appendChild(root);
  area.focus();
  return { root, area };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("composer keyboard dismissal", () => {
  it("reads the coarse pointer that stands for a phone", () => {
    stubPointer(true);
    expect(isCoarsePointer()).toBe(true);
    stubPointer(false);
    expect(isCoarsePointer()).toBe(false);
  });

  it("treats a missing matchMedia as a fine pointer", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(isCoarsePointer()).toBe(false);
  });

  it("blurs the focused textarea on a coarse pointer", () => {
    stubPointer(true);
    const { root, area } = composerWithTextarea();
    expect(document.activeElement).toBe(area);

    expect(dismissComposerKeyboard(root)).toBe(true);
    expect(document.activeElement).not.toBe(area);
  });

  it("leaves a desktop caret alone", () => {
    stubPointer(false);
    const { root, area } = composerWithTextarea();

    expect(dismissComposerKeyboard(root)).toBe(false);
    expect(document.activeElement).toBe(area);
  });

  it("is a no-op when the composer has no textarea or no root", () => {
    stubPointer(true);
    const empty = document.createElement("form");
    document.body.appendChild(empty);

    expect(dismissComposerKeyboard(empty)).toBe(false);
    expect(dismissComposerKeyboard(null)).toBe(false);
  });
});

describe("composerHasText", () => {
  it("reads the draft before a send clears it", () => {
    const root = document.createElement("form");
    const area = document.createElement("textarea");
    area.value = "How do I get started?";
    root.appendChild(area);

    expect(composerHasText(root)).toBe(true);
  });

  it("treats whitespace as empty, and a missing composer as empty", () => {
    const root = document.createElement("form");
    const area = document.createElement("textarea");
    area.value = "   \n  ";
    root.appendChild(area);

    expect(composerHasText(root)).toBe(false);
    expect(composerHasText(document.createElement("form"))).toBe(false);
    expect(composerHasText(null)).toBe(false);
  });
});
