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
 * lines of code"`, checked by `scripts/build-digithings.sh`. It is the only
 * one: the folded `/modules/*` and `/architecture` routes this pane used to
 * back are gone, so `ModuleManifest` stays for the module prose it still
 * carries, not as a contract marker.
 */
