import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ArchSpec } from "./ArchitectureDiagram";
import { ArchitectureSvg } from "./architecture-svg";

const GRID: ArchSpec = {
  title: "Grid",
  description: "Three columns, three rows.",
  services: [
    { id: "a", label: "a", col: 0, row: 0 },
    { id: "b", label: "b", col: 2, row: 0 },
    { id: "c", label: "c", col: 1, row: 1 },
    { id: "d", label: "d", col: 0, row: 2 },
    { id: "e", label: "e", col: 2, row: 2 },
  ],
  edges: [{ from: "a", to: "c" }],
};

function viewBox(html: string): { x: number; y: number; w: number; h: number } {
  const m = /viewBox="([^"]+)"/.exec(html);
  const [x, y, w, h] = (m?.[1] ?? "").split(" ").map(Number);
  return { x, y, w, h };
}

function boxX(html: string, id: string): number {
  const m = new RegExp(`id="arch-service-${id}"[^>]*>\\s*<rect[^>]*x="([-\\d.]+)"`).exec(html);
  return Number(m?.[1]);
}

describe("ArchitectureSvg aspect fit", () => {
  const natural = viewBox(renderToStaticMarkup(<ArchitectureSvg spec={GRID} />));

  it("keeps the default grid when no aspect is given", () => {
    const html = renderToStaticMarkup(<ArchitectureSvg spec={GRID} aspect={undefined} />);
    expect(viewBox(html)).toEqual(natural);
  });

  it("widens the column gutters to reach a wider frame", () => {
    const target = (natural.w / natural.h) * 1.3;
    const html = renderToStaticMarkup(<ArchitectureSvg spec={GRID} aspect={target} />);
    const vb = viewBox(html);
    expect(vb.w / vb.h).toBeCloseTo(target, 2);
    expect(vb.h).toBeCloseTo(natural.h, 5);
    expect(boxX(html, "b")).toBeGreaterThan(boxX(renderToStaticMarkup(<ArchitectureSvg spec={GRID} />), "b"));
  });

  it("deepens the row gutters to reach a taller frame", () => {
    const target = (natural.w / natural.h) * 0.8;
    const vb = viewBox(renderToStaticMarkup(<ArchitectureSvg spec={GRID} aspect={target} />));
    expect(vb.w / vb.h).toBeCloseTo(target, 2);
    expect(vb.w).toBeCloseTo(natural.w, 5);
  });

  it("caps the stretch, letterboxing past it rather than pulling boxes apart forever", () => {
    const vb = viewBox(renderToStaticMarkup(<ArchitectureSvg spec={GRID} aspect={50} />));
    expect(vb.w / vb.h).toBeLessThan(50);
    expect(vb.w).toBeGreaterThan(natural.w);
  });
});
