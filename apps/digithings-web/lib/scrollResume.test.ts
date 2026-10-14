import { describe, expect, it, vi } from "vitest";

import { SCROLL_RESUME_FLAG, SCROLL_RESUME_PLACE } from "./scrollResume";

function runFlag(navType: string | undefined, stored: string | null) {
  const classes = new Set<string>();
  const win: Record<string, unknown> = {};
  new Function("document", "window", "performance", "sessionStorage", "location", SCROLL_RESUME_FLAG)(
    { documentElement: { classList: { add: (name: string) => classes.add(name) } } },
    win,
    { getEntriesByType: () => (navType ? [{ type: navType }] : []) },
    { getItem: () => stored },
    { pathname: "/", search: "" },
  );
  return { classes, win };
}

describe("scroll resume", () => {
  it("flags a reload that was scrolled down", () => {
    const { classes, win } = runFlag("reload", JSON.stringify({ id: "why", frac: 0.4, y: 1800 }));
    expect(classes.has("scroll-resumed")).toBe(true);
    expect(win.__dtResumeY).toBe(1800);
  });

  it("flags back/forward too", () => {
    expect(runFlag("back_forward", JSON.stringify({ y: 400 })).classes.has("scroll-resumed")).toBe(true);
  });

  it("keeps the intro on a cold visit, even with a stale saved position", () => {
    expect(runFlag("navigate", JSON.stringify({ y: 1800 })).classes.size).toBe(0);
  });

  it("keeps the intro for a reload at (or near) the top", () => {
    expect(runFlag("reload", JSON.stringify({ y: 0 })).classes.size).toBe(0);
    expect(runFlag("reload", JSON.stringify({ y: 40 })).classes.size).toBe(0);
  });

  it("ignores missing or unreadable storage", () => {
    expect(runFlag("reload", null).classes.size).toBe(0);
    expect(runFlag("reload", "{nope").classes.size).toBe(0);
    expect(runFlag(undefined, null).classes.size).toBe(0);
  });

  it("places the scroll only when a position was flagged", () => {
    const scrollTo = vi.fn();
    const history = { scrollRestoration: "auto" };
    new Function("window", "history", SCROLL_RESUME_PLACE)({ __dtResumeY: 1800, scrollTo }, history);
    expect(scrollTo).toHaveBeenCalledWith({ top: 1800, behavior: "instant" });
    expect(history.scrollRestoration).toBe("manual");

    const idle = vi.fn();
    new Function("window", "history", SCROLL_RESUME_PLACE)({ scrollTo: idle }, { scrollRestoration: "auto" });
    expect(idle).not.toHaveBeenCalled();
  });
});
