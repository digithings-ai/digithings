"use client";

import { ModuleGrid as KitModuleGrid, modules, type ModuleGridItem } from "@digithings/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { moduleLines } from "@/lib/repoActivity";
import { moduleCountLabel, moduleVersion } from "@/lib/moduleCounts";

/**
 * The landing's module mosaic and its `#architecture` anchor: the kit
 * `ModuleGrid` fed this repo's line counts, versions and endpoint/tool counts.
 * "ask digichat" hands the question to `/chat`.
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
    </section>
  );
}
