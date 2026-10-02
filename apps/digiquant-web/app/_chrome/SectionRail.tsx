"use client";

import { useEffect, useState } from "react";
import { BANDS } from "../_bands/registry";

/** Wayfinding in the left gutter (≥1400px): a tick per band plus a vertical
 *  terminal path naming the band under the viewport middle.
 *
 *  Hidden on the chart hero (`top`). First appears once you’ve scrolled into
 *  the second section (dashboard) and stays for every band below. */
const pad2 = (n: number) => String(n).padStart(2, "0");

export function SectionRail() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    let frame = 0;
    const read = () => {
      const mid = window.innerHeight / 2;
      let next = 0;
      BANDS.forEach((band, index) => {
        const el = document.getElementById(band.id);
        if (el && el.getBoundingClientRect().top <= mid) next = index;
      });
      setActive(next);
    };
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  // Hero = band 0. Rail stays off until the second section owns the midpoint.
  const visible = active >= 1;

  return (
    <nav
      aria-label="Page sections"
      aria-hidden={visible ? undefined : true}
      className={`fixed top-1/2 z-30 hidden -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-[1.1rem] font-mono text-[0.68rem] text-ink-mute transition-opacity duration-300 min-[1400px]:flex ${
        visible ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
      }`}
      style={{ left: "calc((100vw - var(--frame-w) - 2 * var(--page-pad)) / 4)" }}
    >
      <ol className="m-0 flex list-none flex-col items-center p-0">
        {BANDS.map((band, index) => (
          <li key={band.id}>
            <a
              href={`#${band.id}`}
              tabIndex={visible ? undefined : -1}
              aria-label={band.label}
              aria-current={index === active ? "location" : undefined}
              className="group flex h-[0.8rem] w-[1.4rem] items-center justify-center"
            >
              <span
                className={`block h-px transition-[width,background-color] duration-300 ${
                  index === active ? "w-[1.1rem] bg-ink" : "w-[0.5rem] bg-ink-mute group-hover:w-[0.8rem] group-hover:bg-ink-soft"
                }`}
              />
            </a>
          </li>
        ))}
      </ol>
      <span aria-hidden="true" className="rotate-180 whitespace-nowrap tracking-[0.04em] [writing-mode:vertical-rl]">
        <span className="text-ink-soft">{pad2(active + 1)}</span> / <span className="text-ink">{BANDS[active].label}</span>
      </span>
    </nav>
  );
}
