import { CtaLink, MediaFrame } from "@digithings/ui";
import { DASHBOARD_VIDEO_POSTER, DASHBOARD_VIDEO_SRC } from "@/components/dashboard/dashboard-video";
import { Band } from "../_chrome/Band";
import { DashboardViewPlaceholder } from "../_placeholders";

/** What the dashboard holds, as a ledger. The surfaces live in the dashboard app,
 *  not on this site. */
const DASHBOARD_SURFACES: { key: string; value: string }[] = [
  { key: "strategy builder", value: "Describe a strategy in chat, test it against history, inspect it, hand it off. In development." },
  { key: "strategies", value: "Each strategy with its backtest tearsheet. In-sample and illustrative." },
  { key: "journal", value: "Notes kept next to the runs and strategies they belong to." },
  { key: "tools", value: "Research data and MCP tools, reached from inside the app." },
];

/** The product band: the dashboard view (a labelled placeholder until a recording
 *  or screenshot exists) beside what it holds. The dashboard is a separate app and
 *  is not embedded here. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      status={DASHBOARD_VIDEO_SRC ? "recording" : "recording to come"}
      title="The dashboard is the product"
      takeaway="Build strategies, read the results and keep notes in one app. This page shows it; the tools live there."
    >
      <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
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

        <div className="flex min-w-0 flex-col gap-4">
          <dl className="m-0 flex-1 border border-hair text-left font-mono text-[0.72rem] leading-[1.55]">
            {DASHBOARD_SURFACES.map((row) => (
              <div key={row.key} className="border-b border-hair px-3 py-2 last:border-b-0">
                <dt className="text-ink-mute">[ {row.key} ]</dt>
                <dd className="m-0 mt-1 font-sans text-[0.8125rem] text-ink-soft">{row.value}</dd>
              </div>
            ))}
          </dl>
          <div>
            <CtaLink
              href="/dashboard/"
              variant="ghost"
              className="hero-action h-auto border border-hair bg-transparent px-4 py-[0.7rem] font-mono text-[0.8rem] text-ink no-underline hover:bg-surface-2"
            >
              Open the dashboard
            </CtaLink>
          </div>
        </div>
      </div>
    </Band>
  );
}
