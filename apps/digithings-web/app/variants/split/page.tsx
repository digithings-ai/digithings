import type { Metadata } from "next";

import { BentoCell, BentoGrid, CtaLink, Emblem, moduleById } from "@digithings/ui";
import { FloatNav } from "@/app/_variants/headers";
import { Bleed, BlockLabel, ComposeCrop } from "@/app/_variants/parts";
import { BENTO, CLAIM, COUNTS, LEDE, ROADMAP_ROWS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";

// V5 · Split — full-bleed under a bar that yields. A true half-and-half hero
// with the real compose table as the visual. Exploration only.

export const metadata: Metadata = {
  title: "V5 · Split — variant",
  robots: { index: false, follow: false },
};

export default function VariantSplit() {
  return (
    <>
      <FloatNav />

      <main id="main" tabIndex={-1}>
        {/* No nav offset on purpose: this variant's whole point is that the page
            runs to the top edge and the bar arrives over it. */}
        <Bleed className="grid items-center gap-[2.5rem] border-b border-hair py-[var(--page-step)] min-[900px]:grid-cols-2">
          <div>
            <BlockLabel>open core · self-hosted · MIT</BlockLabel>
            <h1 className="mt-[1rem] mb-0 max-w-[18ch] font-mono text-[length:var(--type-hero)] font-medium leading-[1.14] tracking-[-0.02em] text-ink">
              {CLAIM}
            </h1>
            <p className="mt-[1.1rem] mb-0 max-w-[50ch] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
              {LEDE}
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="/chat" variant="ghost">
                Ask digichat
              </CtaLink>
            </div>
          </div>
          <ComposeCrop />
        </Bleed>

        <Bleed className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>the stack, at a glance</BlockLabel>
          <p className="mt-[0.7rem] mb-0 max-w-[62ch] text-[0.95rem] text-ink-soft">
            {COUNTS.shipping} modules ship today. Weight in the grid follows tier: the supervisor
            anchors it, the flagship runs wide, the rest take a cell each.
          </p>
          <div className="mt-[1.6rem]">
            {/* Three columns, so the spans have to tile 3-wide: the hero (2x2) and
                the tall cell (1x2) fill rows 1–2 exactly, and the nine units fill
                the 3x3 below. The `wide` span would leave a hole here — it wants
                a 2-column cell but only 1 column remains on its row — so
                digiquant renders as a unit in this variant, and the roadmap pair
                moves to its own labelled row underneath. */}
            <BentoGrid className="[grid-template-columns:repeat(3,minmax(0,1fr))] max-[760px]:[grid-template-columns:1fr]">
              {BENTO.map(({ id, span }) => {
                const m = moduleById(id);
                if (!m) return null;
                return (
                  <BentoCell key={id} span={span === "wide" ? "unit" : span} livery={m.emblem} className="gap-[0.6rem]">
                    <Emblem id={m.emblem} size={span === "hero" ? 30 : 20} />
                    <div>
                      <p className={`m-0 font-mono text-ink ${span === "hero" ? "bento-name" : "text-[0.95rem]"}`}>
                        {m.name}
                      </p>
                      <p className="mt-[0.3rem] mb-0 text-[0.78rem] leading-[1.5] text-ink-soft">{m.role}</p>
                    </div>
                  </BentoCell>
                );
              })}
            </BentoGrid>
          </div>

          {/* The roadmap pair, moved out of the grid and labelled as what it is. */}
          <div className="mt-[1.6rem] border-t border-hair pt-[1.2rem]">
            <BlockLabel>roadmap · not shipped</BlockLabel>
            <div className="mt-[0.9rem] grid gap-[0.9rem] min-[700px]:grid-cols-2">
              {ROADMAP_ROWS.map((m) => (
                <BentoCell key={m.id} span="unit" livery={m.emblem} className="gap-[0.5rem]">
                  <Emblem id={m.emblem} size={18} />
                  <p className="m-0 font-mono text-[0.95rem] text-ink">{m.name}</p>
                  <p className="mt-[0.2rem] mb-0 text-[0.78rem] leading-[1.5] text-ink-soft">{m.role}</p>
                </BentoCell>
              ))}
            </div>
          </div>
        </Bleed>

        <Bleed className="py-[var(--page-step)]">
          <div className="flex flex-wrap items-end justify-between gap-[1.2rem]">
            <h2 className="m-0 max-w-[26ch] font-mono text-[length:var(--type-section)] font-medium leading-[1.35] text-ink">
              Take the whole stack, or one module and leave the rest.
            </h2>
            <div className="flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="https://github.com/digithings-ai/digithings" external variant="ghost">
                Browse the repository
              </CtaLink>
            </div>
          </div>
        </Bleed>
      </main>

      <DtFooter />
    </>
  );
}
