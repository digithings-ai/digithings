/**
 * @vitest-environment happy-dom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { runTearsheetPrint } from "./print";

beforeEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.classList.remove("ts-printing");
  document.title = "";
  vi.restoreAllMocks();
});

function stubPrint(impl?: () => void) {
  const print = vi.fn(impl ?? (() => {}));
  Object.defineProperty(window, "print", {
    value: print,
    writable: true,
    configurable: true,
  });
  return print;
}

function printingRecorder() {
  const calls: boolean[] = [];
  return {
    setPrinting: (v: boolean) => {
      calls.push(v);
    },
    calls,
  };
}

describe("runTearsheetPrint", () => {
  it("restores theme, title, class and printing state after print", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    document.title = "prev";
    const print = stubPrint();
    const rec = printingRecorder();

    runTearsheetPrint({ documentTitle: "export", setPrinting: rec.setPrinting });

    expect(print).toHaveBeenCalledTimes(1);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.title).toBe("prev");
    expect(document.documentElement.classList.contains("ts-printing")).toBe(false);
    expect(rec.calls).toEqual([true, false]);
  });

  it("restores state even when window.print throws", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    document.title = "prev";
    stubPrint(() => {
      throw new Error("denied");
    });
    const rec = printingRecorder();

    expect(() =>
      runTearsheetPrint({ documentTitle: "x", setPrinting: rec.setPrinting }),
    ).toThrow("denied");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.title).toBe("prev");
    expect(document.documentElement.classList.contains("ts-printing")).toBe(false);
    expect(rec.calls).toEqual([true, false]);
  });

  it("removes data-theme when none was set instead of pinning dark", () => {
    stubPrint();
    const rec = printingRecorder();

    runTearsheetPrint({ documentTitle: "x", setPrinting: rec.setPrinting });

    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
