"use client";

import { TerminalDesk } from "@/components/dashboard/terminal-desk";
import { Band } from "../_chrome/Band";

/** The product band: the same portfolio windows as the digiquant terminal
 *  (book, sleeves, movers, holdings, NAV, drawdown) on a 12×12 grid.
 *  Figures come from the public house-book read. A missing figure is an em dash. */
export function DashboardBand() {
  return (
    <Band
      id="dashboard"
      fill
      status="paper book"
      title="The dashboard is the product"
      takeaway="The house book, in the terminal's portfolio windows. A figure appears only when that read has it. Otherwise it is an em dash."
    >
      <TerminalDesk />
    </Band>
  );
}
