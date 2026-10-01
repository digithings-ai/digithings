"use client";

/**
 * Module grid — the scroll-walked treemap mosaic. Consumes the shared
 * <ModuleGrid/> from @digithings/ui with fixture line counts; digithings-web
 * feeds the same component its repo's real counts.
 */
import { ModuleGrid, modules, type ModuleGridItem } from "@digithings/ui";

const FIXTURE: Record<string, { lines: number | null; version: string | null; counts?: string }> = {
  digiquant: { lines: 178_900, version: "0.9.2", counts: "41 endpoints · 18 MCP tools" },
  digigraph: { lines: 62_400, version: "1.4.0", counts: "22 endpoints · 12 MCP tools" },
  digisearch: { lines: 24_800, version: "0.8.1", counts: "9 endpoints · 6 MCP tools" },
  digichat: { lines: 41_200, version: "1.2.0" },
  digikey: { lines: 8_900, version: "0.6.0", counts: "7 endpoints" },
  digismith: { lines: 950, version: "0.3.0", counts: "3 endpoints" },
  digiclaw: { lines: 2_600, version: "0.4.1" },
  digibase: { lines: 5_300, version: "0.5.0" },
  digivault: { lines: 12_100, version: "0.7.0", counts: "11 endpoints · 8 MCP tools" },
};

const ITEMS: ModuleGridItem[] = modules.map((module) => ({
  module,
  lines: FIXTURE[module.id]?.lines ?? null,
  version: FIXTURE[module.id]?.version ?? null,
  counts: FIXTURE[module.id]?.counts,
}));

export function ModuleGridReference() {
  return (
    <section className="section-block" id="module-grid">
      <p className="kicker">{"// module grid"}</p>
      <h2 className="title">Sized by the code, walked by the scroll.</h2>
      <p className="section-copy">
        One angular tile per module, each tile&apos;s area its share of the stack&apos;s lines of
        code — biggest top-left, roadmap modules last. Scrolling the pinned track walks the focus:
        the focused tile grows in place with its facts, packages and compose command while the
        rest repack around it. Click a tile to jump to it. On a phone, or under reduced motion,
        the same tiles stack and open in turn. Figures here are fixtures.
      </p>
      <ModuleGrid items={ITEMS} vhPerModule={24} className="mt-[1.2rem]" />
    </section>
  );
}
