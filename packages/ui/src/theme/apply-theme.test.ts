// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyDocumentTheme,
  matchThemeStep,
  nextThemeStep,
  PALETTE_IDS,
  readPaintedTheme,
  themeCycle,
} from "./apply-theme";

beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  });
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-palette");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("theme cycle", () => {
  it("is default dark, default light, then each palette dark and light", () => {
    const steps = themeCycle();
    expect(steps).toHaveLength(2 + PALETTE_IDS.length * 2);
    expect(steps.slice(0, 4).map((s) => s.id)).toEqual([
      "default:dark",
      "default:light",
      `${PALETTE_IDS[0]}:dark`,
      `${PALETTE_IDS[0]}:light`,
    ]);
    expect(new Set(steps.map((s) => s.id)).size).toBe(steps.length);
  });

  it("steps from a palette to the next and wraps to default dark", () => {
    const last = PALETTE_IDS[PALETTE_IDS.length - 1];
    expect(nextThemeStep("dark", PALETTE_IDS[0], "dark").id).toBe(`${PALETTE_IDS[0]}:light`);
    expect(nextThemeStep("light", PALETTE_IDS[0], "light").id).toBe(`${PALETTE_IDS[1]}:dark`);
    expect(nextThemeStep("light", last, "light").id).toBe("default:dark");
  });

  it("auto matches the resolved mode", () => {
    expect(matchThemeStep("auto", "default", "light").id).toBe("default:light");
  });
});

describe("applyDocumentTheme", () => {
  it("persists a choice, and repaints without writing when asked", () => {
    applyDocumentTheme("light", "nord");
    expect(localStorage.getItem("dt-theme")).toBe("light");
    expect(localStorage.getItem("dt-palette")).toBe("nord");
    localStorage.clear();
    applyDocumentTheme("dark", "dracula", undefined, { persist: false });
    expect(readPaintedTheme()).toEqual({ resolved: "dark", palette: "dracula" });
    expect(localStorage.getItem("dt-theme")).toBeNull();
    expect(localStorage.getItem("dt-palette")).toBeNull();
  });
});
