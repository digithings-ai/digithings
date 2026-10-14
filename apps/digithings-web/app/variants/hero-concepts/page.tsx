import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { StandardNav } from "@/app/_variants/headers";
import { BlockLabel, Doc, Specimen } from "@/app/_variants/parts";
import { LAYOUTS } from "@/components/landing/concepts/layouts";

// DIG-3319 concept index. Routes are /variants/hero-concepts/<layout> ([layout]/page.tsx).
// noindex, absent from sitemap.ts, and not linked from the public nav.

export const metadata: Metadata = {
  title: "hero concepts — exploration",
  robots: { index: false, follow: false },
};

export default function HeroConceptsIndex() {
  return (
    <>
      <StandardNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Doc className="pt-[var(--page-step)]">
          <BlockLabel>DIG-3319 · exploration · not shipped</BlockLabel>
          <h1 className="mt-[0.9rem] mb-0 font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
            Embedding map: three layouts.
          </h1>
          <p className="mt-[1.1rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            The base drawing is now a 2D embedding map of a knowledge base: clusters of meaning
            take the place of the continents, topic centroids pulse where the exchange hubs did,
            and queries land and reach for their nearest topics. An index sweep drifts across the
            map in place of day and night. Same cube field, same trail mechanic (monochrome ink),
            same performance. Pick a layout; nothing here is wired into{" "}
            <span className="text-ink">/</span>.
          </p>

          <div className="mt-[2rem] grid gap-[0.8rem]">
            {LAYOUTS.map((c) => (
              <Specimen key={c.slug}>
                <div className="flex flex-wrap items-baseline justify-between gap-[0.8rem]">
                  <a
                    href={`/variants/hero-concepts/${c.slug}`}
                    className="font-mono text-[0.95rem] text-ink underline-offset-[3px] hover:underline"
                  >
                    {c.name}
                  </a>
                  <span className="font-mono text-[var(--type-meta)] text-ink-mute">
                    {"embedding map"}
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
