import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { StandardNav } from "@/app/_variants/headers";
import { Doc, BlockLabel } from "@/app/_variants/parts";
import { ModuleGraphField } from "@/components/landing/concepts/ModuleGraphField";

// DIG-3319 concept 1 — module graph. Exploration only, not wired into `/`.

export const metadata: Metadata = {
  title: "hero concept 1 · module graph — exploration",
  robots: { index: false, follow: false },
};

export default function HeroConceptModuleGraph() {
  return (
    <>
      <StandardNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <section className="pixel-hero border-b border-hair">
          <ModuleGraphField />
          <Doc className="relative z-10 flex flex-col items-center py-[4rem] text-center">
            <BlockLabel>DIG-3319 · concept 1 of 3</BlockLabel>
            <h1 className="m-0 mt-[1rem] font-display text-[1.6rem] font-semibold leading-[1.25] tracking-[-0.02em] text-ink sm:text-[1.9rem]">
              Module graph
            </h1>
            <p className="m-0 mt-[0.9rem] max-w-[46ch] text-[0.9375rem] leading-[1.6] text-ink-soft">
              Nine fixed nodes, one per digi module, linked by the edges they actually share data
              over. Pulses travel the links to read as live data flow between modules — the
              subject the ticket suggested in place of the world map.
            </p>
            <p className="m-0 mt-[1.2rem] font-mono text-[0.78rem] text-ink-mute">
              kept: pixel-grid cells · mouse trail · smooth perf — changed: subject (no map),
              trail (monochrome ink, no rainbow)
            </p>
          </Doc>
        </section>
      </main>
      <DtFooter />
    </>
  );
}
