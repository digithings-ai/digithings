"use client";

import { ProductStage } from "@/components/dashboard/product-stage";
import { Band } from "../_chrome/Band";

/** The product band, above the pipeline. The terminal UI and the web app
 *  stay on screen together and tour the same page. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      fill
      title="terminal UI, or web app"
      takeaway="The terminal UI and the web app are the same desk."
    >
      <ProductStage />
    </Band>
  );
}
