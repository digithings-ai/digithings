"use client";

import { ProductStage } from "@/components/dashboard/product-stage";
import { Band } from "../_chrome/Band";

/** The product band, above the pipeline. The terminal and the hosted desk
 *  stay on screen together and tour the same page. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      fill
      title="Self-hosted, or hosted"
      takeaway="The terminal and the hosted desk are the same product."
    >
      <ProductStage />
    </Band>
  );
}
