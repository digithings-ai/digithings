"use client";

import { useEffect, useState } from "react";
import { LANDING_SECTIONS } from "./sections";

/**
 * The landing page's wayfinding (Refs #4429): a terminal path set vertically
 * in the left gutter, outside the page rails, with one tick per band. The
 * path names the band under the middle of the viewport, and each tick jumps
 * to its band. It only renders where the gutter is wide enough to hold it.
 */

const SECTIONS = LANDING_SECTIONS;

export function SectionRail() {
  const [active, setActive] = useState(-1);

  useEffect(() => {
    /* One observer, a zero-height band on the viewport's middle line: the band
       whose top crossed that line is the one under the reader. Reading every
       section's rect on each scroll frame forced a layout per frame for seven
       1px ticks. An entry leaving the line is ignored rather than resetting the
       label, so the last band stays named after the page bottom scrolls past. */
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const index = SECTIONS.findIndex((section) => section.id === entry.target.id);
          if (index >= 0) setActive(index);
        }
      },
      { rootMargin: "-50% 0px -50% 0px" },
    );
    for (const section of SECTIONS) {
      const el = document.getElementById(section.id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, []);

  const current = active >= 0 ? SECTIONS[active] : null;

  return (
    <nav
      aria-label="Page sections"
      className="fixed top-1/2 z-30 hidden -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-[1.1rem] font-mono text-[0.68rem] text-ink-mute min-[1400px]:flex"
      style={{ left: "calc((100vw - var(--frame-w) - 2 * var(--page-pad)) / 4)" }}
    >
      <ol className="m-0 flex list-none flex-col items-center p-0">
        {SECTIONS.map((section, index) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              aria-label={section.label}
              aria-current={index === active ? "location" : undefined}
              className="group flex h-[0.8rem] w-[1.4rem] items-center justify-center"
            >
              <span
                className={`block h-px transition-colors duration-200 ease-brand ${
                  index === active
                    ? "w-[1.1rem] bg-ink"
                    : "w-[0.5rem] bg-ink-mute group-hover:w-[0.8rem] group-hover:bg-ink-soft"
                }`}
              />
            </a>
          </li>
        ))}
      </ol>
      <span
        aria-hidden="true"
        className="rotate-180 whitespace-nowrap tracking-[0.04em] [writing-mode:vertical-rl]"
      >
        ~/digithings
        {current ? <span className="text-ink">/{current.label}</span> : null}
      </span>
    </nav>
  );
}
