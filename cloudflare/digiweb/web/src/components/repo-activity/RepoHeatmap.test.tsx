// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { RepoHeatmap } from "./RepoHeatmap";

const PULLS = [
  {
    number: 1,
    title: "a",
    url: "https://github.com/o/r/pull/1",
    mergedAt: "2026-08-21T17:35:10Z",
  },
  {
    number: 2,
    title: "b",
    url: "https://github.com/o/r/pull/2",
    mergedAt: "2026-08-21T09:00:00Z",
  },
];

describe("RepoHeatmap GitHub-style contributions", () => {
  it("announces total contributions in the last year", () => {
    const html = renderToStaticMarkup(
      <RepoHeatmap pulls={PULLS} weeks={4} end={new Date("2026-08-24T07:15:49Z")} />,
    );
    expect(html).toMatch(/2 contributions in the last/i);
  });

  it("renders month labels, Mon/Wed/Fri day labels, and a Less/More legend", () => {
    const html = renderToStaticMarkup(
      <RepoHeatmap pulls={PULLS} weeks={4} end={new Date("2026-08-24T07:15:49Z")} />,
    );
    expect(html).toMatch(/Aug/);
    expect(html).toMatch(/Mon/);
    expect(html).toMatch(/Wed/);
    expect(html).toMatch(/Fri/);
    expect(html).toMatch(/Less/);
    expect(html).toMatch(/More/);
  });

  it("wraps the month row, cell row and legend in one max-content frame", () => {
    const html = renderToStaticMarkup(
      <RepoHeatmap pulls={PULLS} weeks={4} end={new Date("2026-08-24T07:15:49Z")} />,
    );
    // The month labels are %-positioned, so their coordinate space must be the
    // grid width, not the wider scroll body — .ra-heat-frame gives them that
    // (repo-activity.css). Assert real DOM nesting (not substring order): the
    // month/row/grid/foot nodes must all be descendants of the single frame, so
    // an empty sibling frame can no longer satisfy this.
    const container = document.createElement("div");
    container.innerHTML = html;
    const frame = container.querySelector(".ra-heat-frame");
    expect(frame).toBeTruthy();
    for (const part of ["ra-heat-months", "ra-heat-row", "ra-heat-grid", "ra-heat-foot"]) {
      expect(frame!.querySelector(`.${part}`)).toBeTruthy();
    }
    // …and the frame really is the shared width container: without this rule
    // the %-positioned month row spans the wider scroll body (the 172px drift).
    const css = readFileSync(
      path.resolve(process.cwd(), "src/styles/repo-activity.css"),
      "utf8",
    );
    expect(css).toMatch(/\.ra-heat-frame\s*\{[^}]*width:\s*max-content/);
  });

  it("renders a full grid of square cells with categorical levels", () => {
    const html = renderToStaticMarkup(
      <RepoHeatmap pulls={PULLS} weeks={4} end={new Date("2026-08-24T07:15:49Z")} />,
    );
    const cells = html.match(/data-level="[0-4]"/g) ?? [];
    expect(cells.length).toBeGreaterThanOrEqual(28);
    expect(html).toMatch(/data-level="[1-4]"/);
  });
});
