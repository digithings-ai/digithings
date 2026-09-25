import type { Metadata } from "next";
import { Footer } from "@digithings/ui";
import { DQ_FOOTER, DQ_FOOTER_META } from "../../_nav";
import { SiteNav } from "@/components/landing/SiteNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { SdcaRecalibrationComparison } from "@/components/tearsheet/sdca-recalibration-comparison";

export const metadata: Metadata = {
  title: "SDCA recalibration v1 — digiquant research",
  description:
    "Local-only comparison of the BTC-SDCA recalibration v1 research rounds against the live validated candidate.",
};

// Local-only research page (SDCA recalibration v1). Not linked from primary
// nav and not a published/production strategy listing — every non-live card
// here is a diagnostic tearsheet served from the static-JSON fallback in
// lib/live/strategies.ts, never pushed to Supabase. See
// digiquant/src/digiquant/strategies/sdca/RESEARCH_STATE.md for the full
// round-by-round research ledger this page visualizes.
export default function SdcaRecalibrationPage() {
  return (
    <>
      <SiteNav />
      <main className="dq-subpage pb-[clamp(4.5rem,10vw,7rem)]">
        <AmbientMesh />
        <div className="wrap pb-[1.5rem]">
          <header className="dq-sechead">
            <div className="kicker">{"// research"}</div>
            <h1 className="dq-title">SDCA recalibration v1</h1>
            <p className="dq-sub">
              A local-only side-by-side of every BTC-SDCA recalibration round tried this cycle
              (1 through 4, plus the round 8 post-mortem follow-up) against the current live
              validated candidate. None of the rounds below were promoted — each card links to
              its own full tearsheet so the arc across rounds is visible at a glance instead of
              buried in a research log.
            </p>
          </header>
          <SdcaRecalibrationComparison />
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
