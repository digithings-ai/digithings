"use client";

import { ModuleGrid as KitModuleGrid, Reveal, modules, type ModuleGridItem } from "@digithings/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { moduleLines } from "@/lib/repoActivity";
import { moduleCountLabel, moduleVersion } from "@/lib/moduleCounts";
import { ModuleManifest } from "./ModuleManifest";

/**
 * The landing's module mosaic and its `#architecture` anchor: the kit
 * `ModuleGrid` fed this repo's line counts, versions and endpoint/tool counts.
 * "ask digichat" hands the question to `/chat`.
 *
 * The dist/ contract is the mosaic's `aria-label="digithings modules, sized by
 * lines of code"`, checked by `scripts/build-digithings.sh`. It is the only
 * one: the folded `/modules/*` and `/architecture` routes this pane used to
 * back are gone, so `ModuleManifest` stays for the module prose it still
 * carries, not as a contract marker.
 *
 * Band eyebrows (`SectionHead`) above the mosaic were dropped in #4898;
 * the `#architecture` id on the section remains the jump target.
 */
const ITEMS: ModuleGridItem[] = modules.map((module) => ({
  module,
  lines: moduleLines(module.id),
  version: moduleVersion(module.id),
  counts: moduleCountLabel(module.id) || undefined,
}));

function ask(id: string) {
  writeHandoff([], `What does ${id} do, and how do I use it?`);
  window.location.href = "/chat";
}

export function ModuleGrid() {
  return (
    <section id="architecture" className="line-t line-b scroll-mt-[var(--dq-nav-h)]">
      <KitModuleGrid items={ITEMS} onAsk={ask} />
      <Reveal className="mx-auto max-w-[var(--frame-w)] px-[var(--page-pad)] pb-[clamp(2.25rem,5vw,3.5rem)] pt-[clamp(1.5rem,3vw,2.25rem)]">
        <ModuleManifest />
      </Reveal>
    </section>
  );
}
