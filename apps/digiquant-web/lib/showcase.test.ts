import { describe, expect, it } from "vitest";
import {
  DESK_TOUR,
  FORBIDDEN_SHOWCASE_CLAIM,
  METHOD_STAGES,
  PARTNER_SLOTS,
  SHOWCASE_FOOTER,
  SHOWCASE_METRICS,
  SHOWCASE_NAV,
  STORY_STAGES,
  VIDEO_SLOTS,
} from "./showcase";

function navLabels(items: typeof SHOWCASE_NAV): string[] {
  return items.map((item) => ("items" in item ? item.label : item.label));
}

describe("digiquant-web showcase IA (#4895)", () => {
  it("keeps a thin primary nav of showcase beats, not a strategy SPA", () => {
    expect(navLabels(SHOWCASE_NAV)).toEqual([
      "Desk",
      "Method",
      "Watch",
      "Partners",
      "Story",
    ]);
    expect(SHOWCASE_NAV.some((item) => "href" in item && item.href === "/#strategies")).toBe(
      false,
    );
  });

  it("points published research at /strategies from the footer only", () => {
    expect(SHOWCASE_FOOTER.some((l) => l.href === "/strategies")).toBe(true);
    expect(SHOWCASE_NAV.some((item) => "href" in item && item.href === "/strategies")).toBe(
      false,
    );
  });

  it("tells the digichat → Nautilus → inspect arc as a demo narrative", () => {
    expect(STORY_STAGES.map((s) => s.title)).toEqual([
      "digichat",
      "Nautilus backtest",
      "Inspect",
      "Hand off",
    ]);
    expect(STORY_STAGES[3]?.mech.toLowerCase()).toContain("live venue is off");
  });

  it("names LuxAlgo and Gloomberg as partner story slots", () => {
    expect(PARTNER_SLOTS.map((p) => p.title)).toEqual(["LuxAlgo", "Gloomberg"]);
  });

  it("reserves three video slots without implying a live tool", () => {
    expect(VIDEO_SLOTS).toHaveLength(3);
    expect(VIDEO_SLOTS[2]?.body.toLowerCase()).toContain("film forthcoming");
  });

  it("marks the desk display as paper and in-app", () => {
    expect(DESK_TOUR.mode).toBe("paper");
    expect(DESK_TOUR.caption.toLowerCase()).toContain("in-app");
    expect(DESK_TOUR.book.every((row) => row.state === "paper")).toBe(true);
  });

  it("reports zero live venues", () => {
    expect(SHOWCASE_METRICS.some((s) => s.label === "live venues" && s.value === "0")).toBe(
      true,
    );
  });

  it("does not ship live-trading claims or retired module names", () => {
    const blob = [
      ...METHOD_STAGES.flatMap((s) => [s.title, s.mech, s.tag ?? ""]),
      ...STORY_STAGES.flatMap((s) => [s.title, s.mech, s.tag ?? ""]),
      ...VIDEO_SLOTS.flatMap((s) => [s.title, s.body]),
      ...PARTNER_SLOTS.flatMap((s) => [s.title, s.body]),
      DESK_TOUR.caption,
      DESK_TOUR.prompt,
      ...DESK_TOUR.journal.map((j) => j.note),
    ].join("\n");
    expect(blob).not.toMatch(FORBIDDEN_SHOWCASE_CLAIM);
  });
});
