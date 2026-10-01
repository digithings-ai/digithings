import { CtaLink, MediaFrame } from "@digithings/ui";
import { DASHBOARD_VIDEO_POSTER, DASHBOARD_VIDEO_SRC } from "@/components/dashboard/dashboard-video";
import { PortfolioIsland } from "@/components/live/portfolio-island";
import { Band } from "../_chrome/Band";
import { DashboardViewPlaceholder } from "../_placeholders";

/** What the dashboard holds, as a ledger. The surfaces live in the dashboard app,
 *  not on this site. */
const DASHBOARD_SURFACES: { key: string; value: string }[] = [
  { key: "strategy builder", value: "Describe a strategy in chat, backtest it on Nautilus, inspect it, hand it off. In development." },
  { key: "strategies", value: "Each strategy with its backtest tearsheet. In-sample and illustrative." },
  { key: "journal", value: "Notes kept next to the runs and strategies they belong to." },
  { key: "tools", value: "Research data, MCP tools and LuxAlgo, reached from inside the app." },
];

/** The product band: the dashboard view (a labelled placeholder until a recording
 *  or screenshot exists), what it holds, and the paper book it shows. The dashboard
 *  is a separate app and is not embedded here. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      tint
      status={DASHBOARD_VIDEO_SRC ? "recording" : "recording to come"}
      title="The dashboard is the product"
      takeaway="Build strategies, read the results and keep notes in one app. This page shows it; the tools live there."
    >
      <div className="flex flex-col gap-4">
        {DASHBOARD_VIDEO_SRC ? (
          <MediaFrame
            src={DASHBOARD_VIDEO_SRC}
            poster={DASHBOARD_VIDEO_POSTER}
            title="dashboard walkthrough"
            badge="Recorded walkthrough"
            placeholderLabel="recording to come"
            caption="A recorded walkthrough of the dashboard."
          />
        ) : (
          <DashboardViewPlaceholder />
        )}

        <dl className="m-0 border border-hair bg-surface text-left font-mono text-[0.72rem] leading-[1.55]">
          {DASHBOARD_SURFACES.map((row) => (
            <div key={row.key} className="grid border-b border-hair last:border-b-0 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <dt className="px-3 pb-0 pt-2 text-ink-mute sm:border-e sm:border-hair sm:pb-2">[ {row.key} ]</dt>
              <dd className="m-0 px-3 pb-2 pt-0 font-sans text-[0.8125rem] text-ink-soft sm:pt-2">{row.value}</dd>
            </div>
          ))}
        </dl>

        <PortfolioIsland />

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.8125rem] text-ink-soft">
          <CtaLink
            href="/dashboard/"
            variant="ghost"
            className="hero-action h-auto border border-hair bg-transparent px-4 py-[0.7rem] font-mono text-[0.8rem] text-ink no-underline hover:bg-surface-2"
          >
            Open the dashboard
          </CtaLink>
          <span>The paper book above is a research portfolio. No real money is in it.</span>
        </div>
      </div>
    </Band>
  );
}
