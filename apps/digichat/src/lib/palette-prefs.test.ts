// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THEME_CHANGE_EVENT } from "@digithings/ui/theme";

import {
  applyDeployedPalette,
  applyThemeModeKeepingPalette,
  readEffectiveThemeState,
} from "./palette-prefs";

describe("deployment palette default", () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = new Map();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: (i: number) => [...store.keys()][i] ?? null,
      get length() {
        return store.size;
      },
    });
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.removeAttribute("data-palette");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("paints the deployment palette without writing storage, and tells the provider", () => {
    const changed = vi.fn();
    window.addEventListener(THEME_CHANGE_EVENT, changed);
    applyDeployedPalette(" Dracula ");
    window.removeEventListener(THEME_CHANGE_EVENT, changed);
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
    expect(store.size).toBe(0);
    expect(changed).toHaveBeenCalledTimes(1);
    expect(readEffectiveThemeState().palette).toBe("dracula");
  });

  it("leaves a stored palette choice alone", () => {
    store.set("dt-palette", "aura");
    document.documentElement.setAttribute("data-palette", "aura");
    applyDeployedPalette("dracula");
    expect(document.documentElement.getAttribute("data-palette")).toBe("aura");
    expect(store.get("dt-palette")).toBe("aura");
    expect(readEffectiveThemeState().palette).toBe("aura");
  });

  it("treats an unknown stored palette as no choice", () => {
    store.set("dt-palette", "draculaa");
    applyDeployedPalette("dracula");
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
  });

  it("reads the painted palette when storage throws", () => {
    document.documentElement.setAttribute("data-palette", "dracula");
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    });
    expect(readEffectiveThemeState().palette).toBe("dracula");
  });

  it("stores only the mode for /theme <mode>, never the painted palette", () => {
    document.documentElement.setAttribute("data-palette", "dracula");
    const writes: string[] = [];
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        writes.push(k);
        store.set(k, String(v));
      },
      removeItem: (k: string) => void store.delete(k),
    });
    applyThemeModeKeepingPalette("light");
    expect(writes).toEqual(["dt-theme"]);
    expect(store.get("dt-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("leaves a pinned embed document alone", () => {
    const meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    meta.setAttribute("content", "#121417");
    document.head.append(meta);
    document.documentElement.setAttribute("data-theme-pin", "1");
    const changed = vi.fn();
    window.addEventListener(THEME_CHANGE_EVENT, changed);
    applyDeployedPalette("dracula");
    window.removeEventListener(THEME_CHANGE_EVENT, changed);
    document.documentElement.removeAttribute("data-theme-pin");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(meta.getAttribute("content")).toBe("#121417");
    expect(changed).not.toHaveBeenCalled();
    meta.remove();
  });

  it("ignores an unknown or default deployment palette", () => {
    applyDeployedPalette("not-a-palette");
    applyDeployedPalette("default");
    applyDeployedPalette(null);
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
  });
});
