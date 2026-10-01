import { CtaLink, MediaFrame } from "@digithings/ui";
import { DASHBOARD_VIDEO_POSTER, DASHBOARD_VIDEO_SRC } from "@/components/dashboard/dashboard-video";
import { PortfolioIsland } from "@/components/live/portfolio-island";
import { Band } from "../_chrome/Band";

/** What the dashboard holds. Shown as a ledger on the showcase: the surfaces live in
 *  the dashboard app, not on this site. Statuses follow the product rows. */
const DASHBOARD_SURFACES: { key: string; value: string }[] = [
  { key: "strategy builder", value: "describe an idea in chat, backtest it on Nautilus, inspect and hand it off · in development" },
  { key: "strategies", value: "every strategy with its backtest tearsheet, labelled in-sample and illustrative" },
  { key: "journal", value: "decisions and notes kept next to the runs they came from" },
  { key: "tools and integrations", value: "research data, the MCP tools and LuxAlgo, reached from inside the app" },
];

/** Centred, tinted band: the dashboard recording on top (a labelled placeholder
 *  until one exists), a ledger of what the dashboard holds, and a rail down to the
 *  paper book it shows. The dashboard itself is a separate app and is not embedded
 *  here; this band demonstrates it. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      layout="center"
      tint
      status={DASHBOARD_VIDEO_SRC ? "recording" : "recording to come"}
      title="The dashboard is the product"
      takeaway="One app for building strategies, keeping the journal and running the tools. This is a look at it, not the app."
    >
      <div className="mx-auto flex max-w-[52rem] flex-col items-stretch">
        <MediaFrame
          src={DASHBOARD_VIDEO_SRC}
          poster={DASHBOARD_VIDEO_POSTER}
          title="dashboard walkthrough"
          badge={DASHBOARD_VIDEO_SRC ? "Recorded walkthrough" : "Placeholder · no recording yet"}
          placeholderLabel="recording to come"
          caption={
            DASHBOARD_VIDEO_SRC
              ? "A recorded walkthrough of the dashboard."
              : "A recorded walkthrough of the dashboard will go here once the dashboard UI rebuild is done."
          }
        />

        <dl className="m-0 mt-3 border border-hair bg-surface text-left font-mono text-[0.7rem] leading-[1.5]">
          {DASHBOARD_SURFACES.map((row) => (
            <div key={row.key} className="grid border-b border-hair last:border-b-0 sm:grid-cols-[13rem_minmax(0,1fr)]">
              <dt className="px-3 pb-0 pt-2 text-ink-mute sm:border-e sm:border-hair sm:pb-2">[ {row.key} ]</dt>
              <dd className="m-0 px-3 pb-2 pt-0 text-ink-soft sm:pt-2">{row.value}</dd>
            </div>
          ))}
        </dl>

        <div className="mx-auto flex flex-col items-center font-mono text-[0.66rem] tracking-[0.06em] text-ink-mute" aria-hidden="true">
          <span className="h-6 border-s border-hair" />
          <span className="border border-hair bg-surface px-3 py-1">[ a slice of the paper book it shows ]</span>
          <span className="h-6 border-s border-hair" />
        </div>

        <PortfolioIsland />

        <p className="m-0 mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-center font-mono text-[0.72rem] leading-[1.6] text-ink-soft">
          <span>The tools live in the dashboard. This page only shows them.</span>
          <CtaLink href="/dashboard/" variant="ghost" className="h-auto border border-hair bg-transparent px-3 py-1.5 font-mono text-[0.72rem] text-ink no-underline hover:bg-surface-2">
            Open the dashboard
          </CtaLink>
        </p>
      </div>
    </Band>
  );
}
