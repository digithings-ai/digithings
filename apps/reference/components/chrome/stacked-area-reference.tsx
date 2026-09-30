"use client";

/**
 * StackedAreaChart specimen — weights over time with a cash wash, from
 * @digithings/ui/ui. Click a column to lock a date; the dashed accent line
 * marks it. SVG only, token-dressed, no fetching.
 */
import { useState } from "react";

import { StackedAreaChart } from "@digithings/ui/ui";

const DATA = Array.from({ length: 12 }, (_, i) => {
  const eq = 38 + i * 1.5;
  const bd = 34 - i;
  const cash = 8 + (i % 4);
  const alt = 100 - eq - bd - cash;
  return { date: `2026-${String(i + 1).padStart(2, "0")}-01`, eq, bd, alt, cash };
});

export function StackedAreaReference() {
  const [sel, setSel] = useState<string | null>("2026-06-01");
  return (
    <section className="section-block">
      <p className="kicker">{"// stacked area"}</p>
      <h2 className="title">Sleeve weights over time.</h2>
      <p className="section-copy">
        <code>StackedAreaChart</code> stacks weights per date from an ordered token palette, with
        the cash series in a neutral wash. Selected: <code>{sel ?? "none"}</code>.
      </p>
      <StackedAreaChart
        data={DATA}
        keys={["eq", "bd", "alt"]}
        cashKey="cash"
        formatKey={(k) => ({ eq: "Equities", bd: "Bonds", alt: "Alternatives", cash: "Cash" })[k] ?? k}
        selectedX={sel}
        onSelect={setSel}
        label="Sleeve weights over 2026"
      />
    </section>
  );
}
