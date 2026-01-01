import { describe, expect, it } from "vitest";
import {
  filterThreadsByQuery,
  groupThreadsByDate,
  type SidebarThread,
} from "./conversation-sidebar";

function t(id: string, title: string, updatedAt: string): SidebarThread {
  return { id, title, updatedAt };
}

describe("filterThreadsByQuery", () => {
  const threads = [
    t("1", "BTC valuation rails", "2026-09-04T10:00:00.000Z"),
    t("2", "Portfolio review", "2026-09-03T10:00:00.000Z"),
    t("3", "btc risk band", "2026-09-02T10:00:00.000Z"),
  ];

  it("returns all threads for empty or whitespace query", () => {
    expect(filterThreadsByQuery(threads, "")).toEqual(threads);
    expect(filterThreadsByQuery(threads, "   ")).toEqual(threads);
  });

  it("filters case-insensitively by title substring", () => {
    expect(filterThreadsByQuery(threads, "btc").map((x) => x.id)).toEqual(["1", "3"]);
    expect(filterThreadsByQuery(threads, "PORTFOLIO").map((x) => x.id)).toEqual(["2"]);
  });

  it("returns empty when nothing matches", () => {
    expect(filterThreadsByQuery(threads, "zzzz")).toEqual([]);
  });
});

describe("groupThreadsByDate", () => {
  // Anchor in local calendar so buckets are timezone-stable.
  const now = new Date(2026, 8, 4, 15, 0, 0); // 4 Sep 2026 local
  const isoAt = (y: number, m: number, d: number, h = 12) =>
    new Date(y, m, d, h, 0, 0).toISOString();

  it("buckets into Today / Yesterday / Last 7 days / Older", () => {
    const threads = [
      t("today", "A", isoAt(2026, 8, 4, 11)),
      t("yest", "B", isoAt(2026, 8, 3, 11)),
      t("week", "C", isoAt(2026, 7, 30, 11)),
      t("old", "D", isoAt(2026, 7, 1, 11)),
    ];
    const groups = groupThreadsByDate(threads, now);
    expect(groups.map((g) => g.label)).toEqual([
      "Today",
      "Yesterday",
      "Last 7 days",
      "Older",
    ]);
    expect(groups.map((g) => g.items.map((i) => i.id))).toEqual([
      ["today"],
      ["yest"],
      ["week"],
      ["old"],
    ]);
  });

  it("omits empty buckets", () => {
    const only = t("only", "X", isoAt(2026, 8, 4, 1));
    const groups = groupThreadsByDate([only], now);
    expect(groups).toEqual([{ label: "Today", items: [only] }]);
  });
});
