"use client";

import { ModuleGrid as KitModuleGrid, Reveal, modules, type ModuleGridItem } from "@digithings/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { moduleLines } from "@/lib/repoActivity";
import { moduleCountLabel, moduleVersion } from "@/lib/moduleCounts";
import { ModuleManifest } from "./ModuleManifest";
import { SectionHead } from "./SectionHead";

/**
 * The landing's module mosaic and its `#architecture` anchor: the kit
 * `ModuleGrid` fed this repo's line counts, versions and endpoint/tool counts.
 * "ask digichat" hands the question to `/chat`.
 *
 * Below the mosaic, the shared `<TerminalManifest>` process list
 * (`ModuleManifest`) stays on the home page so the Deploy dist/ contract
 * (`aria-label="digithings module manifest"`) keeps matching — the mosaic
 * replaced the old sole listing, but the pane marker is still the contract
 * for folded `/modules/*` and `/architecture` routes.
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
      <Reveal className="mx-auto max-w-[var(--frame-w)] px-[var(--page-pad)] pt-[clamp(2.25rem,5vw,3.5rem)]">
        <SectionHead
          id="architecture"
          title="The stack, sized by its code"
          lede="Each tile is a module and its area is its share of the lines of code. Scroll to walk them, biggest first."
        />
      </Reveal>
      <KitModuleGrid items={ITEMS} onAsk={ask} />
      <Reveal className="mx-auto max-w-[var(--frame-w)] px-[var(--page-pad)] pb-[clamp(2.25rem,5vw,3.5rem)] pt-[clamp(1.5rem,3vw,2.25rem)]">
        <ModuleManifest />
      </Reveal>
    </section>
  );
}
