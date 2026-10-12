"use client";

import { useEffect, useState } from "react";
import { LIT_SHADE, REST_SHADE, wordmarkLines } from "./digivoice-wordmark.js";

/** Same 80ms step the digivoice TUI uses to advance the equalizer. */
const TICK_MS = 80;

function gray(rgb: number): string {
  const channel = rgb.toString(16).padStart(2, "0");
  return `#${channel}${channel}${channel}`;
}

const LIT = gray(LIT_SHADE.rgb);
const REST = gray(REST_SHADE.rgb);

/** The digivoice hero. Pixels and the equalizer come from `digivoice-wordmark.js`
 *  (the TUI component). This only draws those cubes. */
export function DigivoiceHero({ className }: { className?: string }) {
  const [tMs, setTMs] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      setTMs((now) => now + TICK_MS);
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const drawn = wordmarkLines("DIGIVOICE", { cols: 100, tMs, truecolor: true });
  const width = drawn.lines[0]?.length ?? 1;
  const height = drawn.scale * 10;

  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="digivoice"
      shapeRendering="crispEdges"
    >
      {drawn.cubes.map((cube) => (
        <rect
          key={`${cube.x}-${cube.y}`}
          x={cube.x}
          y={cube.y}
          width={1}
          height={1}
          fill={cube.bright ? LIT : REST}
        />
      ))}
    </svg>
  );
}
