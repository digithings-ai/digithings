import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { modules } from "../../data/modules";
import { ModuleGrid, type ModuleGridItem } from "./ModuleGrid";

const byId = (id: string) => {
  const found = modules.find((m) => m.id === id);
  if (!found) throw new Error(`missing module ${id}`);
  return found;
};

const ITEMS: ModuleGridItem[] = [
  { module: byId("digismith"), lines: 950, version: "0.3.0" },
  { module: byId("digistore"), lines: null, version: null },
  { module: byId("digiquant"), lines: 178_900, version: "0.9.2", counts: "41 endpoints" },
  { module: byId("digigraph"), lines: 62_400, version: "1.4.0" },
];

describe("ModuleGrid", () => {
  const html = renderToStaticMarkup(<ModuleGrid items={ITEMS} label="modules by size" />);

  it("orders tiles biggest first and roadmap modules last", () => {
    const order = [...html.matchAll(/data-mod="([^"]+)"/g)].map((m) => m[1]);
    expect(order).toEqual(["digiquant", "digigraph", "digismith", "digistore"]);
  });

  it("labels the list and states each version, roadmap without a fabricated one", () => {
    expect(html).toContain('role="list"');
    expect(html).toContain('aria-label="modules by size"');
    expect(html).toContain("v0.9.2");
    expect(html).toContain(">roadmap<");
  });

  it("names each tile's facts on its focus control", () => {
    expect(html).toContain("178,900 lines · 41 endpoints");
  });
});
