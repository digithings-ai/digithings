import type { Metadata } from "next";

import {
  BentoCell,
  BentoGrid,
  CopyCommand,
  CtaLink,
  Emblem,
  StackRow,
  moduleById,
} from "@digithings/ui";
import { StandardNav } from "@/app/_variants/headers";
import { BlockLabel, Doc } from "@/app/_variants/parts";
import { BENTO, CLAIM, COUNTS, INSTALL, MODULE_ROWS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";

// V6 · Registry — document width, no separate hero. The bento leads and the
// install command lives inside the hero cell; the page's spine is then an
// accordion over all eleven modules, plain <details> so it works with no JS.
// Exploration only.

export const metadata: Metadata = {
  title: "V6 · Registry — variant",
  robots: { index: false, follow: false },
};

const SUMMARY = "flex list-none items-baseline gap-[0.9rem] py-[0.8rem] [&::-webkit-details-marker]:hidden";

export default function VariantRegistry() {
  return (
    <>
      <StandardNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Doc className="pt-[var(--page-step)]">
          <BlockLabel>open core · self-hosted · MIT</BlockLabel>
          <h1 className="mt-[0.9rem] mb-0 max-w-[24ch] font-mono text-[length:var(--type-hero)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            {CLAIM}
          </h1>

          <div className="mt-[1.6rem]">
            <BentoGrid>
              {BENTO.map(({ id, span }) => {
                const m = moduleById(id);
                if (!m) return null;
                const isHero = span === "hero";
                return (
                  <BentoCell key={id} span={span} livery={m.emblem} className="gap-[0.7rem]">
                    <div className="flex items-start justify-between gap-[0.6rem]">
                      <Emblem id={m.emblem} size={isHero ? 30 : 20} />
                      {m.tier === "roadmap" ? (
                        <span className="font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
                          roadmap
                        </span>
                      ) : null}
                    </div>
                    <div>
                      <p className={`m-0 font-mono text-ink ${isHero ? "bento-name" : "text-[0.95rem]"}`}>
                        {m.name}
                      </p>
                      <p className="mt-[0.3rem] mb-0 text-[0.78rem] leading-[1.5] text-ink-soft">{m.role}</p>
                    </div>
                    {/* The install command lives in the hero cell: the first
                        thing the page asks you to do is the thing that starts it. */}
                    {isHero ? (
                      <div className="mt-auto">
                        <CopyCommand samples={INSTALL} ariaLabel="Install command" />
                      </div>
                    ) : null}
                  </BentoCell>
                );
              })}
            </BentoGrid>
          </div>

          <div className="mt-[var(--page-step)] border-t border-hair pt-[0.8rem]">
            <BlockLabel>every module, in order</BlockLabel>
            <p className="mt-[0.7rem] mb-0 max-w-[var(--measure-prose)] text-[0.95rem] text-ink-soft">
              Open any row for the module&rsquo;s role, its real dependency list, and the compose
              command that starts it. {COUNTS.shipping} ship today; {COUNTS.roadmap} are roadmap.
            </p>

            <div className="mt-[1.4rem]">
              {MODULE_ROWS.map((m) => (
                <details key={m.id} className="border-b border-hair">
                  <summary className={SUMMARY}>
                    <Emblem id={m.emblem} size={16} />
                    <span className="font-mono text-[0.9rem] text-ink">{m.name}</span>
                    <span className="hidden text-[0.9rem] text-ink-soft min-[700px]:inline">{m.role}</span>
                    <span className="ml-auto font-mono text-[0.72rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
                      {m.tier === "roadmap" ? "roadmap" : `${m.deps} edges`}
                    </span>
                  </summary>
                  <div className="pb-[1.2rem] pl-[1.9rem]">
                    <p className="m-0 max-w-[62ch] text-[0.92rem] leading-[1.7] text-ink-soft">{m.tagline}</p>
                    <div className="mt-[1rem]">
                      <BlockLabel>depends on</BlockLabel>
                      <div className="mt-[0.6rem]">
                        <StackRow items={m.stack} />
                      </div>
                    </div>
                    {m.dockerCmd ? (
                      <div className="mt-[1rem]">
                        <BlockLabel>start it</BlockLabel>
                        <p className="mt-[0.5rem] mb-0 font-mono text-[0.85rem] text-ink">{m.dockerCmd}</p>
                      </div>
                    ) : null}
                  </div>
                </details>
              ))}
            </div>
          </div>

          <div className="mt-[2rem] flex flex-wrap items-center gap-[0.8rem]">
            <CtaLink href="/docs">Read the docs</CtaLink>
            <CtaLink href="/security" variant="ghost">
              Review security
            </CtaLink>
          </div>
        </Doc>
      </main>

      <DtFooter />
    </>
  );
}
