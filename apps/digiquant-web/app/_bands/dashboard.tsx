"use client";

import { ProductStage } from "@/components/dashboard/product-stage";
import { HOSTED_COPY, SELF_HOSTED_COPY, TOUR_CAPTION } from "@/components/dashboard/surface-tour";
import { Band } from "../_chrome/Band";

/** The product band, above the pipeline. A switch shows either the self-hosted
 *  terminal screens or the hosted web desk. One surface is in the frame. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      fill
      status="desk"
      title="Self-hosted, or hosted"
      takeaway={`${SELF_HOSTED_COPY} ${HOSTED_COPY} ${TOUR_CAPTION}`}
    >
      <ProductStage />
    </Band>
  );
}
