"use client";

/**
 * AllocationTreemap specimen — squarified, area = value, tone = a second
 * number, labelled, selectable. From @digithings/ui/ui.
 */
import { useState } from "react";

import { AllocationTreemap } from "@digithings/ui/ui";

const ITEMS = [
  { id: "spy", label: "SPY", value: 28, detail: "28.0%" },
  { id: "qqq", label: "QQQ", value: 18, detail: "18.0%" },
  { id: "tlt", label: "TLT", value: 14, detail: "14.0%" },
  { id: "gld", label: "GLD", value: 10, detail: "10.0%" },
  { id: "efa", label: "EFA", value: 9, detail: "9.0%" },
  { id: "vnq", label: "VNQ", value: 7, detail: "7.0%" },
  { id: "dbc", label: "DBC", value: 5, detail: "5.0%" },
  { id: "cash", label: "Cash", value: 9, detail: "9.0%" },
];

export function TreemapReference() {
  const [sel, setSel] = useState<string | null>("spy");
  return (
    <section className="section-block">
      <p className="kicker">{"// allocation treemap"}</p>
      <h2 className="title">Book allocation, by area.</h2>
      <p className="section-copy">
        <code>AllocationTreemap</code> lays items out with a squarified algorithm; a single-hue
        accent ramp carries tone (never up/down — allocation is not P&amp;L). Selected:{" "}
        <code>{sel ?? "none"}</code>.
      </p>
      <AllocationTreemap items={ITEMS} selectedId={sel} onSelect={setSel} />
    </section>
  );
}
