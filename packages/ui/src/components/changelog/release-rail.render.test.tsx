import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReleaseRail, type ReleaseRailItem } from "./ReleaseRail";

const ITEMS: ReleaseRailItem[] = [
  {
    product: "digichat",
    version: "v2.3.1",
    date: "2026-09-20",
    title: "Charge the free-turn counter at send time",
    href: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.1",
    tag: "fix",
    entries: ["The counter no longer lags a turn behind the user."],
  },
  {
    product: "digiskills",
    version: "v0.2.1",
    date: "2026-08-15",
    title: "Skill registry parity",
    href: "https://github.com/digithings-ai/digithings/releases/tag/digiskills-v0.2.1",
  },
];

describe("ReleaseRail", () => {
  it("renders one row per release, in the caller's order", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={ITEMS} />);
    expect(html.match(/sm:grid-cols-\[180px_1fr\]/g)?.length).toBe(2);
    expect(html.indexOf("v2.3.1")).toBeLessThan(html.indexOf("v0.2.1"));
  });

  it("keeps the version the link and pins the aside sticky", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={ITEMS} />);
    expect(html).toContain("sm:grid-cols-[180px_1fr]");
    expect(html).toContain("sm:sticky");
    expect(html).toContain(
      'href="https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.1"',
    );
    expect(html).toContain(">v2.3.1<");
  });

  it("carries the machine-readable date and the upstream tag", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={ITEMS} />);
    expect(html).toContain('<time dateTime="2026-09-20">2026-09-20</time>');
    expect(html).toContain("· fix");
  });

  it("omits the tag separator when a release is untagged", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={ITEMS} />);
    expect(html).not.toContain("· undefined");
    expect(html).not.toContain("· <");
  });

  it("renders highlights with the [*] glyph and no highlight list when absent", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={ITEMS} />);
    expect(html).toContain("[*]");
    expect(html).toContain("The counter no longer lags a turn behind the user.");
    expect(html.match(/\[\*\]/g)?.length).toBe(1);
  });

  it("uses no syntax palette and no colour literal", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={ITEMS} />);
    expect(html).not.toMatch(/text-(emerald|sky|amber|rose|violet|fuchsia|blue|green|red)-/);
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}/);
  });

  it("renders an empty list without rows", () => {
    const html = renderToStaticMarkup(<ReleaseRail items={[]} />);
    expect(html).not.toContain("<li");
  });
});
