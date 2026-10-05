import type { Metadata } from "next";

import {
  BentoCell,
  BentoGrid,
  Colophon,
  ContactMailto,
  CtaLink,
  Emblem,
  Figure,
  OdometerStrip,
  RepoActivity,
  SocialRow,
  Terminal,
  moduleById,
} from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { CommandStrip, StandardNav } from "@/app/_variants/headers";
import { Bleed, BlockLabel } from "@/app/_variants/parts";
import { BENTO, CLAIM, COUNTS, LEDE, METRICS, QUICKSTART } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_LIVE, REPO_URL, repoActivity } from "@/lib/repoActivity";
import { DT_CONTACT_EMAIL } from "@/app/_nav";

// V1 · Command bar — full-bleed. The install command is chrome (a strip above
// the bar), and the hero pairs the claim with the documented quick start.
// Exploration only.

export const metadata: Metadata = {
  title: "V1 · Command bar — variant",
  robots: { index: false, follow: false },
};

export default function VariantCommandBar() {
  return (
    <>
      <StandardNav />

      {/* The strip sits *under* the fixed bar and sticks there, so the command
          stays one click away for the whole scroll. The nav is fixed, so the
          page needs the offset — hence the padding on the wrapper rather than
          on `<main>`, which would push the strip down with it. */}
      <div className="pt-[var(--dq-nav-h)]">
        <div className="sticky top-[var(--dq-nav-h)] z-30">
          <CommandStrip />
        </div>

        <main id="main" tabIndex={-1}>
          <Bleed className="border-b border-hair py-[var(--page-step)]">
          <div className="grid items-start gap-[2.5rem] min-[900px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <BlockLabel>open core · self-hosted · MIT</BlockLabel>
              <h1 className="mt-[1rem] mb-0 max-w-[20ch] font-mono text-[length:var(--type-hero)] font-medium leading-[1.14] tracking-[-0.02em] text-ink">
                {CLAIM}
              </h1>
              <p className="mt-[1.1rem] mb-0 max-w-[52ch] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
                {LEDE}
              </p>
              <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
                <CtaLink href="/docs">Read the docs</CtaLink>
                <CtaLink href="/chat" variant="ghost">
                  Ask digichat
                </CtaLink>
              </div>
            </div>
            <Terminal title="README.md · quick start" lines={QUICKSTART} />
          </div>
        </Bleed>

        <Bleed className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>the stack, at a glance</BlockLabel>
          <div className="mt-[1.4rem]">
            <BentoGrid>
              {BENTO.map(({ id, span }) => {
                const m = moduleById(id);
                if (!m) return null;
                return (
                  <BentoCell key={id} span={span} livery={m.emblem} className="gap-[0.6rem]">
                    <div className="flex items-start justify-between gap-[0.6rem]">
                      <Emblem id={m.emblem} size={span === "hero" ? 30 : 20} />
                      {m.tier === "roadmap" ? (
                        <span className="font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
                          roadmap
                        </span>
                      ) : null}
                    </div>
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
        </Bleed>

        <Bleed className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>counted, not asserted</BlockLabel>
          <p className="mt-[0.7rem] mb-0 max-w-[60ch] text-[0.95rem] text-ink-soft">
            Counted {COUNTS.countedAt} on a clean checkout — {COUNTS.shipping} shipping modules,{" "}
            {COUNTS.compose} compose services, {COUNTS.backends} live vector backends,{" "}
            {COUNTS.keysStored} provider keys stored.
          </p>
          <div className="mt-[1.6rem] max-w-[1100px]">
            <Figure n={1} caption="Single-sourced in lib/siteCounts.ts.">
              <OdometerStrip stats={METRICS} />
            </Figure>
          </div>
        </Bleed>

        <Bleed className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>one public monorepo</BlockLabel>
          <div className="mt-[1.4rem]">
            <RepoActivity
              variant="detailed"
              snapshot={repoActivity}
              repoUrl={REPO_URL}
              live={REPO_LIVE}
              cloneCommand={REPO_CLONE}
              contributingUrl={CONTRIBUTING_URL}
            />
          </div>
        </Bleed>

        <Bleed className="py-[var(--page-step)]">
          <h2 className="m-0 max-w-[28ch] font-mono text-[length:var(--type-section)] font-medium leading-[1.35] text-ink">
            Questions, enterprise, or partnership.
          </h2>
          <div className="mt-[1.4rem] flex flex-wrap items-center gap-[0.8rem]">
            <ContactMailto
              email={DT_CONTACT_EMAIL}
              className={buttonVariants({ variant: "default" })}
              subject="digithings%20inquiry"
            >
              Email us
            </ContactMailto>
            <ContactMailto
              email={DT_CONTACT_EMAIL}
              className={buttonVariants({ variant: "ghost" })}
              subject="digithings%20enterprise"
            >
              Enterprise
            </ContactMailto>
            <span className="font-mono text-[length:var(--type-body)] text-ink-mute">
              <ContactMailto email={DT_CONTACT_EMAIL} showAddress>
                {DT_CONTACT_EMAIL}
              </ContactMailto>
            </span>
          </div>
          <div className="mt-[1.6rem]">
            <SocialRow />
          </div>
        </Bleed>
      </main>
      </div>

      <Colophon name="digi" suffix="things" />
      <DtFooter />
    </>
  );
}
