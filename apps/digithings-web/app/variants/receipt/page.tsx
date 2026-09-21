import type { Metadata } from "next";

import {
  CopyCommand,
  CtaLink,
  FeatureCell,
  Figure,
  GlyphList,
  GlyphRow,
  Mono,
  OdometerStrip,
  RepoActivity,
} from "@digithings/ui";
import { StandardNav } from "@/app/_variants/headers";
import { AuditCrop, BlockLabel, ByokCrop, ComposeCrop, Specimen, Wide } from "@/app/_variants/parts";
import { CLAIM, COUNTS, INSTALL, LEDE, METRICS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_LIVE, REPO_URL, repoActivity } from "@/lib/repoActivity";

// V7 · Receipt — wide 1280. The whole pitch in one dense frame, then the three
// source files side by side, then the repository as the receipts. Exploration
// only.

export const metadata: Metadata = {
  title: "V7 · Receipt — variant",
  robots: { index: false, follow: false },
};

export default function VariantReceipt() {
  return (
    <>
      <StandardNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Wide className="pt-[var(--page-step)]">
          <Specimen label="digithings · open core">
            <h1 className="m-0 max-w-[24ch] font-mono text-[length:var(--type-hero)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
              {CLAIM}
            </h1>
            <p className="mt-[1rem] mb-0 max-w-[62ch] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
              {LEDE}
            </p>

            <div className="mt-[1.8rem] grid gap-[1.4rem] min-[1000px]:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] min-[1000px]:items-end">
              <div>
                <BlockLabel>install</BlockLabel>
                <div className="mt-[0.6rem]">
                  <CopyCommand samples={INSTALL} ariaLabel="Install command" />
                </div>
              </div>
              <Figure n={1} caption={`Counted ${COUNTS.countedAt} — file counts, not coverage.`}>
                <OdometerStrip stats={METRICS} />
              </Figure>
            </div>
          </Specimen>
        </Wide>

        <Wide className="py-[var(--page-step)]">
          <BlockLabel>the three files that carry the claims</BlockLabel>
          <div className="mt-[1.4rem] grid gap-[1rem] min-[900px]:grid-cols-3">
            <div>
              <FeatureCell
                eyebrow="one file"
                outcome="Loopback by default"
                mechanism={`${COUNTS.compose} services, every one bound to 127.0.0.1 until you say otherwise.`}
                href="/docs"
                linkLabel="Deploy guide"
                linkAriaLabel="Read the digithings deploy guide"
                className="[grid-template-columns:1fr]"
              >
                <ComposeCrop />
              </FeatureCell>
            </div>
            <div>
              <FeatureCell
                eyebrow="bring your own key"
                outcome="Never stored"
                mechanism={`The key lives in one tab's memory; ${COUNTS.keysStored} keys are persisted, ever.`}
                href="/legal/privacy"
                linkLabel="Privacy notice"
                linkAriaLabel="Read the digithings privacy notice"
                className="[grid-template-columns:1fr]"
              >
                <ByokCrop />
              </FeatureCell>
            </div>
            <div>
              <FeatureCell
                eyebrow="audit on by default"
                outcome="Every hop on your disk"
                mechanism="One correlation id per request, one redacted JSONL line per event, in a file you own."
                href="/security"
                linkLabel="Security posture"
                linkAriaLabel="Read the digithings security posture"
                className="[grid-template-columns:1fr]"
              >
                <AuditCrop />
              </FeatureCell>
            </div>
          </div>
        </Wide>

        <Wide className="border-t border-hair py-[var(--page-step)]">
          <BlockLabel>fig 2 · the receipts</BlockLabel>
          <p className="mt-[0.7rem] mb-0 max-w-[62ch] text-[0.95rem] text-ink-soft">
            The committed repository snapshot. Every figure above can be reproduced from a clean
            checkout — the snapshot is dated so a stale one reads as dated.
          </p>
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
        </Wide>

        <Wide className="border-t border-hair py-[var(--page-step)]">
          <BlockLabel>what is not built</BlockLabel>
          <div className="mt-[1.2rem]">
            <GlyphList>
              <GlyphRow label="Two modules are roadmap">
                digistore and digilink are not shipped, and are not counted as such.
              </GlyphRow>
              <GlyphRow label="No hosted product">
                No managed tenant, no usage bill. The commercial offer is integration work.
              </GlyphRow>
              <GlyphRow label="Live trading is stubbed">
                Broker adapters raise <Mono>NotImplementedError</Mono>; a human co-sign hook and
                review guard them, not a runtime interlock.
              </GlyphRow>
            </GlyphList>
          </div>
          <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
            <CtaLink href="/docs">Read the docs</CtaLink>
            <CtaLink href="/security" variant="ghost">
              Every limit, on the security page
            </CtaLink>
          </div>
        </Wide>
      </main>

      <DtFooter />
    </>
  );
}
