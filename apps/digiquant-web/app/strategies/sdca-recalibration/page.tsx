import type { Metadata } from "next";
import { Footer } from "@digithings/ui";
import { DQ_FOOTER, DQ_FOOTER_META } from "../../_nav";
import { SiteNav } from "@/components/landing/SiteNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { SdcaRecalibrationComparison } from "@/components/tearsheet/sdca-recalibration-comparison";

export const metadata: Metadata = {
  title: "SDCA recalibration v1 — digiquant research",
  description:
    "Local-only comparison of every BTC-SDCA calibration attempt — ablation rounds, the validated baseline, live settings.json, and Task #93 — against the live production candidate.",
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
              A local-only side-by-side of every BTC-SDCA calibration attempt: ablation rounds 1
              through 4 plus the round 8 post-mortem follow-up, the canonical validated baseline
              from RESEARCH_STATE.md, what&apos;s actually live in settings.json right now, Task
              #93&apos;s rejected 17-indicator recalibration (rounds 2 and 3), and the current
              live production candidate. None of the research rounds below were promoted — each
              card links to its own full tearsheet so the full arc is visible at a glance instead
              of buried in a research log.
            </p>
          </header>
          <SdcaRecalibrationComparison />
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
