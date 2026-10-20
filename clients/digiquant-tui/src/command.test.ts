import { expect, test } from "bun:test";
import { commandPages, deskChoices, nextDesk, publicRailPaths, searchCommandPages } from "./command";
import { railPaths, railRows } from "./rail";

function labels(id: string): string[] {
  return railRows(id).flatMap((row) => (row.kind === "page" ? [row.label] : []));
}

test("the public desk dropdown is Baseline", () => {
  expect(deskChoices().map((desk) => desk.id)).toEqual(["baseline"]);
  expect(deskChoices().map((desk) => desk.label)).toEqual(["Baseline"]);
  expect(deskChoices().some((desk) => /12x/i.test(desk.label) || /12x/i.test(desk.blurb))).toBe(false);
  expect(nextDesk("baseline")).toBe("baseline");
  expect(nextDesk("fx")).toBe("baseline");
});

test("the public page list is the baseline rail", () => {
  const hits = commandPages("baseline");
  expect(hits.map((hit) => hit.path)).toEqual(railPaths("baseline"));
  expect(hits.map((hit) => hit.label)).toEqual(labels("baseline"));
  expect(publicRailPaths("fx")).toEqual(railPaths("baseline"));
  expect(commandPages("fx").map((hit) => hit.path)).toEqual(railPaths("baseline"));
  expect(hits.some((hit) => hit.path === "/fx" || hit.path.startsWith("/fx/"))).toBe(false);
  const blob = JSON.stringify(hits).toLowerCase();
  expect(blob).not.toContain("fx hub");
  expect(blob).not.toContain("12x");
});

test("a query matches the public path, label, and web href", () => {
  expect(searchCommandPages("portfolio", "baseline").map((hit) => hit.path)).toEqual([
    "/portfolio",
    "/portfolio/holdings",
    "/portfolio/attribution",
    "/portfolio/ledger",
    "/portfolio/tearsheet",
    "/portfolio/theses",
  ]);
  expect(searchCommandPages("charts", "baseline")[0]?.path).toBe("/tools/charts");
  expect(searchCommandPages("digichat", "baseline").map((hit) => hit.label)).toEqual(["digichat"]);
  expect(searchCommandPages("/app/tools/terminal/", "baseline").map((hit) => hit.label)).toEqual(["Terminal"]);
  expect(searchCommandPages("fx", "baseline")).toEqual([]);
  expect(searchCommandPages("12x", "baseline")).toEqual([]);
  expect(searchCommandPages("luxalgo", "baseline")).toEqual([]);
  expect(searchCommandPages("/", "baseline").map((hit) => hit.path)).toEqual(publicRailPaths("baseline"));
});
