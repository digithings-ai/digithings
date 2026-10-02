"use client";

import { EmbeddedDesk } from "@/components/dashboard/embedded-desk";
import { Band } from "../_chrome/Band";

/** The product band: the digiquant terminal, embedded at /app. A walkthrough clicks
 *  Brief, Portfolio, and Pipeline until the reader takes the frame. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      fill
      status="terminal"
      title="The terminal is the product"
      takeaway="The digiquant terminal, in the frame. A walkthrough opens Brief, Portfolio, and Pipeline until you take the pointer, the wheel, a key, or Take control."
    >
      <EmbeddedDesk />
    </Band>
  );
}
