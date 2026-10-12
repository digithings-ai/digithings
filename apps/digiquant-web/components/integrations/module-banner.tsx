"use client";

import { useEffect, useRef, useState } from "react";
import { BANNERS } from "../../../../packages/hero-banner/src/definitions";
import type { BannerDefinition } from "../../../../packages/hero-banner/src/types";
import { preparedBanner } from "../../../../packages/hero-banner/src/engine";
import { HeroBanner } from "../../../../packages/hero-banner/src/web";

/** One banner pixel, so every word draws at the same cap height. */
const CELL_REM = 0.15;
const WORD_ROWS = 10;

/** A module's own hero banner, small. Client-side because a banner definition
 *  carries its animation functions, which cannot cross from a server component.
 *  The banner stays blank until it scrolls into view, so its build plays where
 *  the reader sees it, not off screen while the top of the page loads. Height
 *  follows the banner's rows, and rows above the word (digiclaw's rail) rise
 *  into the space above, so every word sits on the same line at the same size. */
export function ModuleBanner({ name, className }: { name: string; className?: string }) {
  const def = (BANNERS as Record<string, BannerDefinition>)[name];
  const ref = useRef<HTMLSpanElement>(null);
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || armed) return;
    // Without IntersectionObserver there is nothing to wait for: arm on the next frame.
    if (typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => setArmed(true));
      return () => cancelAnimationFrame(frame);
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setArmed(true);
        observer.disconnect();
      },
      { threshold: 0.5 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [armed]);

  if (!def) return null;
  const rows = preparedBanner(def).layout.height;
  return (
    <span
      ref={ref}
      className="block w-fit"
      style={{ height: `${rows * CELL_REM}rem`, marginTop: `${(WORD_ROWS - rows) * CELL_REM}rem` }}
    >
      <HeroBanner def={def} armed={armed} className={className} />
    </span>
  );
}
