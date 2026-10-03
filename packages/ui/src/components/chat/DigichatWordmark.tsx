"use client";

/**
 * Square-pixel DIGICHAT mark. The settled word is the logo. The scramble
 * is how it plays. Pixels are 1×1 user units with no radius.
 */
import { useEffect, useState } from "react";

import {
  CYCLE_MS,
  SETTLED_MS,
  shadeHex,
  wordmarkPixels,
} from "./digichat-wordmark";

const TICK_MS = 40;

export function DigichatWordmark() {
  const [tMs, setTMs] = useState(SETTLED_MS);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const origin = performance.now() - SETTLED_MS;
    const timer = window.setInterval(() => {
      setTMs((performance.now() - origin) % CYCLE_MS);
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const { pixels, width, height } = wordmarkPixels(tMs);
  const cell = 2;
  return (
    <svg
      className="digichat-wordmark"
      role="img"
      aria-label="digichat"
      width={width * cell}
      height={height * cell}
      viewBox={`0 0 ${width} ${height}`}
      shapeRendering="crispEdges"
      style={{ display: "block", borderRadius: 0 }}
    >
      {pixels.map((pixel) => (
        <rect
          key={`${pixel.x}-${pixel.y}`}
          x={pixel.x}
          y={pixel.y}
          width={1}
          height={1}
          rx={0}
          ry={0}
          fill={shadeHex(pixel.shade)}
        />
      ))}
    </svg>
  );
}
