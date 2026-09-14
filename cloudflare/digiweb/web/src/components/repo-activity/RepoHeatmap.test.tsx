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

  it("renders a full grid of square cells with categorical levels", () => {
    const html = renderToStaticMarkup(
      <RepoHeatmap pulls={PULLS} weeks={4} end={new Date("2026-08-24T07:15:49Z")} />,
    );
    const cells = html.match(/data-level="[0-4]"/g) ?? [];
    expect(cells.length).toBeGreaterThanOrEqual(28);
    expect(html).toMatch(/data-level="[1-4]"/);
  });
});
