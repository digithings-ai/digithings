"use client";
import { useState } from "react";
import { GraphSVG, modules } from "@digithings/web";

export default function ArchGraph() {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <figure className="dg-graph-wrap" style={{ maxWidth: 920, margin: "0 auto" }}
      onMouseLeave={() => setHover(null)}
      onMouseOver={(e) => {
        const g = (e.target as Element).closest?.(".dg-node") as SVGGElement | null;
        const lbl = g?.getAttribute("aria-label");
        if (lbl) setHover(modules.find((m) => m.name === lbl)?.id ?? null);
      }}>
      <GraphSVG activeId={hover} onPick={(id) => { location.href = `/modules/${id}`; }} />
    </figure>
  );
}
