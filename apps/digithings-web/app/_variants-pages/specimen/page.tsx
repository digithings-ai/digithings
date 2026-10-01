import type { Metadata } from "next";

import {
  CtaLink,
  Figure,
  GlyphList,
  GlyphRow,
  Mono,
  OdometerStrip,
  RepoActivity,
} from "@digithings/ui";
import { StandardNav } from "@/app/_variants/headers";
import { AuditCrop, ByokCrop, BlockLabel, ComposeCrop, Doc, Specimen } from "@/app/_variants/parts";
import { StackTabs } from "@/app/_variants/stack-tabs";
import { CLAIM, COUNTS, LEDE, METRICS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_LIVE, REPO_URL, repoActivity } from "@/lib/repoActivity";

// V2 · Specimen frames — document width. The design reference's own rhythm: the
// page is a stack of labelled, bordered blocks, and the stack itself can be
// re-cut three ways. Exploration only.

export const metadata: Metadata = {
  title: "V2 · Specimen frames — variant",
  robots: { index: false, follow: false },
};

export default function VariantSpecimen() {
  return (
    <>
      <StandardNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Doc className="grid gap-[1rem] pt-[var(--page-step)]">
          <Specimen label="the claim">
            <h1 className="m-0 max-w-[22ch] font-mono text-[length:var(--type-hero)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
              {CLAIM}
            </h1>
            <p className="mt-[1.1rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
              {LEDE}
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="/chat" variant="ghost">
                Ask digichat
              </CtaLink>
            </div>
          </Specimen>

          <Specimen label="the stack · eleven modules">
            <StackTabs />
          </Specimen>

          <Specimen label="what it buys you">
            <div className="grid gap-[1.6rem]">
              <div className="grid items-center gap-[1.4rem] min-[900px]:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
                <div>
                  <BlockLabel>one file</BlockLabel>
                  <h3 className="mt-[0.5rem] mb-0 font-mono text-[1.05rem] text-ink">
                    Self-hosted, loopback by default
                  </h3>
                  <p className="mt-[0.6rem] mb-0 max-w-[42ch] text-[0.92rem] text-ink-soft">
                    One <Mono>docker-compose.yml</Mono> brings up {COUNTS.compose} services, every
                    one bound to <Mono>127.0.0.1</Mono>.
                  </p>
                </div>
                <ComposeCrop />
              </div>
              <div className="grid items-center gap-[1.4rem] border-t border-hair pt-[1.6rem] min-[900px]:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
                <ByokCrop />
                <div>
                  <BlockLabel>bring your own key</BlockLabel>
                  <h3 className="mt-[0.5rem] mb-0 font-mono text-[1.05rem] text-ink">
                    Forwarded per request, never stored
                  </h3>
                  <p className="mt-[0.6rem] mb-0 max-w-[42ch] text-[0.92rem] text-ink-soft">
                    The key lives in the page&rsquo;s memory for one tab; the site persists two
                    preference strings and {COUNTS.keysStored} keys.
                  </p>
                </div>
              </div>
              <div className="grid items-center gap-[1.4rem] border-t border-hair pt-[1.6rem] min-[900px]:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
                <div>
                  <BlockLabel>audit on by default</BlockLabel>
                  <h3 className="mt-[0.5rem] mb-0 font-mono text-[1.05rem] text-ink">
                    Every hop lands on your disk
                  </h3>
                  <p className="mt-[0.6rem] mb-0 max-w-[42ch] text-[0.92rem] text-ink-soft">
                    Redacted by key name on the way in, appended, never rewritten.
                  </p>
                </div>
                <AuditCrop />
              </div>
            </div>
          </Specimen>

          <Specimen label={`fig 1 · counted ${COUNTS.countedAt}`}>
            <Figure n={1} caption="Single-sourced in lib/siteCounts.ts, each figure with the command that produced it.">
              <OdometerStrip stats={METRICS} />
            </Figure>
          </Specimen>

          <Specimen label="fig 2 · the repository">
            <RepoActivity
              variant="detailed"
              snapshot={repoActivity}
              repoUrl={REPO_URL}
              live={REPO_LIVE}
              cloneCommand={REPO_CLONE}
              contributingUrl={CONTRIBUTING_URL}
            />
          </Specimen>

          <Specimen label="what is not built">
            <GlyphList>
              <GlyphRow label="Two modules are roadmap">
                digistore and digilink are badged in the grid above rather than counted as shipped.
              </GlyphRow>
              <GlyphRow label="No hosted product">
                There is no managed tenant and no usage bill. You run the software.
              </GlyphRow>
              <GlyphRow label="Live trading is stubbed">
                Broker adapters raise <Mono>NotImplementedError</Mono>; a human co-sign hook and
                review guard them, not a runtime interlock.
              </GlyphRow>
            </GlyphList>
          </Specimen>

          <Specimen label="close">
            <p className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
              The whole monorepo is MIT-licensed and public — take it and run it yourself.
            </p>
            <div className="mt-[1.4rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="/security" variant="ghost">
                Review security
              </CtaLink>
            </div>
          </Specimen>
        </Doc>
      </main>

      <DtFooter />
    </>
  );
}
