"use client";

import { ProductStage } from "@/components/dashboard/product-stage";
import { Band } from "../_chrome/Band";

/** The product band, above the pipeline. One centered desk: the terminal UI
 *  first, then the web app. The copy above the frame follows the view. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      fill
      title="terminal UI, or web app"
      takeaway="The terminal UI and the web app are nearly one to one. The note above the desk follows the view."
    >
      <ProductStage />
    </Band>
  );
}
