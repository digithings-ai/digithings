import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { StandardNav } from "@/app/_variants/headers";
import { BlockLabel, Doc, Specimen } from "@/app/_variants/parts";

// DIG-3319 concept index. Routes are /variants/hero-concepts/<slug> (this folder).
// noindex, absent from sitemap.ts, and not linked from the public nav.

export const metadata: Metadata = {
  title: "hero concepts — exploration",
  robots: { index: false, follow: false },
};

type Concept = {
  slug: string;
  name: string;
  subject: string;
  note: string;
};

const CONCEPTS: Concept[] = [
  {
    slug: "module-graph",
    name: "1 · Module graph",
    subject: "nodes + links",
    note: "Nine fixed nodes, one per digi module, linked by the edges they actually share data over. Pulses travel the links as live data flow — the subject the ticket itself suggested in place of the world map.",
  },
  {
    slug: "circuit-trace",
    name: "2 · Circuit trace",
    subject: "PCB rails + vias",
    note: "Orthogonal rails and vias replace the land bitmap entirely. Traveling signal pulses read as “a traced request path,” the phrase already in the hero copy.",
  },
  {
    slug: "glass-rings",
    name: "3 · Glass rings",
    subject: "nested frames",
    note: "Nested square frames pulse outward from center — pure geometry, no map. A literal echo of the headline: “AI infrastructure, in a glass box you own.”",
  },
];

export default function HeroConceptsIndex() {
  return (
    <>
      <StandardNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Doc className="pt-[var(--page-step)]">
          <BlockLabel>DIG-3319 · exploration · not shipped</BlockLabel>
          <h1 className="mt-[0.9rem] mb-0 font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
            Three replacements for the hero.
          </h1>
          <p className="mt-[1.1rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            The current hero is an animated pixel-grid world map with exchange hubs and a
            rainbow mouse trail, copied from another site. These three concepts keep the
            pixel-grid cube effect, the mouse-trail mechanic and the performance, but replace the
            world map with an original subject and the rainbow trail with a monochrome ink
            trail. Nothing here is wired into <span className="text-ink">/</span>.
          </p>

          <div className="mt-[2rem] grid gap-[0.8rem]">
            {CONCEPTS.map((c) => (
              <Specimen key={c.slug}>
                <div className="flex flex-wrap items-baseline justify-between gap-[0.8rem]">
                  <a
                    href={`/variants/hero-concepts/${c.slug}`}
                    className="font-mono text-[0.95rem] text-ink underline-offset-[3px] hover:underline"
                  >
                    {c.name}
                  </a>
                  <span className="font-mono text-[var(--type-meta)] text-ink-mute">
                    {c.subject}
                  </span>
                </div>
                <p className="mt-[0.6rem] mb-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.7] text-ink-soft">
                  {c.note}
                </p>
              </Specimen>
            ))}
          </div>
        </Doc>
      </main>
      <DtFooter />
    </>
  );
}
