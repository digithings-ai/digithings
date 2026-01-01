import { describe, expect, it } from "vitest";

import { bucketContributions, bucketDaily, levelFor } from "./heatmap";
import type { RepoPullItem } from "./types";

const END = new Date("2026-08-24T07:15:49Z");

function pull(mergedAt: string | null, number = 1): RepoPullItem {
  return { number, title: "t", url: "https://example.test/pr/1", mergedAt };
}

describe("bucketDaily", () => {
  it("returns weeks * 7 consecutive UTC days ending today, oldest first", () => {
    const days = bucketDaily([], 2, END);
    expect(days).toHaveLength(14);
    expect(days[0]?.date).toBe("2026-08-11");
    expect(days[13]?.date).toBe("2026-08-24");
    expect(days.every((d) => d.count === 0)).toBe(true);
  });

  it("buckets multiple merges on one day and ignores undated or out-of-window pulls", () => {
    const days = bucketDaily(
      [
        pull("2026-08-21T17:35:10Z", 1),
        pull("2026-08-21T09:00:00Z", 2),
        pull("2026-08-20T22:32:46Z", 3),
        pull(null, 4),
        pull("2025-01-01T00:00:00Z", 5),
      ],
      16,
      END,
    );
    expect(days).toHaveLength(112);
    expect(days.find((d) => d.date === "2026-08-21")?.count).toBe(2);
    expect(days.find((d) => d.date === "2026-08-20")?.count).toBe(1);
    expect(days.find((d) => d.date === "2026-08-19")?.count).toBe(0);
  });
});

describe("bucketContributions", () => {
  it("sums merges, commits, and closed issues per day like the profile graph", () => {
    const days = bucketContributions(
      [pull("2026-08-21T17:35:10Z", 1), pull("2026-08-21T09:00:00Z", 2)],
      ["2026-08-21T10:00:00Z", "2026-08-20T22:32:46Z"],
      ["2026-08-20T08:00:00Z", null],
      16,
      END,
    );
    expect(days).toHaveLength(112);
    expect(days.find((d) => d.date === "2026-08-21")?.count).toBe(3);
    expect(days.find((d) => d.date === "2026-08-20")?.count).toBe(2);
    expect(days.find((d) => d.date === "2026-08-19")?.count).toBe(0);
  });

  it("defaults to a full year window", () => {
    const days = bucketContributions([], [], [], 53, END);
    expect(days).toHaveLength(371);
    expect(days[days.length - 1]?.date).toBe("2026-08-24");
  });
});

describe("levelFor", () => {
  it("stays empty at zero and maps 1:1 for quiet histories", () => {
    expect(levelFor(0, 3)).toBe(0);
    expect(levelFor(1, 3)).toBe(1);
    expect(levelFor(3, 3)).toBe(3);
    expect(levelFor(9, 3)).toBe(4);
  });

  it("uses quartiles once a busy day would flatten the rest", () => {
    expect(levelFor(1, 8)).toBe(1);
    expect(levelFor(4, 8)).toBe(2);
    expect(levelFor(6, 8)).toBe(3);
    expect(levelFor(8, 8)).toBe(4);
  });
});
