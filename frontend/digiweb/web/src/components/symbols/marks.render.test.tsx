/**
 * SSR smoke tests for the promoted brand marks (#1548): the DigiquantMark emits
 * its animatable per-stroke class hooks (retargetable for the dashboard
 * loader), and the Wordmark dresses its suffix in the livery
 * accent.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DigiquantMark, OlympusMark, Wordmark } from "./marks";

describe("DigiquantMark", () => {
  it("emits the default olympus-stroke hooks and stays decorative", () => {
    const html = renderToStaticMarkup(<DigiquantMark />);
    expect(html).toContain("olympus-mark");
    for (const n of [1, 2, 3, 4]) expect(html).toContain(`olympus-stroke-${n}`);
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain('width="22"');
  });

  it("retargets stroke classes for the dashboard loader grammar", () => {
    const html = renderToStaticMarkup(
      <DigiquantMark size={56} className="atlas-loader-mark" strokeClassPrefix="atlas-loader-stroke" />
    );
    for (const n of [1, 2, 3, 4]) expect(html).toContain(`atlas-loader-stroke-${n}`);
    expect(html).toContain("atlas-loader-mark");
    expect(html).toContain('width="56"');
  });

  it("exposes a titled mark as an image", () => {
    const html = renderToStaticMarkup(<DigiquantMark title="digiquant" />);
    expect(html).toContain("<title>digiquant</title>");
    expect(html).toContain('role="img"');
    expect(html).not.toContain("aria-hidden");
  });

  it("keeps OlympusMark as a one-release alias", () => {
    expect(OlympusMark).toBe(DigiquantMark);
  });
});

describe("Wordmark", () => {
  it("dresses the suffix in the accent", () => {
    const html = renderToStaticMarkup(<Wordmark suffix="quant" />);
    expect(html).toContain("digi");
    expect(html).toContain(">quant</em>");
    expect(html).toContain("text-accent");
    expect(html).toContain("font-mono");
  });

  it("passes className and a custom prefix through", () => {
    const html = renderToStaticMarkup(<Wordmark prefix="digi" suffix="things" className="text-[2rem]" />);
    expect(html).toContain("text-[2rem]");
    expect(html).toContain(">things</em>");
  });
});
