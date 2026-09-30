import { CtaLink, MediaFrame } from "@digithings/ui";
import { DASHBOARD_VIDEO_POSTER, DASHBOARD_VIDEO_SRC } from "@/components/dashboard/dashboard-video";
import { PortfolioIsland } from "@/components/live/portfolio-island";
import { Band } from "../_chrome/Band";

/** Centred, tinted band: the walkthrough recording on top (a labelled
 *  placeholder until one exists), a rail down to the paper book below it. The
 *  dashboard itself is a separate app and is not embedded here. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      layout="center"
      tint
      status={DASHBOARD_VIDEO_SRC ? "recording" : "recording to come"}
      title="The dashboard"
      takeaway="The book, the run and the results in one view."
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
              : "A walkthrough of the dashboard will go here once the dashboard UI rebuild is done."
          }
        />

        <div className="mx-auto flex flex-col items-center font-mono text-[0.66rem] tracking-[0.06em] text-ink-mute" aria-hidden="true">
          <span className="h-6 border-s border-hair" />
          <span className="border border-hair bg-surface px-3 py-1">[ the book it shows ]</span>
          <span className="h-6 border-s border-hair" />
        </div>

        <PortfolioIsland />

        <p className="m-0 mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-center font-mono text-[0.72rem] leading-[1.6] text-ink-soft">
          <span>The dashboard is its own app and cannot be embedded on this page.</span>
          <CtaLink href="/dashboard/" variant="ghost" className="h-auto border border-hair bg-transparent px-3 py-1.5 font-mono text-[0.72rem] text-ink no-underline hover:bg-surface-2">
            Open the dashboard
          </CtaLink>
        </p>
      </div>
    </Band>
  );
}
