"use client";

import {
  ModuleGrid as KitModuleGrid,
  modules,
  type ModuleGridItem,
  type ModuleNode,
} from "@digithings/ui";
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
 *  in the mosaic reserved empty weight. digivoice takes their place: it is
 *  live, and it is not in the shared module registry, so the stack section
 *  stays as approved. digibook is the docs book, not a module card. */
const LANDING_MODULES = modules.filter(
  (module) => module.id !== "digistore" && module.id !== "digilink",
);

/** Tracked text lines under digivoice/, counted the same way as the activity snapshot. */
const DIGIVOICE_LINES = 20_723;

const DIGIVOICE_MODULE: ModuleNode = {
  id: "digivoice",
  name: "digivoice",
  tier: "support",
  graphOrder: 11,
  graph: { x: 0, y: 0, r: 20 },
  emblem: "digivoice",
  role: "Local speech · whisper.cpp · Piper",
  tagline: "Dictation and speech on the machine, with a terminal UI.",
  summary: [
    "A local command line for dictation and speech: whisper.cpp takes the microphone, Piper plays the readout, and every take is appended to a session history. Speech stays on the machine.",
  ],
  stack: [
    { name: "whisper.cpp", icon: null, mono: "W" },
    { name: "Piper", icon: null, mono: "Pi" },
    { name: "Pydantic", icon: "pydantic" },
  ],
  dockerCmd: null,
  initSnippet: { lang: "bash", code: "digivoice doctor" },
  api: [{ label: "Doctor", code: "digivoice doctor" }],
  links: [{ label: "Source", href: "https://github.com/digithings-ai/digithings" }],
  related: ["digichat"],
};

const ITEMS: ModuleGridItem[] = [
  ...LANDING_MODULES.map((module) => ({
    module,
    lines: moduleLines(module.id),
    version: moduleVersion(module.id),
    counts: moduleCountLabel(module.id) || undefined,
    mark: markFor(module.id),
  })),
  {
    module: DIGIVOICE_MODULE,
    lines: DIGIVOICE_LINES,
    version: "0.1.0",
    mark: markFor("digivoice"),
  },
];

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
