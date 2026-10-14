import type { Metadata } from "next";

import {
  CtaLink,
  Emblem,
  Figure,
  OdometerStrip,
  RepoActivity,
} from "@digithings/ui";
import { StandardNav } from "@/app/_variants/headers";
import { BlockLabel, Wide } from "@/app/_variants/parts";
import { CLAIM, COUNTS, LEDE, METRICS, MODULE_ROWS, REQUEST_PATH, ROADMAP_ROWS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_LIVE, REPO_URL, repoActivity } from "@/lib/repoActivity";

// V3 · Instrument — wide 1280. Figures above the fold, the stack as a table
// rather than cards, and the request path as a stage list. The stage list shows
// no timings on purpose: nothing here measures them. Exploration only.

export const metadata: Metadata = {
  title: "V3 · Instrument — variant",
  robots: { index: false, follow: false },
};

const HEAD = "font-mono text-[0.68rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute";

export default function VariantInstrument() {
  return (
    <>
      <StandardNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Wide className="border-b border-hair py-[var(--page-step)]">
          <div className="grid items-start gap-[2.5rem] min-[960px]:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
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
            <Figure n={1} caption={`Counted ${COUNTS.countedAt} — file counts, not coverage.`}>
              <OdometerStrip stats={METRICS} />
            </Figure>
          </div>
        </Wide>

        <Wide className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>the stack, as data</BlockLabel>
          <div className="mt-[1.2rem] overflow-x-auto">
            <table className="w-full border-collapse text-left font-mono text-[0.8rem]">
              <thead>
                <tr>
                  <th className={`border-b border-hair p-[0.6rem] font-normal ${HEAD}`}>module</th>
                  <th className={`border-b border-hair p-[0.6rem] font-normal ${HEAD}`}>tier</th>
                  <th className={`border-b border-hair p-[0.6rem] font-normal ${HEAD}`}>role</th>
                  <th className={`border-b border-hair p-[0.6rem] text-right font-normal ${HEAD}`}>edges</th>
                  <th className={`border-b border-hair p-[0.6rem] font-normal ${HEAD}`}>docker</th>
                </tr>
              </thead>
              <tbody>
                {MODULE_ROWS.map((m) => (
                  <tr key={m.id}>
                    <td className="border-b border-hair p-[0.6rem] text-ink">
                      <span className="flex items-center gap-[0.5rem]">
                        <Emblem id={m.emblem} size={14} />
                        {m.name}
                      </span>
                    </td>
                    <td className="border-b border-hair p-[0.6rem] text-ink-soft">{m.tier}</td>
                    <td className="border-b border-hair p-[0.6rem] text-ink-soft">{m.role}</td>
                    <td className="border-b border-hair p-[0.6rem] text-right text-ink-mute">{m.deps}</td>
                    <td className="border-b border-hair p-[0.6rem] text-ink-mute">{m.dockerCmd ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-[0.9rem] mb-0 font-mono text-[0.72rem] text-ink-mute">
            {ROADMAP_ROWS.length} of {MODULE_ROWS.length} rows are roadmap. Edges are registry edges,
            not runtime calls.
          </p>
        </Wide>

        <Wide className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>what happens to a request</BlockLabel>
          <p className="mt-[0.7rem] mb-0 max-w-[62ch] text-[0.95rem] text-ink-soft">
            No durations are shown because this repository does not measure them per hop. The
            sequence is the documented one; the timing column is deliberately empty.
          </p>
          <ul className="mt-[1.4rem] m-0 grid list-none gap-0 p-0">
            {REQUEST_PATH.map((stage, i) => (
              <li key={stage.label} className="grid gap-[0.4rem] border-t border-hair py-[0.8rem] last:border-b sm:grid-cols-[3rem_10rem_1fr_5rem] sm:items-baseline sm:gap-[1rem]">
                <span className="font-mono text-[0.72rem] text-ink-mute">{String(i + 1).padStart(2, "0")}</span>
                <span className="font-mono text-[0.85rem] text-ink">{stage.label}</span>
                <span className="text-[0.9rem] text-ink-soft">{stage.detail}</span>
                <span className="text-right font-mono text-[0.8rem] text-ink-mute">—</span>
              </li>
            ))}
          </ul>
        </Wide>

        <Wide className="border-b border-hair py-[var(--page-step)]">
          <BlockLabel>fig 2 · the repository</BlockLabel>
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

        <Wide className="py-[var(--page-step)]">
          <div className="flex flex-wrap items-center justify-between gap-[1rem]">
            <h2 className="m-0 max-w-[30ch] font-mono text-[length:var(--type-section)] font-medium leading-[1.35] text-ink">
              Nine modules. One compose file. Your hosts.
            </h2>
            <div className="flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="/security" variant="ghost">
                Review security
              </CtaLink>
            </div>
          </div>
        </Wide>
      </main>

      <DtFooter />
    </>
  );
}
