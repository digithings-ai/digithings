"use client";

import { ModuleGrid as KitModuleGrid, modules, type ModuleGridItem } from "@digithings/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { moduleLines } from "@/lib/repoActivity";
import { moduleCountLabel, moduleVersion } from "@/lib/moduleCounts";
import { bannerFor, ScrollBanner } from "./ScrollBanner";

/** A tile's name mark: the module's hero banner, or none (text name) yet. */
function markFor(id: string) {
  const def = bannerFor(id);
  return def ? <ScrollBanner def={def} /> : undefined;
}

/**
 * The landing's module mosaic and its `#architecture` anchor: the kit
 * `ModuleGrid` fed this repo's line counts, versions and endpoint/tool counts.
 * "ask digichat" hands the question to `/chat`.
 *
 * The dist/ contract is the mosaic's `aria-label="digithings modules, sized by
 * lines of code"`, checked by `scripts/build-digithings.sh`.
 *
 * Band eyebrows (`SectionHead`) above the mosaic were dropped in #4898;
 * the `#architecture` id on the section remains the jump target.
 *
 * Each tile names its module with that module's hero banner, built on
 * scroll-in; a module the banner family has not reached yet keeps its text name.
 */
/** digistore and digilink are roadmap and have no hero banner. Leaving them
 *  in the mosaic reserved empty weight. */
const LANDING_MODULES = modules.filter(
  (module) => module.id !== "digistore" && module.id !== "digilink",
);

const ITEMS: ModuleGridItem[] = LANDING_MODULES.map((module) => ({
  module,
  lines: moduleLines(module.id),
  version: moduleVersion(module.id),
  counts: moduleCountLabel(module.id) || undefined,
  mark: markFor(module.id),
}));

function ask(id: string) {
  writeHandoff([], `What does ${id} do, and how do I use it?`);
  window.location.href = "/chat";
}

export function ModuleGrid() {
  return (
    <section id="architecture" className="line-t line-b scroll-mt-[var(--dq-nav-h)]">
      <KitModuleGrid items={ITEMS} onAsk={ask} />
    </section>
  );
}
