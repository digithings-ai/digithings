"use client";

/**
 * Square-pixel DIGICHAT mark. The settled word is the logo. The scramble
 * plays once per tab, then one letter flashes. Pixels are 1×1 with no radius.
 */
import { useEffect, useState } from "react";

import {
  WORDMARK_CLOCK_HOST,
  ensureWordmarkClock,
  heroWordmarkPixels,
  shadeHex,
  wordmarkSample,
  type WordmarkClock,
  type WordmarkStore,
} from "./digichat-wordmark";

const TICK_MS = 40;

function clockHost(): WordmarkClock | null {
  const bag = window as unknown as Record<string, WordmarkClock | undefined>;
  return bag[WORDMARK_CLOCK_HOST] ?? null;
}

function storeClock(clock: WordmarkClock) {
  (window as unknown as Record<string, WordmarkClock>)[WORDMARK_CLOCK_HOST] = clock;
}

export function DigichatWordmark() {
  const [sample, setSample] = useState({ elapsed: 0, full: false });

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let store: WordmarkStore | null = null;
    try {
      store = window.sessionStorage;
    } catch {
      store = null;
    }
    const clock = ensureWordmarkClock(performance.now(), store, clockHost());
    storeClock(clock);
    const tick = () => {
      const current = clockHost() ?? clock;
      setSample(wordmarkSample(performance.now(), current));
    };
    tick();
    const timer = window.setInterval(tick, TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const { pixels, width, height } = heroWordmarkPixels(sample.elapsed, sample.full);
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
