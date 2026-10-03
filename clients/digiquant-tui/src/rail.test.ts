import { expect, test } from "bun:test";
import { navFromDesk } from "../../../apps/digiquant-web/components/desk/desk-manifest";
import { grantedDesk, railLine, railPaths, railRows } from "./rail";

function webPaths(id: string): string[] {
  const desk = grantedDesk(id);
  if (!desk) return [];
  return navFromDesk(desk).flatMap((group) =>
    group.items.flatMap((item) => [item.path, ...(item.children ?? []).map((child) => child.path)]),
  );
}

function webLabels(id: string): string[] {
  const desk = grantedDesk(id);
  if (!desk) return [];
  return navFromDesk(desk).flatMap((group) =>
    group.items.flatMap((item) => [item.label, ...(item.children ?? []).map((child) => child.label)]),
  );
}

test("the baseline rail is the web sidebar, in order", () => {
  const rows = railRows("baseline").filter((row) => row.kind === "page");
  expect(railPaths("baseline")).toEqual(webPaths("baseline"));
  expect(rows.map((row) => row.label)).toEqual(webLabels("baseline"));
  expect(railPaths("baseline")).toEqual([
    "/brief",
    "/portfolio",
    "/portfolio/holdings",
    "/portfolio/attribution",
    "/portfolio/ledger",
    "/portfolio/tearsheet",
    "/portfolio/theses",
    "/pipeline",
    "/strategies",
    "/strategies/detail",
    "/strategies/deploy",
    "/tools/terminal",
    "/tools/charts",
    "/tools/chat",
  ]);
  expect(railPaths("baseline")).not.toContain("/settings");
  expect(railPaths("baseline")).not.toContain("/performance");
  expect(railPaths("baseline")).not.toContain("/fx");
  const strategies = rows.find((row) => row.path === "/strategies");
  expect(strategies && railLine(strategies)).toBe("▾ /strategies [wip]");
  const charts = rows.find((row) => row.path === "/tools/charts");
  expect(charts && railLine(charts)).toBe("▸ /tools/charts [soon]");
  expect(railRows("baseline").some((row) => row.kind === "title" && row.text === "tools")).toBe(true);
});

test("the FX rail is the FX desk, not a second menu", () => {
  expect(railPaths("fx")).toEqual(webPaths("fx"));
  expect(railPaths("fx")).toEqual(["/fx", "/fx/ideas", "/fx/watch", "/fx/rates", "/fx/settings"]);
  const labels = railRows("fx").flatMap((row) => (row.kind === "page" ? [row.label] : []));
  expect(labels).toEqual(webLabels("fx"));
});
